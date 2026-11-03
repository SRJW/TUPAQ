"""Native, offline desktop interface. Device writes are not implemented."""
import argparse
import csv
import plistlib
from pathlib import Path
import re
import sys
import tempfile
import time

from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView, QTabWidget, QTableView)

from .audio import inspect_audio, read_artwork
from .artwork import thumbnail
from .devices import discover, DiscoveryError
from .sync.signing import FixedHostSession
from .library import read_phone_library, LibraryError
from .models import LibraryModel

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
                track = inspect_audio(path, path.name)
                try:
                    track['thumbnail'] = thumbnail(read_artwork(path))
                except (OSError, ValueError):
                    track['thumbnail'] = None
                self.track.emit(track)
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


class LibraryReader(QThread):
    result = Signal(list)
    problem = Signal(str)

    def run(self):
        try:
            self.result.emit(read_phone_library())
        except LibraryError as error:
            self.problem.emit(f'{error}\nDiagnóstico: {error.diagnostic}')


def csv_value(value):
    text = str(value if value is not None else '')
    return "'"+text if re.match(r'^\s*[=+@-]', text) else text


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('Importios')
        self.resize(1140, 900)
        self.setMinimumSize(780, 580)
        self.setAcceptDrops(True)
        self.tracks = {}
        self.worker = None
        self.device_worker = None
        self.library_worker = None
        self.duplicates = 0
        panel = QWidget()
        self.setCentralWidget(panel)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(10)
        brand = QLabel('♫  importios')
        brand.setObjectName('brand')
        layout.addWidget(brand)
        title = QLabel('Tu música, en un solo lugar.')
        title.setObjectName('title')
        layout.addWidget(title)
        intro = QLabel('Elige o arrastra canciones MP3, WAV, M4A (AAC/ALAC) y AIFF. Los originales se conservan.')
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
        self.library_button = QPushButton('Leer biblioteca del iPhone')
        self.library_button.clicked.connect(self.load_library)
        connection.addWidget(self.library_button)
        self.device_status = QLabel('Detección sin sincronizar ni modificar el teléfono.')
        self.device_status.setWordWrap(True)
        connection.addStretch()
        self.copy_diagnostic = QPushButton('Copiar diagnóstico')
        self.last_diagnostic = ''
        self.copy_diagnostic.setEnabled(False)
        self.copy_diagnostic.clicked.connect(lambda: QApplication.clipboard().setText(self.last_diagnostic))
        connection.addWidget(self.copy_diagnostic)
        layout.addLayout(connection)
        self.device_status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.device_status)
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
        preview = QHBoxLayout()
        self.now_cover = QLabel('♫')
        self.now_cover.setFixedSize(72, 72)
        self.now_cover.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.addWidget(self.now_cover)
        self.now_title = QLabel('La portada de la canción aparecerá aquí, si el archivo la incluye.')
        self.now_title.setTextFormat(Qt.TextFormat.PlainText)
        self.now_title.setWordWrap(True)
        preview.addWidget(self.now_title, 1)
        layout.addLayout(preview)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Canción', 'Artista', 'Álbum', 'Formato', 'Duración', 'Tamaño'])
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.verticalHeader().hide()
        self.table.setIconSize(QSize(48, 48))
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.itemSelectionChanged.connect(self.update_buttons)
        self.tabs = QTabWidget()
        self.tabs.addTab(self.table, 'Canciones para preparar')
        self.library_model = LibraryModel(self)
        self.library_table = QTableView()
        self.library_table.setModel(self.library_model)
        self.library_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.library_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.library_table.verticalHeader().hide()
        self.tabs.addTab(self.library_table, 'Biblioteca del iPhone · solo lectura')
        layout.addWidget(self.tabs, 1)
        self.status = QLabel('Sin canciones. Puedes arrastrar archivos sobre esta ventana.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.progress = QProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        self.errors = QListWidget()
        self.errors.setMaximumHeight(72)
        self.errors.hide()
        layout.addWidget(self.errors)
        footer = QLabel('Análisis local · No se envían canciones a Internet · La lista no se conserva al cerrar')
        footer.setWordWrap(True)
        footer.setObjectName('footer')
        layout.addWidget(footer)
        self.setStyleSheet('''
            QWidget { background: #f5f5f7; color: #1d1d1f; font-size: 14px; }
            QLabel#brand { font-size: 19px; font-weight: 600; }
            QLabel#title { font-size: 27px; font-weight: 600; }
            QLabel#notice { background: #e9e9ed; border-radius: 9px; padding: 12px; color: #515154; }
            QLabel#footer { color: #6e6e73; font-size: 12px; }
            QPushButton { background: #ffffff; border: 1px solid #d2d2d7; padding: 8px 13px; border-radius: 7px; }
            QPushButton#primary { background: #007aff; color: white; border: 1px solid #007aff; font-weight: 600; }
            QPushButton:disabled { background: #eeeef0; color: #9b9ba0; border-color: #dedee2; }
            QPushButton:focus { border: 2px solid #007aff; }
            QTableWidget, QTableView { background: white; alternate-background-color: #fafafa; border: 1px solid #dedee2; gridline-color: #eeeeef; selection-background-color: #dcecff; selection-color: #1d1d1f; }
            QTableWidget::item { padding: 6px; }
            QHeaderView::section { background: #f2f2f4; color: #6e6e73; padding: 9px; border: 0; }
            QListWidget { background: #fff5f4; color: #a12c21; border: 1px solid #ecd5d2; }
            QProgressBar { border: 0; background: #e5e5ea; text-align: center; border-radius: 4px; }
            QProgressBar::chunk { background: #007aff; border-radius: 4px; }
            QTabBar::tab { background: #e9e9ed; padding: 8px 14px; margin-right: 2px; }
            QTabBar::tab:selected { background: #ffffff; color: #0066cc; }
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

    def load_library(self):
        if self.library_worker is not None:
            return
        self.library_model.replace([])
        self.tabs.setTabText(1, 'Biblioteca del iPhone · solo lectura')
        self.library_button.setEnabled(False)
        self.copy_diagnostic.setEnabled(False)
        self.tabs.setCurrentIndex(1)
        self.device_status.setText('Leyendo una copia de la biblioteca. Puede tardar hasta dos minutos…')
        self.library_worker = LibraryReader(self)
        self.library_worker.result.connect(self.show_library)
        self.library_worker.problem.connect(self.show_library_error)
        self.library_worker.finished.connect(self.library_finished)
        self.library_worker.start()

    def show_library(self, tracks):
        self.library_model.replace(tracks)
        self.tabs.setTabText(1, f"Biblioteca del iPhone · {len(tracks)} canciones")
        self.device_status.setText(f'{len(tracks)} canciones leídas. No se modificó la biblioteca. La importación sigue pendiente.')

    def show_library_error(self, message):
        self.last_diagnostic = message
        self.device_status.setText(message)
        self.copy_diagnostic.setEnabled(True)

    def library_finished(self):
        worker = self.library_worker
        self.library_worker = None
        if worker is not None:
            worker.deleteLater()
        self.library_button.setEnabled(True)

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
        picture = QPixmap()
        if track.get('thumbnail'):
            picture.loadFromData(track['thumbnail'])
        if picture.isNull():
            self.now_cover.setPixmap(QPixmap())
            self.now_cover.setText('♫')
        else:
            self.now_cover.setPixmap(picture.scaled(72, 72, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.now_title.setText(f"Preparando: {track['title']}\n{track['artist'] or 'Sin artista'}")
        row = self.table.rowCount()
        self.table.insertRow(row)
        seconds = int(track['duration'])
        values = [track['title'], track['artist'] or 'Sin artista', track['album'] or 'Sin álbum',
                  (f"M4A · {track['format']}" if track.get('container') == 'M4A' else track['format']), f'{seconds//60}:{seconds%60:02}', f"{track['size']/1024/1024:.1f} MB"]
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, track['id'])
                item.setToolTip(track['filename'])
                if not picture.isNull():
                    item.setIcon(QIcon(picture))
            self.table.setItem(row, column, item)
        self.table.setRowHeight(row, 58)

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
        self.now_cover.setPixmap(QPixmap())
        self.now_cover.setText('♫')
        self.now_title.setText('La portada de la canción aparecerá aquí, si el archivo la incluye.')
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
        if self.library_worker is not None:
            self.device_status.setText('Espera a que termine la lectura de la biblioteca antes de cerrar la ventana.')
            event.ignore()
            return
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
    # Import the USB transport inside the frozen build without opening a device.
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService
    assert callable(create_using_usbmux) and callable(AfcService)
    vectors = plistlib.loads((fixtures/'sync/grappa-fixed-vectors.plist').read_bytes())
    assert len(vectors) == 4
    for vector in vectors:
        session = FixedHostSession(vector['request'], vector['reply'])
        assert session.sign(vector['operation']) == vector['sidecar']
        session.close()
    files = [fixtures/name for name in ['sample.mp3', 'sample.wav', 'sample.aiff', 'sample.m4a', 'covered-aac.m4a']]
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
        assert window.table.rowCount() == 5
        assert {track['format'] for track in window.tracks.values()} == {'MP3', 'WAV', 'AIFF', 'ALAC', 'AAC'}
        assert not window.table.item(4, 0).icon().isNull()
        assert window.now_title.text().startswith('Preparando: M4A con portada')
        assert window.duplicates == 1
        assert window.errors.count() == 1
        path = folder/'list.csv'
        window.export_list(path)
        with path.open(encoding='utf-8-sig', newline='') as stream:
            assert len(list(csv.reader(stream))) == 6
        if output:
            assert window.grab().save(str(output))
        window.table.selectRow(0)
        window.remove_selection()
        assert len(window.tracks) == window.table.rowCount() == 4
        window.clear_tracks()
        assert not window.tracks and window.table.rowCount() == 0
        assert not window.export.isEnabled()
        assert all(path.exists() for path in files)
        window.show_library([{'id': 'test', 'title': 'Canción sintética', 'artist': 'Prueba', 'album': 'Prueba', 'duration': 1}])
        assert window.library_model.rowCount() == 1
        assert window.library_model.data(window.library_model.index(0, 0)) == 'Canción sintética'
        window.show_library_error('Error de prueba\nDiagnóstico: usb:ConnectionRefusedError')
        window.device_status.setText('Otro estado de prueba')
        window.copy_diagnostic.click()
        assert QApplication.clipboard().text() == 'Error de prueba\nDiagnóstico: usb:ConnectionRefusedError'


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
