"""Native desktop interface for local preparation and USB audio transfers."""
import argparse
import csv
from contextlib import closing
import plistlib
from pathlib import Path
import re
import sys
import sqlite3
import tempfile
import time
import asyncio

from PySide6.QtCore import Qt, QThread, Signal, QSize, QStandardPaths, QLockFile, QUrl, QTimer, QSettings, QPoint
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices
from PySide6.QtWidgets import (QApplication, QFileDialog, QHBoxLayout, QHeaderView,
    QLabel, QListWidget, QMainWindow, QMessageBox, QProgressBar, QPushButton,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView, QTabWidget, QTableView)

from .audio import inspect_audio, read_artwork
from .artwork import thumbnail
from .devices import discover, DiscoveryError
from .sync.signing import FixedHostSession
from .library import read_phone_library, read_catalogue, LibraryError, format_diagnostics
from .models import LibraryModel
from .version import VERSION
from .transfers import run_transfer, TransferError

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
                track['path'] = str(path.resolve())
                try:
                    track['thumbnail'] = thumbnail(read_artwork(path))
                except (OSError, ValueError):
                    track['thumbnail'] = None
                self.track.emit(track)
            except (OSError, ValueError) as error:
                self.problem.emit(f'{path.name}: {error}')
            self.progress.emit(index+1, len(self.paths))


class DeviceReader(QThread):
    result = Signal(list)
    problem = Signal(str)

    def run(self):
        try:
            self.result.emit(discover(fingerprint=True))
        except DiscoveryError as error:
            self.problem.emit(str(error))


class LibraryReader(QThread):
    result = Signal(list, str)
    problem = Signal(str)
    name = Signal(str)

    def run(self):
        try:
            diagnostics = {}
            info = {}
            tracks = read_phone_library(diagnostics=diagnostics,device_info=info)
            self.name.emit(info.get('name','iPhone'))
            self.result.emit(tracks, format_diagnostics(diagnostics))
        except LibraryError as error:
            self.problem.emit(f'TUPAQ {VERSION}\n{error}\nDiagnóstico: {error.diagnostic}')


class ArtworkReader(QThread):
    image = Signal(int,str,bytes)

    def __init__(self, tracks, epoch, parent=None):
        super().__init__(parent)
        self.tracks,self.epoch = tracks,epoch
        self.loop = self.task = None

    def stop(self):
        self.requestInterruption()
        if self.loop is not None and self.task is not None:
            try:
                self.loop.call_soon_threadsafe(self.task.cancel)
            except RuntimeError:
                pass

    def run(self):
        async def work():
            from .transfers import device
            from .remote_artwork import cover_for_track
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.current_task()
            async with device() as (_,afc):
                for track in self.tracks:
                    if self.isInterruptionRequested():
                        break
                    try:
                        result = await asyncio.wait_for(cover_for_track(afc,track,self.isInterruptionRequested),timeout=10)
                        if result and not self.isInterruptionRequested():
                            self.image.emit(self.epoch,track['id'],result)
                    except Exception:
                        continue
        try:
            asyncio.run(work())
        except (Exception,asyncio.CancelledError):
            pass
        finally:
            self.loop = self.task = None


class TransferWorker(QThread):
    result = Signal(dict)
    problem = Signal(str)
    progress = Signal(int,int,str,str)

    def __init__(self, mode, selected, destination, lock_path, parent=None):
        super().__init__(parent)
        self.mode, self.selected, self.destination, self.lock_path = mode, selected, destination, lock_path

    def run(self):
        lock = QLockFile(str(self.lock_path))
        if not lock.tryLock(0):
            self.problem.emit('Hay otra transferencia de TUPAQ en curso.\nDiagnóstico: transfer:busy')
            return
        try:
            def report(value,total,label,identifier=''):
                self.progress.emit(value,total,label,identifier)
            self.result.emit(run_transfer(self.mode,self.selected,self.destination,report))
        except TransferError as error:
            self.problem.emit(f'TUPAQ {VERSION}\n{error}\nDiagnóstico: {error.diagnostic}')
        finally:
            lock.unlock()


def csv_value(value):
    text = str(value if value is not None else '')
    return "'"+text if re.match(r'^\s*[=+@-]', text) else text


