"""Native, offline desktop interface. Device writes are not implemented."""
import argparse
import csv
import plistlib
from pathlib import Path
import re
import sys
import tempfile
import time

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView)

from .audio import inspect_audio
from .devices import discover, DiscoveryError
from .sync.signing import FixedHostSession

MAX_SIZE = 256 * 1024 * 1024


class Reader(QThread):
    track = Signal(dict)
    problem = Signal(str)
    progress = Signal(int, int)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = paths

    def run(self):
        for index, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                break
            try:
                if not 0 < path.stat().st_size <= MAX_SIZE:
                    raise ValueError('El archivo está vacío o supera los 256 MB.')
                self.track.emit(inspect_audio(path, path.name))
            except (OSError, ValueError) as error:
                self.problem.emit(f'{path.name}: {error}')
            self.progress.emit(index+1, len(self.paths))


class DeviceReader(QThread):
    result = Signal(str)

    def run(self):
        try:
            count = len(discover())
            self.result.emit(f'{count} dispositivos Apple detectados por USB. Esto no verifica la importación a Música.'
                if count else 'No se detectaron dispositivos Apple por USB. Conecta y desbloquea el iPhone.')
        except DiscoveryError as error:
            self.result.emit(str(error))


def csv_value(value):
    text = str(value if value is not None else '')
    return "'"+text if re.match(r'^\s*[=+@-]', text) else text


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Importios')
        self.resize(1140, 780)
        self.setMinimumSize(780, 580)
        self.setAcceptDrops(True)
        self.tracks = {}
        self.worker = None
        self.device_worker = None
        self.duplicates = 0
        panel = QWidget()
        self.setCentralWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(16)
        brand = QLabel('♫  importios')
        brand.setObjectName('brand')
        layout.addWidget(brand)
        title = QLabel('Tu música, en un solo lugar.')
        title.setObjectName('title')
        layout.addWidget(title)
        intro = QLabel('Elige o arrastra canciones MP3, WAV, ALAC y AIFF. Los originales se conservan.')
        intro.setWordWrap(True)
        layout.addWidget(intro)
        notice = QLabel('Transferencia al iPhone: pendiente de implementar y verificar.\n'
                        'Esta versión prepara canciones; no modifica la biblioteca de Música.')
        notice.setObjectName('notice')
        notice.setWordWrap(True)
        layout.addWidget(notice)
        connection = QHBoxLayout()
        self.device_button = QPushButton('Comprobar iPhone por USB')
        self.device_button.clicked.connect(self.check_device)
        connection.addWidget(self.device_button)
        self.device_status = QLabel('Detección sin sincronizar ni modificar el teléfono.')
        self.device_status.setWordWrap(True)
        connection.addWidget(self.device_status, 1)
        layout.addLayout(connection)
        buttons = QHBoxLayout()
        self.choose = QPushButton('Elegir canciones')
        self.choose.setObjectName('primary')
        self.choose.clicked.connect(self.choose_files)
        buttons.addWidget(self.choose)
        self.remove = QPushButton('Quitar selección')
        self.remove.clicked.connect(self.remove_selection)
        buttons.addWidget(self.remove)
        self.clear = QPushButton('Vaciar lista')
        self.clear.clicked.connect(self.clear_tracks)
        buttons.addWidget(self.clear)
        buttons.addStretch()
        self.export = QPushButton('Guardar lista CSV')
        self.export.clicked.connect(self.choose_export)
        buttons.addWidget(self.export)
        layout.addLayout(buttons)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Canción', 'Artista', 'Álbum', 'Formato', 'Duración', 'Tamaño'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        layout.addWidget(self.table, 1)
        self.status = QLabel('Sin canciones. Puedes arrastrar archivos sobre esta ventana.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.errors = QListWidget()
        self.errors.setMaximumHeight(100)
        self.errors.hide()
        layout.addWidget(self.errors)
        footer = QLabel('Análisis local · No se envían canciones a Internet · La lista no se conserva al cerrar')
        footer.setWordWrap(True)
        footer.setObjectName('footer')
        layout.addWidget(footer)
        self.setStyleSheet('''
            QWidget { background: #111723; color: #e9eef7; font-size: 14px; }
            QLabel#brand { font-size: 23px; color: #b5f3ce; font-weight: 700; }
            QLabel#title { font-size: 30px; font-weight: 700; }
            QLabel#notice { background: #202d3d; border-left: 3px solid #b5f3ce; padding: 15px; }
            QLabel#footer { color: #a3b0c5; font-size: 12px; }
            QPushButton { background: #29374c; padding: 11px 15px; border: 0; border-radius: 7px; }
            QPushButton#primary { background: #b5f3ce; color: #14251b; font-weight: 700; }
            QPushButton:disabled { background: #202939; color: #6d7d96; }
            QPushButton:focus { border: 2px solid #b5f3ce; }
            QTableWidget { background: #161e2d; border: 1px solid #33425a; gridline-color: #33425a; }
            QTableWidget::item { padding: 8px; }
            QTableWidget::item:selected { background: #334f65; }
            QHeaderView::section { background: #233047; padding: 10px; border: 0; }
            QListWidget { color: #ffb5b5; border: 1px solid #513745; }
            QProgressBar { border: 0; background: #263249; text-align: center; }
            QProgressBar::chunk { background: #54876c; }
        ''')
        self.update_buttons()

    def update_buttons(self):
        busy = self.worker is not None
        self.choose.setEnabled(not busy)
        self.clear.setEnabled(not busy and bool(self.tracks))
        self.export.setEnabled(not busy and bool(self.tracks))
        self.remove.setEnabled(not busy and bool(self.table.selectionModel().selectedRows()))

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Elegir canciones', '',
            'Audio (*.mp3 *.wav *.m4a *.alac *.aif *.aiff);;Todos los archivos (*)')
        self.add_paths(paths)

    def check_device(self):
        if self.device_worker is not None:
            return
        self.device_button.setEnabled(False)
        self.device_status.setText('Consultando el servicio local de Apple…')
        self.device_worker = DeviceReader(self)
        self.device_worker.result.connect(self.device_status.setText)
        self.device_worker.finished.connect(self.device_finished)
        self.device_worker.start()

    def device_finished(self):
        worker = self.device_worker
        self.device_worker = None
        if worker is not None:
            worker.deleteLater()
        self.device_button.setEnabled(True)

    def add_paths(self, paths):
        if self.worker is not None or not paths:
            return
        self.errors.clear()
        self.errors.hide()
        self.duplicates = 0
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText('Revisando canciones…')
        self.worker = Reader([Path(path) for path in paths], self)
        self.worker.track.connect(self.accept_track)
        self.worker.problem.connect(self.show_problem)
        self.worker.progress.connect(lambda value, total: self.progress.setValue(value))
        self.worker.finished.connect(self.read_finished)
        self.update_buttons()
        self.worker.start()

    def accept_track(self, track):
        if track['id'] in self.tracks:
            self.duplicates += 1
            return
        self.tracks[track['id']] = track
        row = self.table.rowCount()
        self.table.insertRow(row)
        seconds = int(track['duration'])
        values = [track['title'], track['artist'] or 'Sin artista', track['album'] or 'Sin álbum',
                  track['format'], f'{seconds//60}:{seconds%60:02}', f"{track['size']/1024/1024:.1f} MB"]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, track['id'])
                item.setToolTip(track['filename'])
            self.table.setItem(row, column, item)
        self.table.resizeRowToContents(row)

    def show_problem(self, message):
        self.errors.addItem(message)
        self.errors.show()

    def read_finished(self):
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.progress.hide()
        self.status.setText(f'{len(self.tracks)} canciones · Duplicadas omitidas: {self.duplicates}'
                            f' · No añadidas: {self.errors.count()}')
        self.update_buttons()

    def remove_selection(self):
        for row in sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True):
            self.tracks.pop(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            self.table.removeRow(row)
        self.status.setText(f'{len(self.tracks)} canciones. Los archivos originales se conservan.')
        self.update_buttons()

    def clear_tracks(self):
        self.table.setRowCount(0)
        self.tracks.clear()
        self.errors.clear()
        self.errors.hide()
        self.status.setText('Lista vaciada. Los archivos originales se conservan.')
        self.update_buttons()

    def export_list(self, path):
        with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['Archivo', 'Título', 'Artista', 'Álbum', 'Formato', 'Duración (segundos)', 'Tamaño (bytes)', 'SHA-256'])
            for track in self.tracks.values():
                writer.writerow([csv_value(track[key]) for key in
                    ['filename', 'title', 'artist', 'album', 'format', 'duration', 'size', 'id']])

    def choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar lista', 'importios-canciones.csv', 'CSV (*.csv)')
        if path:
            try:
                self.export_list(path)
                self.status.setText('Lista guardada.')
            except OSError:
                QMessageBox.warning(self, 'No se pudo guardar', 'Elige una carpeta donde tengas permiso para escribir.')

    def dragEnterEvent(self, event):
        if self.worker is None and event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_paths(paths)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.tracks and QMessageBox.question(self, 'Cerrar Importios',
            'La lista no se conserva al cerrar. ¿Quieres salir?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()
        if self.device_worker is not None:
            self.device_worker.wait()
        event.accept()


def smoke(app, window, fixtures, output=None):
    vectors = plistlib.loads((fixtures/'sync/grappa-fixed-vectors.plist').read_bytes())
    assert len(vectors) == 4
    for vector in vectors:
        session = FixedHostSession(vector['request'], vector['reply'])
        assert session.sign(vector['operation']) == vector['sidecar']
        session.close()
    files = [fixtures/name for name in ['sample.mp3', 'sample.wav', 'sample.aiff', 'sample.m4a']]
    with tempfile.TemporaryDirectory(prefix='importios-native-test-') as temporary:
        folder = Path(temporary)
        invalid = folder/'broken.wav'
        invalid.write_bytes(b'not audio')
        window.add_paths(files+[files[0], invalid])
        deadline = time.monotonic()+45
        while window.worker is not None:
            app.processEvents()
            if time.monotonic() > deadline:
                raise RuntimeError('Native audio inspection timed out')
            time.sleep(0.005)
        assert window.table.rowCount() == 4
        assert {track['format'] for track in window.tracks.values()} == {'MP3', 'WAV', 'AIFF', 'ALAC'}
        assert window.duplicates == 1
        assert window.errors.count() == 1
        path = folder/'list.csv'
        window.export_list(path)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            assert len(list(csv.reader(stream))) == 5
        if output:
            assert window.grab().save(str(output))
        window.table.selectRow(0)
        window.remove_selection()
        assert len(window.tracks) == window.table.rowCount() == 3
        window.clear_tracks()
        assert not window.tracks and window.table.rowCount() == 0
        assert not window.export.isEnabled()
        assert all(path.exists() for path in files)


def main():
    parser = argparse.ArgumentParser(description='Importios: aplicación de escritorio')
    parser.add_argument('--smoke-fixtures', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-report', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-screenshot', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName('Importios')
    app.setOrganizationName('Importios')
    window = Window()
    window.show()
    if args.smoke_fixtures:
        smoke(app, window, args.smoke_fixtures, args.smoke_screenshot)
        if args.smoke_report:
            args.smoke_report.write_text('native-ui-smoke-passed', encoding='ascii')
        return
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