class Window(QMainWindow):
    def __init__(self, auto_connect=True):
        super().__init__()
        self.setWindowTitle(f'TUPAQ {VERSION}')
        self.resize(1260, 900)
        self.setMinimumSize(980, 660)
        self.setAcceptDrops(True)
        self.tracks = {}
        self.worker = None
        self.device_worker = None
        self.library_worker = None
        self.transfer_worker = None
        self.transfer_outcome = None
        self.progress_track_id = None
        self.backup_root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))/'catalogue-backups'
        self.background_enabled = auto_connect
        self.thumbnail_worker = None
        self.after_artwork = None
        self.connection_token = None
        self.library_ready = False
        self.retry_library_at = 0
        self.library_epoch = 0
        self.artwork_attempted = set()
        self.duplicates = 0
        from .interface import build, apply_theme
        build(self)
        self.persist_settings = auto_connect
        if self.persist_settings:
            settings = QSettings()
            self.theme_choice.setCurrentIndex(int(settings.value('appearance',0)))
            self.auto_read.setChecked(settings.value('automatic_library',True,type=bool))
        self.theme_choice.currentIndexChanged.connect(self.change_theme)
        self.auto_read.toggled.connect(self.change_auto_read)
        QApplication.styleHints().colorSchemeChanged.connect(self.system_theme_changed)
        apply_theme(self)
        self.device_timer = QTimer(self)
        self.device_timer.setInterval(5000)
        self.device_timer.timeout.connect(self.poll_device)
        self.artwork_timer = QTimer(self)
        self.artwork_timer.setSingleShot(True)
        self.artwork_timer.setInterval(180)
        self.artwork_timer.timeout.connect(self.fetch_visible_artwork)
        self.library_table.verticalScrollBar().valueChanged.connect(self.schedule_artwork)
        self.view_changed(0)
        self.nav_buttons[0].setChecked(True)
        self.change_theme()
        if self.background_enabled and self.auto_read.isChecked():
            self.device_timer.start()
            QTimer.singleShot(150,self.poll_device)
        self.update_buttons()

    def update_buttons(self):
        busy = self.worker is not None or self.transfer_worker is not None or self.after_artwork is not None
        self.choose.setEnabled(not busy)
        self.clear.setEnabled(not busy and bool(self.tracks))
        self.export.setEnabled(not busy and bool(self.tracks))
        self.remove.setEnabled(not busy and bool(self.table.selectionModel().selectedRows()))
        phone_busy = busy or self.library_worker is not None or self.device_worker is not None or self.after_artwork is not None
        self.device_button.setEnabled(not phone_busy)
        self.library_button.setEnabled(not phone_busy)
        self.import_phone.setEnabled(not phone_busy and bool(self.tracks) and self.tabs.currentIndex() == 0)
        rows = self.library_table.selectionModel().selectedRows()
        self.export_phone.setEnabled(not phone_busy and self.tabs.currentIndex() == 1 and bool(rows)
            and all(self.library_model.tracks[r.row()].get('afc_path') for r in rows))
        self.verify_import.setEnabled(not phone_busy and self.backup_root.exists())
        self.open_backup.setEnabled(self.backup_root.exists())

    def navigate(self, number):
        self.pages.setCurrentIndex(1 if number == 3 else 0)
        if number != 3:
            self.tabs.setCurrentIndex(1 if number == 1 else 0)
            self.heading.setText('Tu biblioteca, siempre cerca.' if number == 1 else
                                 'Importar música al iPhone.' if number == 2 else 'Tu música, en un solo lugar.')
        from .interface import apply_theme
        apply_theme(self)
        self.schedule_artwork()

    def view_changed(self, index):
        self.local_tools.setVisible(index == 0)
        self.import_phone.setVisible(index == 0)
        self.export_phone.setVisible(index == 1)
        if index == 1:
            self.nav_buttons[1].setChecked(True)
            self.heading.setText('Tu biblioteca, siempre cerca.')
        elif self.nav_buttons[1].isChecked():
            self.nav_buttons[2].setChecked(True)
            self.heading.setText('Importar música al iPhone.')
        from .interface import apply_theme
        apply_theme(self)
        self.update_buttons()
        if self.worker is None and self.transfer_worker is None:
            self.status.setText(f'{len(self.library_model.tracks)} canciones en el iPhone.' if index == 1
                else f'{len(self.tracks)} canciones preparadas · Duplicadas omitidas: {self.duplicates}')
        self.schedule_artwork()

    def change_theme(self, *ignored):
        hints = QApplication.styleHints()
        index = self.theme_choice.currentIndex()
        if index == 0:
            hints.unsetColorScheme()
        else:
            hints.setColorScheme(Qt.ColorScheme.Dark if index == 2 else Qt.ColorScheme.Light)
        from .interface import apply_theme
        apply_theme(self)
        if self.persist_settings:
            QSettings().setValue('appearance',self.theme_choice.currentIndex())

    def system_theme_changed(self, *ignored):
        if self.theme_choice.currentIndex() == 0:
            from .interface import apply_theme
            apply_theme(self)

    def change_auto_read(self, enabled):
        if self.persist_settings:
            QSettings().setValue('automatic_library',enabled)
        if enabled and self.background_enabled:
            self.device_timer.start()
            self.poll_device()
        else:
            self.device_timer.stop()

    def open_backup_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.backup_root)))

    def poll_device(self):
        if not self.background_enabled or not self.auto_read.isChecked() or self.thumbnail_worker is not None or self.after_artwork is not None:
            return
        self.check_device(automatic=True)

    def devices_found(self, devices):
        if len(devices) != 1:
            self.connection_token = None
            self.library_ready = False
            self.library_epoch += 1
            self.library_model.replace([])
            self.artwork_attempted.clear()
            self.device_name.setText('iPhone')
            self.connection_badge.setText('○ Sin conexión USB' if not devices else '● Conecta un solo iPhone')
            self.device_status.setText('Conecta tu iPhone. Su biblioteca aparecerá automáticamente.' if not devices else 'Se detectó más de un dispositivo Apple. Conecta un solo iPhone para continuar.')
            return
        token = devices[0].get('token','usb')
        changed = token != self.connection_token
        if changed:
            self.connection_token = token
            self.library_ready = False
            self.retry_library_at = 0
            self.library_epoch += 1
            self.library_model.replace([])
            self.artwork_attempted.clear()
        self.connection_badge.setText('● Conectado por USB')
        if not self.library_ready and time.monotonic() >= self.retry_library_at:
            self.load_library(automatic=True)

    def device_problem(self, message):
        self.connection_token = None
        self.library_ready = False
        self.library_epoch += 1
        self.library_model.replace([])
        self.artwork_attempted.clear()
        self.connection_badge.setText('○ Servicio USB no disponible')
        if self.connection_token is None:
            self.device_status.setText(message)

    def schedule_artwork(self, *ignored):
        if self.background_enabled and hasattr(self,'artwork_timer'):
            self.artwork_timer.start()

    def fetch_visible_artwork(self):
        if (self.thumbnail_worker is not None or self.library_worker is not None or self.transfer_worker is not None
            or self.after_artwork is not None or self.tabs.currentIndex() != 1 or self.pages.currentIndex() != 0):
            return
        first = self.library_table.indexAt(QPoint(1,1)).row()
        first = max(first,0)
        count = min(32,max(1,self.library_table.viewport().height()//56+3))
        wanted = [dict(track) for track in self.library_model.tracks[first:first+count]
            if track['id'] not in self.artwork_attempted and track['id'] not in self.library_model.icons
            and (track.get('artwork_paths') or track.get('afc_path'))]
        if not wanted:
            return
        if len(self.artwork_attempted)>4096:
            self.artwork_attempted.clear()
        self.artwork_attempted.update(track['id'] for track in wanted)
        self.thumbnail_worker = ArtworkReader(wanted,self.library_epoch,self)
        self.thumbnail_worker.image.connect(self.phone_artwork_ready)
        self.thumbnail_worker.finished.connect(self.artwork_finished)
        self.thumbnail_worker.start()

    def phone_artwork_ready(self, epoch, identifier, data):
        if epoch != self.library_epoch:
            return
        image = QPixmap()
        if image.loadFromData(data):
            self.library_model.set_icon(identifier,QIcon(image))
            self.artwork_attempted.discard(identifier)
            self.library_selection_changed()

    def library_selection_changed(self, *ignored):
        self.update_buttons()
        rows = self.library_table.selectionModel().selectedRows()
        if not rows or self.tabs.currentIndex() != 1:
            return
        track = self.library_model.tracks[rows[0].row()]
        icon = self.library_model.icons.get(track['id'],self.default_music_icon)
        self.now_cover.setPixmap(icon.pixmap(64,64))
        self.now_title.setText(f"{track['title']}\n{track['artist'] or 'Sin artista'}")

    def artwork_finished(self):
        worker = self.thumbnail_worker
        self.thumbnail_worker = None
        worker.deleteLater()
        pending,self.after_artwork = self.after_artwork,None
        self.update_buttons()
        if pending:
            if pending[0] == 'library':
                self.load_library(automatic=pending[1])
            else:
                self.start_transfer(*pending[1:])
        else:
            self.schedule_artwork()

    def import_songs(self):
        rows = self.table.selectionModel().selectedRows()
        identifiers = [self.table.item(r.row(),0).data(Qt.ItemDataRole.UserRole) for r in rows] if rows else list(self.tracks)
        self.start_transfer('import',[dict(self.tracks[i]) for i in identifiers],self.backup_root)

    def export_songs(self):
        selected = [dict(self.library_model.tracks[r.row()]) for r in self.library_table.selectionModel().selectedRows()]
        if not selected:
            return
        folder = QFileDialog.getExistingDirectory(self,'Guardar audio del iPhone en…')
        if folder:
            self.start_transfer('export',selected,Path(folder))

    def start_transfer(self, mode, selected, destination):
        if self.transfer_worker is not None or self.worker is not None or self.library_worker is not None or self.device_worker is not None:
            return
        if mode == 'import' and not selected:
            return
        if self.thumbnail_worker is not None:
            self.after_artwork = ('transfer',mode,selected,destination)
            self.thumbnail_worker.stop()
            self.update_buttons()
            return
        try:
            self.backup_root.parent.mkdir(parents=True,exist_ok=True)
        except OSError:
            self.show_library_error('No se pudo preparar la carpeta local de datos de TUPAQ.\nDiagnóstico: transfer:local-folder')
            return
        self.transfer_outcome = None
        self.transfer_worker = TransferWorker(mode,selected,destination,self.backup_root.parent/'transfer.lock',self)
        self.transfer_worker.progress.connect(self.transfer_progress)
        self.transfer_worker.result.connect(self.transfer_result)
        self.transfer_worker.problem.connect(self.transfer_problem)
        self.transfer_worker.finished.connect(self.transfer_finished)
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText('Preparando transferencia…')
        self.update_buttons()
        self.transfer_worker.start()

    def transfer_progress(self, value, total, label, identifier=''):
        self.progress.setRange(0,max(1,total))
        self.progress.setValue(value)
        self.status.setText(label)
        if identifier and identifier != self.progress_track_id and identifier in self.tracks:
            self.progress_track_id = identifier
            track = self.tracks[identifier]
            picture = QPixmap()
            if track.get('thumbnail'):
                picture.loadFromData(track['thumbnail'])
            if picture.isNull():
                self.now_cover.setPixmap(QPixmap())
                self.now_cover.setText('♫')
            else:
                self.now_cover.setPixmap(picture.scaled(72,72,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
            self.now_title.setText(f"{track['title']}\n{track['artist'] or 'Sin artista'}")

    def transfer_problem(self, message):
        self.show_library_error(message)
        self.status.setText('Transferencia detenida. Consulta el diagnóstico antes de repetirla.')

    def transfer_result(self, result):
        self.transfer_outcome = result
        if 'exported' in result:
            self.status.setText(f"{result['exported']} archivos exportados y comprobados.")
        else:
            count = result.get('imported',result.get('verified',0))
            skipped = result.get('already_imported',0)
            self.status.setText(f'{count} canciones importadas y comprobadas. Ya importadas: {skipped}. Copia del catálogo en Ver respaldo.')

    def transfer_finished(self):
        worker = self.transfer_worker
        self.transfer_worker = None
        worker.deleteLater()
        self.progress.hide()
        if self.transfer_outcome:
            completed = set(self.transfer_outcome.get('source_ids',[]))
            for row in range(self.table.rowCount()-1,-1,-1):
                identifier = self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
                if identifier in completed:
                    self.tracks.pop(identifier,None)
                    self.table.removeRow(row)
        self.update_buttons()
        if self.transfer_outcome and ('imported' in self.transfer_outcome or 'verified' in self.transfer_outcome):
            self.load_library()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, 'Elegir canciones', '',
            'Audio (*.mp3 *.wav *.m4a *.alac *.aif *.aiff);;Todos los archivos (*)')
        self.add_paths(paths)

    def check_device(self, automatic=False):
        if self.device_worker is not None or self.transfer_worker is not None or self.library_worker is not None or self.after_artwork is not None:
            return
        self.device_button.setEnabled(False)
        if not automatic:
            self.device_status.setText('Consultando el servicio local de Apple…')
        self.device_worker = DeviceReader(self)
        self.device_worker.result.connect(self.devices_found)
        self.device_worker.problem.connect(self.device_problem)
        self.device_worker.finished.connect(self.device_finished)
        self.update_buttons()
        self.device_worker.start()

    def device_finished(self):
        worker = self.device_worker
        self.device_worker = None
        if worker is not None:
            worker.deleteLater()
        self.device_button.setEnabled(True)
        self.update_buttons()

    def load_library(self, automatic=False):
        if self.library_worker is not None or self.transfer_worker is not None:
            return
        if self.thumbnail_worker is not None:
            self.after_artwork = ('library',automatic)
            self.thumbnail_worker.stop()
            self.update_buttons()
            return
        self.library_epoch += 1
        self.artwork_attempted.clear()
        self.library_ready = False
        self.library_model.replace([])
        self.tabs.setTabText(1, 'Biblioteca del iPhone · leyendo…')
        self.library_button.setEnabled(False)
        self.copy_diagnostic.setEnabled(False)
        if not automatic or (not self.tracks and self.pages.currentIndex() == 0):
            self.nav_buttons[1].setChecked(True)
            self.navigate(1)
        self.device_status.setText('Leyendo una copia de la biblioteca. Puede tardar hasta dos minutos…')
        self.library_worker = LibraryReader(self)
        self.library_worker.result.connect(self.show_library)
        self.library_worker.problem.connect(self.library_problem)
        self.library_worker.name.connect(self.device_name.setText)
        self.library_worker.finished.connect(self.library_finished)
        self.update_buttons()
        self.library_worker.start()

    def show_library(self, tracks, diagnostic=''):
        self.library_model.replace(tracks)
        self.last_diagnostic = diagnostic or format_diagnostics({'tracks_returned': len(tracks)})
        self.copy_diagnostic.setEnabled(True)
        self.library_ready = True
        self.retry_library_at = 0
        self.connection_badge.setText('● Conectado por USB')
        if self.tabs.currentIndex() == 1 and self.transfer_worker is None:
            self.status.setText(f'{len(tracks)} canciones en el iPhone.')
        self.tabs.setTabText(1, f"Biblioteca del iPhone · {len(tracks)} resultados")
        self.device_status.setText(f'{len(tracks)} canciones leídas. Selecciona las que quieras exportar al ordenador.'
            if tracks else 'No se encontraron canciones en el catálogo consultado. Esto no confirma que Música esté vacía. Pulsa Copiar diagnóstico.')
        self.update_buttons()
        self.schedule_artwork()

    def library_problem(self, message):
        self.library_ready = False
        self.retry_library_at = time.monotonic()+20
        self.show_library_error(message)

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
        self.update_buttons()
        self.schedule_artwork()

    def add_paths(self, paths):
        if self.worker is not None or self.transfer_worker is not None or not paths:
            return
        self.errors.clear()
        self.tabs.setCurrentIndex(0)
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
                else:
                    item.setIcon(self.default_music_icon)
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
        path, _ = QFileDialog.getSaveFileName(self, 'Guardar lista', 'tupaq-canciones.csv', 'CSV (*.csv)')
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
        if self.transfer_worker is not None:
            self.status.setText('Espera a que termine la transferencia y su comprobación antes de cerrar.')
            event.ignore()
            return
        if self.library_worker is not None:
            self.device_status.setText('Espera a que termine la lectura de la biblioteca antes de cerrar la ventana.')
            event.ignore()
            return
        if self.tracks and QMessageBox.question(self, 'Cerrar TUPAQ',
            'La lista no se conserva al cerrar. ¿Quieres salir?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self.after_artwork = None
        self.device_timer.stop()
        self.artwork_timer.stop()
        if self.thumbnail_worker is not None:
            self.thumbnail_worker.stop()
            self.thumbnail_worker.wait()
        if self.worker is not None:
            self.worker.requestInterruption()
            self.worker.wait()
        if self.device_worker is not None:
            self.device_worker.wait()
        event.accept()


def smoke(app, window, fixtures, output=None):
    assert window.windowTitle() == f'TUPAQ {VERSION}' and app.applicationName() == 'TUPAQ'
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
        window.show_library([], format_diagnostics({'items_total': 3, 'music_items': 0, 'tracks_returned': 0}))
        assert window.copy_diagnostic.isEnabled() and window.library_model.rowCount() == 0
        assert 'no confirma' in window.device_status.text()
        window.copy_diagnostic.click()
        assert '"items_total": 3' in QApplication.clipboard().text()
        # Exercise a reference-shaped iOS catalogue through SQLite, the worker,
        # its signal and the UI. This used to hide music with media_type=8.
        catalogue = folder/'ios27.sqlitedb'
        with closing(sqlite3.connect(catalogue)) as db:
            db.executescript((fixtures/'library-ios27.sql').read_text(encoding='utf-8'))
        original_reader = globals()['read_phone_library']
        def simulated_catalogue(diagnostics=None, device_info=None):
            return read_catalogue(catalogue, diagnostics)
        try:
            globals()['read_phone_library'] = simulated_catalogue
            window.devices_found([{'token':'simulated-attach'}])
            deadline = time.monotonic()+10
            while window.library_worker is not None:
                app.processEvents()
                if time.monotonic() > deadline:
                    raise RuntimeError('Library result signal timed out')
                time.sleep(0.005)
        finally:
            globals()['read_phone_library'] = original_reader
        window.copy_diagnostic.click()
        assert '"music_items": 1' in QApplication.clipboard().text()
        assert '"music_type_code": 8' in QApplication.clipboard().text()
        assert window.library_model.rowCount() == 1
        assert window.library_model.data(window.library_model.index(0, 0)) == 'Canción de catálogo iOS 27'
        assert window.tabs.currentIndex() == 1 and window.library_ready
        window.devices_found([{'token':'simulated-attach'}])
        assert window.library_worker is None
        window.library_model.set_icon(window.library_model.tracks[0]['id'],window.default_music_icon)
        window.library_table.selectRow(0)
        assert 'Canción de catálogo iOS 27' in window.now_title.text()
        for choice,dark in [(2,True),(1,False),(0,False)]:
            window.theme_choice.setCurrentIndex(choice)
            if choice:
                assert window.theme_dark == dark
        # Exercise transfer controls and the real Qt worker/lock/signals, while
        # the protocol itself is replayed in test_transfers (never a real phone).
        track = inspect_audio(fixtures/'covered-aac.m4a','covered-aac.m4a')
        track['path'] = str(fixtures/'covered-aac.m4a')
        track['thumbnail'] = thumbnail(read_artwork(fixtures/'covered-aac.m4a'))
        window.accept_track(track)
        window.tabs.setCurrentIndex(0)
        assert window.import_phone.isEnabled()
        window.show_library([{'id':'synthetic','title':'USB audio','artist':'Prueba','album':'Prueba',
                             'duration':1,'afc_path':'iTunes_Control/Music/F00/AAAA.m4a'}])
        window.tabs.setCurrentIndex(1)
        window.library_table.selectRow(0)
        assert window.export_phone.isEnabled()
        original_transfer = globals()['run_transfer']
        original_backup = window.backup_root
        def simulated_transfer(mode, selected, destination, progress):
            assert mode == 'export' and selected[0]['afc_path'].endswith('.m4a')
            progress(1,2,'Transferencia de prueba',track['id'])
            return {'exported':1,'files':[]}
        try:
            globals()['run_transfer'] = simulated_transfer
            window.backup_root = folder/'synthetic-backups'
            window.start_transfer('export',list(window.library_model.tracks),folder)
            assert not window.import_phone.isEnabled() and not window.export_phone.isEnabled()
            deadline = time.monotonic()+10
            while window.transfer_worker is not None:
                app.processEvents()
                if time.monotonic() > deadline:
                    raise RuntimeError('Transfer worker did not finish')
                time.sleep(0.005)
            assert '1 archivos exportados' in window.status.text()
            assert window.progress_track_id == track['id']
            assert not window.now_cover.pixmap().isNull()
        finally:
            globals()['run_transfer'] = original_transfer
            window.backup_root = original_backup
        window.show_library_error('Error de prueba\nDiagnóstico: usb:ConnectionRefusedError')
        window.device_status.setText('Otro estado de prueba')
        window.copy_diagnostic.click()
        assert QApplication.clipboard().text() == 'Error de prueba\nDiagnóstico: usb:ConnectionRefusedError'


def main():
    parser = argparse.ArgumentParser(description='TUPAQ: aplicación de escritorio')
    parser.add_argument('--smoke-fixtures', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-report', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-screenshot', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName('TUPAQ')
    app.setOrganizationName('TUPAQ')
    window = Window(auto_connect=not bool(args.smoke_fixtures))
    window.show()
    if args.smoke_fixtures:
        smoke(app, window, args.smoke_fixtures, args.smoke_screenshot)
        if args.smoke_report:
            args.smoke_report.write_text('native-ui-smoke-passed', encoding='ascii')
        return
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
