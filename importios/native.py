"""Native desktop interface for local preparation and USB audio transfers."""
import argparse
import csv
import json
from contextlib import closing
import plistlib
from pathlib import Path
import re
import sys
import sqlite3
import tempfile
import time
import asyncio
import threading

from PySide6.QtCore import Qt, QThread, Signal, QSize, QStandardPaths, QLockFile, QUrl, QTimer, QSettings, QPoint, QItemSelectionModel
from PySide6.QtGui import QIcon, QPixmap, QDesktopServices, QShortcut, QKeySequence
from PySide6.QtWidgets import QApplication,QFileDialog,QMainWindow,QMessageBox,QAbstractItemView,QDialog,QVBoxLayout,QScrollArea,QLabel,QPlainTextEdit

from .i18n import tr, set_language, language, LANGUAGES, QMessageBox
from .audio import inspect_audio, read_artwork
from .artwork import thumbnail, image_info, preview_image, PREVIEW_BYTES
from .devices import discover, DiscoveryError
from .sync.signing import FixedHostSession
from .library import read_phone_library, read_catalogue, LibraryError, format_diagnostics
from .models import LibraryModel, SortableItem, SORT_ROLE, byte_label, duration_label
from .version import VERSION
from .transfers import run_transfer, TransferError

from .bulk import MAX_SELECTION

MAX_SIZE = 256 * 1024 * 1024


class Reader(QThread):
    track = Signal(dict)
    problem = Signal(str)
    progress = Signal(int, int)

    def __init__(self, paths, parent=None):
        super().__init__(parent)
        self.paths = paths
        self.credits=threading.Semaphore(64)
        self.problem_count=0

    def run(self):
        last_progress=0.
        for index, path in enumerate(self.paths):
            if self.isInterruptionRequested():
                break
            try:
                if not 0 < path.stat().st_size <= MAX_SIZE:
                    raise ValueError('El archivo está vacío o supera los 256 MB.')
                track = inspect_audio(path, path.name)
                track['path'] = str(path.resolve())
                try:
                    track['thumbnail'] = thumbnail(read_artwork(path),64) if index<96 else None
                except (OSError, ValueError):
                    track['thumbnail'] = None
                while not self.credits.acquire(timeout=.1):
                    if self.isInterruptionRequested():return
                if self.isInterruptionRequested():self.credits.release();return
                self.track.emit(track)
            except (OSError, ValueError) as error:
                self.problem_count+=1
                if self.problem_count<=100:self.problem.emit(f'{path.name}: {error}')
            now=time.monotonic()
            if now-last_progress>=.1 or index+1==len(self.paths):
                self.progress.emit(index+1,len(self.paths));last_progress=now
        if self.problem_count>100:self.problem.emit(f'{self.problem_count-100} archivos adicionales no se pudieron preparar.')


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
    details = Signal(int,str,dict)
    preview = Signal(int,dict)

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
            if self.tracks and self.tracks[0].get('_preview') is not None:
                track=self.tracks[0]
                if track.get('path'):
                    import mutagen
                    from .lyrics import embedded_lyrics
                    audio=mutagen.File(track['path'])
                    result=embedded_lyrics(audio.tags if audio is not None else None)
                    data=read_artwork(track['path'],limit=PREVIEW_BYTES)
                    if data and image_info(data):result.update(cover=data,cover_source='embedded',**image_info(data))
                else:
                    from .transfers import device
                    from .remote_artwork import cover_for_track
                    self.loop=asyncio.get_running_loop();self.task=asyncio.current_task()
                    async with device() as (_,afc):
                        result=await asyncio.wait_for(cover_for_track(afc,track,self.isInterruptionRequested,assets=True),timeout=20)
                if not self.isInterruptionRequested():
                    result=result or {'preview_unavailable':True};result['image']=preview_image(result.get('cover'))
                    self.preview.emit(track['_preview'],result)
                return
            from .transfers import device
            from .remote_artwork import cover_for_track
            from .remote_details import audio_details
            self.loop = asyncio.get_running_loop()
            self.task = asyncio.current_task()
            async with device() as (_,afc):
                for track in self.tracks:
                    if self.isInterruptionRequested():
                        break
                    try:
                        if not track.get('usb_details_read'):
                            try:
                                details = await asyncio.wait_for(audio_details(afc,track),timeout=10)
                                if details:self.details.emit(self.epoch,track['id'],details)
                            except Exception:
                                pass
                        result = await asyncio.wait_for(cover_for_track(afc,track,self.isInterruptionRequested,thumbnail_size=224),timeout=10)
                        if result and not self.isInterruptionRequested():
                            self.image.emit(self.epoch,track['id'],result)
                    except Exception:
                        continue
        try:
            asyncio.run(work())
        except (Exception,asyncio.CancelledError):
            if self.tracks and self.tracks[0].get('_preview') is not None and not self.isInterruptionRequested():
                self.preview.emit(self.tracks[0]['_preview'],{'preview_unavailable':True})
        finally:
            self.loop = self.task = None


class TransferWorker(QThread):
    result = Signal(dict)
    problem = Signal(str)
    progress = Signal(int,int,str,str)

    def __init__(self, mode, selected, destination, lock_path, parent=None):
        super().__init__(parent)
        self.mode, self.selected, self.destination, self.lock_path = mode, selected, destination, lock_path
        from .cancellation import TransferControl
        self.control=TransferControl()

    def cancel(self):return self.control.request()

    def run(self):
        lock = QLockFile(str(self.lock_path))
        if not lock.tryLock(0):
            self.problem.emit('Hay otra transferencia de TUPAQ en curso.\nDiagnóstico: transfer:busy')
            return
        try:
            def report(value,total,label,identifier=''):
                self.progress.emit(value,total,label,identifier)
            report.control=self.control
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
        screen=QApplication.primaryScreen()
        area=screen.availableGeometry() if screen else None
        self.setMinimumSize(1080,680)
        self.resize(min(1500,area.width()-48) if area else 1500,min(880,area.height()-70) if area else 880)
        self.setAcceptDrops(True)
        self.tracks = {}
        self.worker = None
        self.device_worker = None
        self.library_worker = None
        self.transfer_worker = None
        self.transfer_outcome = None
        self.transfer_diagnostic = ''
        self.progress_track_id = None
        self.backup_root = Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))/'catalogue-backups'
        self.background_enabled = auto_connect
        self.thumbnail_worker = None
        self.after_artwork = None
        self.preview_pending=None;self.preview_key=None;self.preview_result={};self.preview_generation=0;self.closing=False
        self.connection_token = None
        self.connection_generation=0
        self.library_ready = False
        self.phone_tracks = []
        self.retry_library_at = 0
        self.library_epoch = 0
        self.artwork_attempted = set()
        self.duplicates = 0
        self.activity_message=''
        saved_language=QSettings().value('language','es') if auto_connect else 'es'
        set_language(saved_language)
        from .typography import configure
        app=QApplication.instance()
        configure(app)
        self.setFont(app.font())
        from .motion import MotionController
        reduced=QSettings().value('reduce_motion',False,type=bool) if auto_connect else False
        self.motion=MotionController(self,enabled=not reduced)
        from .interface import build, apply_theme
        build(self)
        self.language_choice.setCurrentIndex(self.language_choice.findData(language()))
        self.language_choice.currentIndexChanged.connect(self.change_language)
        QShortcut(QKeySequence.StandardKey.Find,self,activated=self.focus_search)
        QShortcut(QKeySequence.StandardKey.Open,self,activated=self.choose_files)
        self.persist_settings = auto_connect
        if self.persist_settings:
            settings = QSettings()
            choice=int(settings.value('appearance',2))
            if settings.value('design_version','')!='tonal-19':settings.setValue('glass_mood',3)
            settings.setValue('design_version','tonal-19')
            settings.setValue('appearance',choice)
            self.theme_choice.setCurrentIndex(choice)
            self.mood_choice.blockSignals(True);self.mood_choice.setCurrentIndex(int(settings.value('glass_mood',3)));self.mood_choice.blockSignals(False)
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
        self.refresh_workspace()
        self.nav_buttons[0].setChecked(True)
        self.change_theme()
        self.library_empty.refresh()
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
        self.import_phone.setEnabled(not phone_busy and bool(self.tracks))
        selected=self.marked_tracks()
        self.export_phone.setEnabled(not phone_busy and bool(selected) and all(t.get('afc_path') for t in selected[:100]))
        self.delete_phone.setEnabled(not phone_busy and bool(selected))
        self.verify_import.setEnabled(not phone_busy and self.backup_root.exists())
        self.resume_import.setEnabled(not phone_busy and self.backup_root.exists())
        self.repair_metadata.setEnabled(not phone_busy and self.backup_root.exists())
        self.open_backup.setEnabled(self.backup_root.exists())
        self.queue_toggle.setVisible(bool(self.tracks) or self.worker is not None)
        self.queue_toggle.setText(tr(f'Cola ({len(self.tracks)})'))
        self.queue_panel.setVisible((bool(self.tracks) or self.worker is not None) and self.queue_toggle.isChecked())
        self.queue_panel.setMinimumHeight(min(210,100+44*len(self.tracks)) if self.tracks else 110)

    def navigate(self, number):
        self.motion.navigate(self.pages,1 if number == 1 else 0)
        self.nav_buttons[1 if number == 1 else 0].setChecked(True)
        self.update_buttons()
        self.schedule_artwork()
        self.library_empty.refresh()

    def focus_search(self):
        self.navigate(0);self.search.setFocus()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'drop_veil') and self.drop_veil.isVisible():self.drop_veil.reveal()
        if hasattr(self,'transfer_actions'):
            from .interface import layout_transfer_actions
            layout_transfer_actions(self)

    def change_language(self, *ignored):
        code=self.language_choice.currentData()
        set_language(code,self)
        self.library_model.headerDataChanged.emit(Qt.Orientation.Horizontal,0,5)
        sorting=self.table.isSortingEnabled();self.table.setSortingEnabled(False)
        try:
            for row in range(self.table.rowCount()):
                for column in range(self.table.columnCount()):
                    self.table.item(row,column).retranslate()
        finally:self.table.setSortingEnabled(sorting)
        if hasattr(self,'preview_track'):self.request_preview(self.preview_track)
        self.library_empty.refresh()
        if self.persist_settings:QSettings().setValue('language',language())

    def refresh_workspace(self):
        self.update_buttons()
        self.schedule_artwork()

    def filter_library(self, *ignored):
        from .library_fields import local_tracks
        self.library_epoch += 1
        self.artwork_attempted.clear()
        if self.thumbnail_worker is not None and not (self.thumbnail_worker.tracks and self.thumbnail_worker.tracks[0].get('_preview') is not None):
            self.thumbnail_worker.stop()
        local = local_tracks(self.phone_tracks)
        known = any('is_local' in track for track in self.phone_tracks)
        displayed=local
        text=self.search.text().strip().casefold()
        if text:
            from .search import matches
            displayed=[track for track in displayed if matches(track,text)]
        view=self.library_table
        selected={self.library_model.tracks[i.row()]['id'] for i in view.selectionModel().selectedRows()}
        current=view.currentIndex();current_id=self.library_model.tracks[current.row()]['id'] if current.isValid() else None
        scroll=view.verticalScrollBar().value()
        first=view.indexAt(QPoint(4,4))
        top_id=self.library_model.tracks[first.row()]['id'] if first.isValid() else None
        view.setUpdatesEnabled(False)
        self.library_model.replace(displayed,preserve_icons=bool(self.phone_tracks))
        self.library_empty.refresh()
        selection=view.selectionModel()
        for identifier in selected:
            row=self.library_model.rows.get(identifier)
            if row is not None:selection.select(self.library_model.index(row,0),QItemSelectionModel.SelectionFlag.Select|QItemSelectionModel.SelectionFlag.Rows)
        if current_id in self.library_model.rows:
            selection.setCurrentIndex(self.library_model.index(self.library_model.rows[current_id],0),QItemSelectionModel.SelectionFlag.NoUpdate)
        if top_id in self.library_model.rows:
            view.scrollTo(self.library_model.index(self.library_model.rows[top_id],0),QAbstractItemView.ScrollHint.PositionAtTop)
        else:view.verticalScrollBar().setValue(scroll)
        view.setUpdatesEnabled(True);view.viewport().update()
        title = 'En el iPhone'
        self.library_heading.setText(tr(f'{title} · {len(displayed)}'))
        if self.worker is None and self.transfer_worker is None and not self.activity_message:
            self.status.setText(tr(f"{len(local)} {'canciones' if known else 'canciones disponibles'} · {len(self.tracks)} para importar"))
        if not self.library_table.selectionModel().selectedRows() and not self.table.selectionModel().selectedRows() and self.transfer_worker is None:self.clear_inspector()
        self.library_selection_changed()
        self.update_library_summary()
        self.checks_changed()
        self.update_buttons()
        self.schedule_artwork()

    def update_library_summary(self):
        from .library_fields import local_tracks
        local=local_tracks(self.phone_tracks)
        missing=sum(track.get('usb_exists') is False for track in self.phone_tracks)
        self.device_metric.setText(tr(f'{len(local)} canciones') if self.connection_token is not None or self.phone_tracks else tr('Tu biblioteca por USB'))
        text=f'{len(local)} canciones en el iPhone'
        self.device_status.setText(tr(text if self.phone_tracks else 'Conecta tu iPhone para mostrar su música.'))

    def change_motion(self,reduced):
        self.motion.set_enabled(not reduced)
        if self.persist_settings:QSettings().setValue('reduce_motion',bool(reduced))

    def change_mood(self,*ignored):
        from .interface import apply_theme
        apply_theme(self)
        if getattr(self,'persist_settings',False):QSettings().setValue('glass_mood',self.mood_choice.currentIndex())

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

    def set_connection_status(self,connected,message):
        self.connection_dot.setProperty('connected',bool(connected))
        self.connection_dot.style().unpolish(self.connection_dot);self.connection_dot.style().polish(self.connection_dot);self.connection_dot.update()
        self.connection_badge.setText(tr(message))

    def devices_found(self, devices):
        if len(devices) != 1:
            self.connection_generation+=1
            self.connection_token = None
            self.library_ready = False
            self.library_epoch += 1
            self.phone_tracks = []
            self.library_model.checked.clear()
            self.filter_library()
            self.artwork_attempted.clear()
            self.device_name.setText('iPhone')
            self.set_connection_status(False,'Sin conexión USB' if not devices else 'Conecta un solo iPhone')
            self.device_status.setVisible(bool(devices))
            self.device_status.setText(tr('Conecta tu iPhone. Su biblioteca aparecerá automáticamente.' if not devices else 'Se detectó más de un dispositivo Apple. Conecta un solo iPhone para continuar.'))
            return
        token = devices[0].get('token','usb')
        changed = token != self.connection_token
        if changed:
            self.connection_generation+=1
            self.connection_token = token
            self.library_ready = False
            self.retry_library_at = 0
            self.library_epoch += 1
            self.phone_tracks = []
            self.library_model.checked.clear()
            self.filter_library()
            self.artwork_attempted.clear()
        self.set_connection_status(True,'Conectado por USB')
        if not self.library_ready and time.monotonic() >= self.retry_library_at:
            self.load_library(automatic=True)

    def device_problem(self, message):
        self.device_status.show()
        self.connection_generation+=1
        self.connection_token = None
        self.library_ready = False
        self.library_epoch += 1
        self.phone_tracks = []
        self.library_model.checked.clear()
        self.filter_library()
        self.artwork_attempted.clear()
        self.set_connection_status(False,'Servicio USB no disponible')
        if self.connection_token is None:
            self.device_status.setText(tr(message))

    def schedule_artwork(self, *ignored):
        if self.closing:return
        if self.preview_pending is not None and hasattr(self,'artwork_timer'):
            self.artwork_timer.start(0)
        elif self.background_enabled and hasattr(self,'artwork_timer'):
            self.artwork_timer.start(180)

    def fetch_visible_artwork(self):
        if (self.thumbnail_worker is not None or self.library_worker is not None or self.transfer_worker is not None or self.device_worker is not None
            or self.after_artwork is not None or self.pages.currentIndex() != 0):
            return
        if self.preview_pending is not None:
            track,self.preview_pending=self.preview_pending,None
            self.thumbnail_worker=ArtworkReader([track],self.library_epoch,self)
            self.thumbnail_worker.preview.connect(self.preview_ready)
            self.thumbnail_worker.finished.connect(self.artwork_finished)
            self.thumbnail_worker.start()
            return
        if not self.background_enabled:return
        first = self.library_table.indexAt(QPoint(1,1)).row()
        first = max(first,0)
        count = min(32,max(1,self.library_table.viewport().height()//56+3))
        wanted = [dict(track) for track in self.library_model.tracks[first:first+count]
            if track['id'] not in self.artwork_attempted and (track['id'] not in self.library_model.icons or not track.get('usb_details_read'))
            and (track.get('artwork_paths') or track.get('afc_path'))]
        if not wanted:
            return
        if len(self.artwork_attempted)>4096:
            self.artwork_attempted.clear()
        self.artwork_attempted.update(track['id'] for track in wanted)
        self.thumbnail_worker = ArtworkReader(wanted,self.library_epoch,self)
        self.thumbnail_worker.image.connect(self.phone_artwork_ready)
        self.thumbnail_worker.details.connect(self.phone_details_ready)
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

    def phone_details_ready(self, epoch, identifier, details):
        if epoch == self.library_epoch:
            self.library_model.set_details(identifier,details)
            if details.get('usb_exists') is False:self.filter_library()
            else:self.library_selection_changed()

    def library_selection_changed(self, *ignored):
        self.update_buttons()
        rows = self.library_table.selectionModel().selectedRows()
        if not rows:
            return
        track = self.library_model.tracks[rows[0].row()]
        self.show_track_details(track,'En el iPhone')

    def local_selection_changed(self):
        self.update_buttons()
        rows=self.table.selectionModel().selectedRows()
        if rows:
            identifier=self.table.item(rows[0].row(),0).data(Qt.ItemDataRole.UserRole)
            if identifier in self.tracks:self.show_track_details(self.tracks[identifier],'Para importar')

    def clear_inspector(self):
        self.preview_generation+=1;self.preview_key=None;self.preview_result={};self.preview_pending=None
        self.cover_metadata.setText('—');self.view_cover.setEnabled(False);self.view_lyrics.setEnabled(False);self.lyrics_status.setText(tr('No se ha detectado letra'))
        self.now_cover.setPixmap(QPixmap());self.now_cover.setText('♪')
        self.now_title.setText(tr('Tu música, siempre contigo.'));self.info_artist.setText(tr('Selecciona una canción para ver sus detalles.'));self.info_origin.setText(tr('TU COLECCIÓN'))
        for value in self.info_fields.values():value.setText('—')
        for value in self.inspector_details:value.hide()

    def show_track_details(self,track,origin):
        for value in self.inspector_details:value.show()
        self.now_title.setText(track.get('title') or tr('Sin título'));self.info_artist.setText(track.get('artist') or tr('Sin artista'))
        self.info_origin.setText(tr(origin.upper()))
        fmt=track.get('format_label') or (f"M4A · {track['format']}" if track.get('container')=='M4A' else track.get('format'))
        rate=track.get('sample_rate');bits=track.get('bit_depth');bitrate=track.get('bit_rate')
        quality=[]
        if type(bits) in (int,float) and 0<bits<=64:quality.append(f'{bits:g} bits')
        if type(rate) in (int,float) and 1000<=rate<=768000:quality.append(f'{rate/1000:g} kHz')
        values={'album':track.get('album') or tr('Sin álbum'),'format':fmt or '—','duration':duration_label(track.get('duration')),
                'quality':' · '.join(quality) or '—','bitrate':f'{bitrate:g} kbps' if type(bitrate) in (int,float) and 0<bitrate<10**7 else '—',
                'genre':track.get('genre') or '—','year':str(track.get('year') or '—'),
                'size':byte_label(track.get('size')),'availability':'Original del ordenador' if track.get('path') else
                'Disponible por USB' if track.get('afc_path') and track.get('usb_exists') is not False else 'Sin acceso USB'}
        for key,value in values.items():
            if key in self.info_fields:self.info_fields[key].setText(value)
        if self.preview_result.get('image') is not None and self.preview_key==self.preview_identity(track):
            self.request_preview(track);return
        image=QPixmap()
        if track.get('thumbnail'):image.loadFromData(track['thumbnail'])
        icon=self.library_model.icons.get(track.get('id'),self.default_music_icon)
        from .visuals import rounded_cover
        self.now_cover.setPixmap(rounded_cover(image if not image.isNull() else icon.pixmap(224,224),224))
        self.request_preview(track)

    def preview_identity(self,track):
        return ('local',track.get('id'),track.get('path')) if track.get('path') else ('phone',self.connection_token,track.get('id'),self.library_model.cover_key(track))

    def request_preview(self,track):
        from .lyrics import label
        self.preview_track=track
        key=self.preview_identity(track)
        if key!=self.preview_key:
            self.preview_key=key;self.preview_generation+=1;self.preview_result={}
            self.cover_metadata.setText(tr('Leyendo carátula original…'));self.view_cover.setEnabled(False);self.view_lyrics.setEnabled(False)
            self.preview_pending={**track,'_preview':self.preview_generation} if track.get('path') or self.background_enabled else None
            if self.thumbnail_worker is not None:self.thumbnail_worker.stop()
            self.schedule_artwork()
        self.lyrics_status.setText(('♫  ' if any(track.get(k) for k in ('lyrics_embedded','lyrics_registered','lyrics_online_available')) else '')+label(track))
        self.render_preview()

    def preview_ready(self,generation,result):
        if generation!=self.preview_generation:return
        self.preview_result=result
        self.preview_track.update({key:value for key,value in result.items() if key.startswith('lyrics_') and key!='lyrics_text'})
        identifier=self.preview_track.get('id')
        if not self.preview_track.get('path'):
            self.library_model.set_details(identifier,{key:value for key,value in self.preview_track.items() if key.startswith('lyrics_')})
        from .lyrics import label
        self.lyrics_status.setText(('♫  ' if any(self.preview_track.get(k) for k in ('lyrics_embedded','lyrics_registered','lyrics_online_available')) else '')+label(self.preview_track))
        self.render_preview()

    def render_preview(self):
        result=self.preview_result;image=result.get('image')
        if image is not None and not image.isNull():
            ratio=self.devicePixelRatioF();key=f'{image.cacheKey()}:{ratio}'
            if self.now_cover.property('previewImageKey')!=key or self.now_cover.pixmap().isNull():
                pixmap=QPixmap.fromImage(image).scaled(round(224*ratio),round(224*ratio),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                pixmap.setDevicePixelRatio(ratio);self.now_cover.setPixmap(pixmap);self.now_cover.setProperty('previewImageKey',key)
            self.cover_metadata.setText(f"{result['cover_width']} × {result['cover_height']} px · {byte_label(result['cover_bytes'])} · {result['cover_format']}")
        elif result:self.cover_metadata.setText(tr('Sin carátula original accesible'))
        self.view_cover.setEnabled(bool(result.get('cover')))
        self.view_lyrics.setEnabled(bool(result.get('lyrics_text')))

    def open_cover(self):
        image=preview_image(self.preview_result.get('cover'),original=True)
        if image is None:return
        dialog=QDialog(self);dialog.setWindowTitle(tr('Carátula original · 100%'));dialog.resize(760,700)
        layout=QVBoxLayout(dialog);metadata=QLabel(self.cover_metadata.text());layout.addWidget(metadata)
        scroll=QScrollArea();label=QLabel();pixmap=QPixmap.fromImage(image);pixmap.setDevicePixelRatio(self.devicePixelRatioF());label.setPixmap(pixmap);label.setFixedSize(pixmap.deviceIndependentSize().toSize());scroll.setWidget(label);layout.addWidget(scroll);dialog.exec()

    def open_lyrics(self):
        text=self.preview_result.get('lyrics_text')
        if not text:return
        dialog=QDialog(self);dialog.setWindowTitle(tr('Letra incluida en el archivo'));dialog.resize(580,640)
        layout=QVBoxLayout(dialog);notice=QLabel(tr('Conservar la letra dentro del archivo no garantiza que Música del iPhone la muestre.'));notice.setWordWrap(True);layout.addWidget(notice)
        editor=QPlainTextEdit();editor.setReadOnly(True);editor.setPlainText(text);layout.addWidget(editor);dialog.exec()

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

    def marked_tracks(self):
        from .library_fields import local_tracks
        return [dict(track) for track in local_tracks(self.phone_tracks) if track['id'] in self.library_model.checked]

    def checks_changed(self):
        count=len(self.marked_tracks());self.selection_count.setText(tr(f'{count} seleccionadas' if count else ''))
        visible={track['id'] for track in self.library_model.tracks};checked=visible & self.library_model.checked
        self.select_visible.blockSignals(True)
        self.select_visible.setCheckState(Qt.CheckState.Checked if visible and checked==visible else Qt.CheckState.PartiallyChecked if checked else Qt.CheckState.Unchecked)
        self.select_visible.blockSignals(False);self.update_buttons()

    def delete_songs(self):
        selected=self.marked_tracks()
        if not selected:return
        if len(selected)>MAX_SELECTION:
            QMessageBox.information(self,tr('Selección demasiado grande'),tr('Puedes procesar hasta 50.000 canciones por operación.'));return
        dialog=QMessageBox(self);dialog.setWindowTitle(tr('Eliminar del iPhone'))
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(tr(f"¿Eliminar {len(selected)} canciones de la biblioteca de Música del iPhone?"))
        dialog.setInformativeText(tr('Esta acción elimina las canciones del iPhone. Conserva los audios que quieras guardar en el ordenador. La copia del catálogo no permite recuperar por sí sola los audios.')+'\n\n'+'\n'.join(t['title'] for t in selected[:5]))
        dialog.setStandardButtons(QMessageBox.StandardButton.Cancel|QMessageBox.StandardButton.Yes)
        dialog.setDetailedText('\n'.join(f"{t['title']} — {t.get('artist','Sin artista')}" for t in selected[:100]))
        dialog.button(QMessageBox.StandardButton.Cancel).setText(tr('Cancelar'))
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel);dialog.button(QMessageBox.StandardButton.Yes).setText(tr('Eliminar canciones'))
        if dialog.exec()==QMessageBox.StandardButton.Yes:self.start_transfer('delete',selected,self.backup_root)

    def export_songs(self):
        selected=self.marked_tracks()
        if not selected:
            return
        folder = QFileDialog.getExistingDirectory(self,tr('Guardar audio del iPhone en…'))
        if folder:
            self.start_transfer('export',selected,Path(folder))

    def start_transfer(self, mode, selected, destination):
        if self.transfer_worker is not None or self.worker is not None or self.library_worker is not None or self.device_worker is not None:
            return
        if mode == 'import' and not selected:
            return
        if self.thumbnail_worker is not None:
            self.after_artwork = ('transfer',mode,selected,destination)
            self.cancel_transfer_button.setText(tr('Cancelar'));self.cancel_transfer_button.setEnabled(True);self.cancel_transfer_button.setVisible(mode in ('import','export','delete'))
            self.thumbnail_worker.stop()
            self.update_buttons()
            return
        try:
            self.backup_root.parent.mkdir(parents=True,exist_ok=True)
        except OSError:
            self.cancel_transfer_button.hide()
            self.show_library_error('No se pudo preparar la carpeta local de datos de TUPAQ.\nDiagnóstico: transfer:local-folder')
            return
        self.transfer_outcome = None
        self.transfer_diagnostic = ''
        self.activity_message=''
        self.progress_track_id = None
        self.transfer_worker = TransferWorker(mode,selected,destination,self.backup_root.parent/'transfer.lock',self)
        self.transfer_worker.progress.connect(self.transfer_progress)
        self.transfer_worker.result.connect(self.transfer_result)
        self.transfer_worker.problem.connect(self.transfer_problem)
        self.transfer_worker.finished.connect(self.transfer_finished)
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        self.progress.show()
        self.cancel_transfer_button.setText(tr('Cancelar'));self.cancel_transfer_button.setEnabled(True)
        self.cancel_transfer_button.setVisible(mode in ('import','export','delete'))
        self.status.setText(tr('Preparando transferencia…'))
        self.update_buttons()
        self.transfer_worker.start()

    def cancel_transfer(self):
        worker=self.transfer_worker
        if worker is None:
            if self.after_artwork and self.after_artwork[0]=='transfer' and self.after_artwork[1] in ('import','export','delete'):
                self.after_artwork=None;self.cancel_transfer_button.hide();self.status.setText(tr('Operación cancelada antes de iniciar el envío.'));self.update_buttons()
            return
        if worker.mode not in ('import','export','delete'):return
        immediate=worker.cancel()
        self.cancel_transfer_button.setEnabled(False)
        self.cancel_transfer_button.setText(tr('Cancelando…' if immediate else 'Finalizando…'))
        self.status.setText(tr('Cancelando la operación…' if immediate else 'El envío de cambios ya comenzó. Se finalizará este lote para no dejar canciones incompletas.'))

    def transfer_progress(self, value, total, label, identifier=''):
        self.progress.setRange(0,max(1,total))
        self.progress.setValue(value)
        control=self.transfer_worker.control if self.transfer_worker is not None else None
        if not (control and control.event.is_set()):self.status.setText(tr(label))
        if identifier and identifier != self.progress_track_id and identifier in self.tracks:
            self.progress_track_id = identifier
            track = self.tracks[identifier]
            self.show_track_details(track,'Importando')

    def transfer_problem(self, message):
        self.transfer_diagnostic=message
        self.show_library_error(message)
        self.status.setText(tr('Transferencia detenida. Consulta el diagnóstico antes de repetirla.'))
        self.activity_message=self.status.text()

    def transfer_result(self, result):
        self.transfer_outcome = result
        if result.get('bulk') and (result.get('cancelled') or result.get('bulk_stopped')):
            self.status.setText(tr(f"Operación detenida: {result['processed']} de {result['requested']} canciones comprobadas."))
            if result.get('diagnostic'):
                self.transfer_diagnostic=f"TUPAQ {VERSION}\nDiagnóstico: {result['diagnostic']}\nLotes comprobados: {result['batches_completed']}"
                self.last_diagnostic=self.transfer_diagnostic;self.copy_diagnostic.setEnabled(True)
        elif result.get('cancelled'):
            self.status.setText(tr(f"Exportación cancelada. Se conservaron {result.get('exported',0)} archivos completos." if 'exported' in result else 'Importación cancelada antes de enviar cambios a Música.'))
        elif 'deleted' in result:
            self.status.setText(tr(f"{result['deleted']} canciones eliminadas de la biblioteca."))
            self.library_model.checked.difference_update(result.get('item_ids',[]))
        elif 'exported' in result:
            self.status.setText(tr(f"{result['exported']} archivos exportados y comprobados."))
        elif 'reconciled' in result and 'imported' not in result:
            self.status.setText(tr(f"{result.get('verified',0)} audios comprobados · {result.get('metadata_unverified',0)} con metadatos por revisar · {result.get('retired',0)} retirados por el iPhone · {result.get('removed',0)} eliminaciones comprobadas"))
        elif 'updated' in result:
            self.status.setText(tr(f"{result['updated']} canciones actualizadas · {result['covers']} portadas comprobadas."))
        else:
            count = result.get('imported',result.get('verified',0))
            skipped = result.get('already_imported',0)
            self.status.setText(tr(f'{count} canciones importadas y comprobadas. Ya importadas: {skipped}. Copia del catálogo en Ver respaldo.'))

        if result.get('cancel_deferred'):self.status.setText(tr('El lote ya enviado se completó y verificó. La solicitud de cancelación llegó después de iniciar los cambios en Música.'))
        if result.get('metadata_unverified') and 'imported' in result:
            self.status.setText(tr(f"Audios comprobados. {result['metadata_unverified']} canciones conservan metadatos pendientes de revisión."))
        if result.get('metadata_unverified'):
            self.transfer_diagnostic=f'TUPAQ {VERSION}\nDiagnóstico: metadata:unverified\nDatos del protocolo: '+json.dumps(result.get('metadata_diagnostics',[]),sort_keys=True)
            self.last_diagnostic=self.transfer_diagnostic;self.copy_diagnostic.setEnabled(True)
        self.activity_message=self.status.text()

    def transfer_finished(self):
        worker = self.transfer_worker
        self.transfer_worker = None
        worker.deleteLater()
        self.progress.hide();self.cancel_transfer_button.hide()
        if self.transfer_outcome:
            completed = set(self.transfer_outcome.get('source_ids',[]))
            for row in range(self.table.rowCount()-1,-1,-1):
                identifier = self.table.item(row,0).data(Qt.ItemDataRole.UserRole)
                if identifier in completed:
                    self.tracks.pop(identifier,None)
                    self.table.removeRow(row)
        self.update_buttons()
        if self.transfer_outcome and any(key in self.transfer_outcome for key in ('imported','verified','updated','deleted')):
            self.load_library()

    def choose_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, tr('Elegir canciones'), '',
            tr('Audio (*.mp3 *.wav *.m4a *.alac *.aif *.aiff);;Todos los archivos (*)'))
        self.add_paths(paths)

    def check_device(self, automatic=False):
        if self.device_worker is not None or self.transfer_worker is not None or self.library_worker is not None or self.after_artwork is not None:
            return
        self.device_button.setEnabled(False)
        if not automatic:
            self.device_status.setText(tr('Consultando el servicio local de Apple…'))
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
        self.schedule_artwork()

    def current_library_result(self):
        worker=self.sender()
        return worker is not None and worker is self.library_worker and worker.connection_generation==self.connection_generation

    def accept_library_result(self,tracks,diagnostic):
        if self.current_library_result():self.show_library(tracks,diagnostic)

    def accept_library_problem(self,message):
        if self.current_library_result():self.library_problem(message)

    def accept_library_name(self,name):
        if self.current_library_result():self.device_name.setText(name)

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
        if not self.phone_tracks:self.library_heading.setText(tr('En el iPhone · leyendo…'))
        self.library_button.setEnabled(False)
        self.copy_diagnostic.setEnabled(False)
        if not self.phone_tracks and (not automatic or (not self.tracks and self.pages.currentIndex() == 0)):
            self.navigate(0)
        self.device_status.show()
        self.device_status.setText(tr('Actualizando biblioteca… Puedes seguir viendo tus canciones.' if self.phone_tracks else 'Leyendo la biblioteca del iPhone…'))
        self.library_worker = LibraryReader(self)
        self.library_worker.connection_generation=self.connection_generation
        self.library_worker.result.connect(self.accept_library_result)
        self.library_worker.problem.connect(self.accept_library_problem)
        self.library_worker.name.connect(self.accept_library_name)
        self.library_worker.finished.connect(self.library_finished)
        self.update_buttons()
        self.library_empty.refresh()
        self.library_worker.start()

    def show_library(self, tracks, diagnostic=''):
        previous={track['id']:track for track in self.phone_tracks}
        for track in tracks:
            old=previous.get(track['id'])
            if old and self.library_model.cover_key(old)==self.library_model.cover_key(track):
                if not track.get('duration') and old.get('duration',0)>0:track['duration']=old['duration']
        self.phone_tracks = tracks
        from .library_fields import local_tracks
        self.library_model.checked.intersection_update(t['id'] for t in local_tracks(tracks))
        self.filter_library()
        self.device_status.setVisible(not bool(tracks))
        self.last_diagnostic = self.transfer_diagnostic or diagnostic or format_diagnostics({'tracks_returned': len(tracks)})
        self.copy_diagnostic.setEnabled(True)
        self.library_ready = True
        self.retry_library_at = 0
        self.set_connection_status(True,'Conectado por USB')
        self.update_library_summary()
        if not tracks:self.device_status.setText(tr('No se encontraron canciones. Esto no confirma que Música esté vacía. Copia el diagnóstico.'))
        self.update_buttons()
        self.schedule_artwork()

    def library_problem(self, message):
        self.device_status.show()
        self.library_ready = False
        self.retry_library_at = time.monotonic()+20
        self.show_library_error(message)
        if self.phone_tracks:self.device_status.setText(tr('No se pudo actualizar. Se mantiene la vista anterior.\n'+message))

    def show_library_error(self, message):
        self.last_diagnostic = message
        self.device_status.setText(tr(message))
        self.copy_diagnostic.setEnabled(True)

    def library_finished(self):
        worker = self.library_worker
        self.library_worker = None
        if worker is not None:
            worker.deleteLater()
        self.library_button.setEnabled(True)
        self.update_buttons()
        self.library_empty.refresh()
        self.schedule_artwork()

    def add_paths(self, paths):
        if len(paths)+len(self.tracks)>MAX_SELECTION:
            QMessageBox.information(self,tr('Selección demasiado grande'),tr('Puedes procesar hasta 50.000 canciones por operación.'));return
        if self.worker is not None or self.transfer_worker is not None or not paths:
            return
        self.errors.clear()
        self.navigate(0)
        self.errors.hide()
        self.duplicates = 0
        self.progress.setRange(0, len(paths))
        self.progress.setValue(0)
        self.progress.show()
        self.status.setText(tr('Revisando canciones…'))
        self.worker = Reader([Path(path) for path in paths], self)
        self.worker.track.connect(self.accept_reader_track)
        self.worker.problem.connect(self.show_problem)
        self.worker.progress.connect(self.preparation_progress)
        self.worker.finished.connect(self.read_finished)
        self.update_buttons()
        self.worker.start()

    def preparation_progress(self,value,total):
        self.progress.setValue(value);self.status.setText(tr(f'Preparando {value} de {total} canciones…'))

    def accept_reader_track(self,track):
        worker=self.sender()
        try:self.accept_track(track)
        finally:worker.credits.release()

    def accept_track(self, track):
        if track['id'] in self.tracks:
            self.duplicates += 1
            return
        self.tracks[track['id']] = track
        picture=QPixmap()
        if track.get('thumbnail'):picture.loadFromData(track['thumbnail'])
        if not self.table.rowCount() or self.worker is None:self.show_track_details(track,'Para importar')
        sorting = self.table.isSortingEnabled()
        self.table.setSortingEnabled(False)
        row = self.table.rowCount()
        self.table.insertRow(row)
        values = [track['title'], track['artist'] or tr('Sin artista'), track['album'] or tr('Sin álbum'),
                  (f"M4A · {track['format']}" if track.get('container') == 'M4A' else track['format']), duration_label(track.get('duration')), byte_label(track['size'])]
        for column, value in enumerate(values):
            item = SortableItem(value)
            if column == 4:item.setData(SORT_ROLE,track['duration'])
            elif column == 5:item.setData(SORT_ROLE,track['size'])
            if column == 0:
                item.setData(Qt.ItemDataRole.UserRole, track['id'])
                from .lyrics import state,label
                from .models import LYRICS_ROLE
                item.setData(LYRICS_ROLE,state(track));item.setToolTip(track['filename']+'\n'+label(track))
                if not picture.isNull():
                    item.setIcon(QIcon(picture))
                else:
                    item.setIcon(self.default_music_icon)
            self.table.setItem(row, column, item)
        self.table.setRowHeight(row, 44)
        self.table.setSortingEnabled(sorting and self.worker is None)

    def show_problem(self, message):
        self.errors.addItem(tr(message))
        self.errors.show()

    def read_finished(self):
        self.table.setSortingEnabled(True)
        worker = self.worker
        self.worker = None
        if worker is not None:
            worker.deleteLater()
        self.progress.hide()
        failed=getattr(worker,'problem_count',self.errors.count()) if worker is not None else self.errors.count()
        self.status.setText(tr(f'{len(self.tracks)} para importar · Duplicadas omitidas: {self.duplicates}'
                            f' · No añadidas: {failed}'))
        self.update_buttons()

    def remove_selection(self):
        self.activity_message=''
        for row in sorted({index.row() for index in self.table.selectionModel().selectedRows()}, reverse=True):
            self.tracks.pop(self.table.item(row, 0).data(Qt.ItemDataRole.UserRole))
            self.table.removeRow(row)
        self.status.setText(tr(f'{len(self.tracks)} para importar. Los archivos originales se conservan.'))
        self.update_buttons()

    def clear_tracks(self):
        self.activity_message=''
        self.clear_inspector()
        self.table.setRowCount(0)
        self.tracks.clear()
        self.errors.clear()
        self.errors.hide()
        self.status.setText(tr('Lista vaciada. Los archivos originales se conservan.'))
        self.update_buttons()

    def export_list(self, path):
        with Path(path).open('w', encoding='utf-8-sig', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow([str(tr(label)) for label in ['Archivo', 'Título', 'Artista', 'Álbum', 'Formato', 'Duración (segundos)', 'Tamaño (bytes)', 'SHA-256']])
            for track in self.tracks.values():
                writer.writerow([csv_value(track[key]) for key in
                    ['filename', 'title', 'artist', 'album', 'format', 'duration', 'size', 'id']])

    def choose_export(self):
        path, _ = QFileDialog.getSaveFileName(self, tr('Guardar lista'), 'tupaq-canciones.csv', tr('CSV (*.csv)'))
        if path:
            try:
                self.export_list(path)
                self.status.setText(tr('Lista guardada.'))
            except OSError:
                QMessageBox.warning(self, tr('No se pudo guardar'), tr('Elige una carpeta donde tengas permiso para escribir.'))

    def dragEnterEvent(self, event):
        if self.worker is None and self.transfer_worker is None and any(url.isLocalFile() for url in event.mimeData().urls()):
            self.drop_veil.reveal();event.acceptProposedAction()
        else:event.ignore()

    def dragLeaveEvent(self,event):
        self.drop_veil.hide();event.accept()

    def dropEvent(self, event):
        self.drop_veil.hide()
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_paths(paths)
        event.acceptProposedAction()

    def closeEvent(self, event):
        if self.transfer_worker is not None:
            self.status.setText(tr('Espera a que termine la transferencia y su comprobación antes de cerrar.'))
            event.ignore()
            return
        if self.library_worker is not None:
            self.device_status.setText(tr('Espera a que termine la lectura de la biblioteca antes de cerrar la ventana.'))
            event.ignore()
            return
        if self.tracks and QMessageBox.question(self, tr('Cerrar TUPAQ'),
            tr('La lista no se conserva al cerrar. ¿Quieres salir?'),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            event.ignore()
            return
        self.motion.set_enabled(False)
        self.closing=True;self.preview_pending=None;self.preview_generation+=1
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
        from .recovery import pending_receipt
        from .sync.protocol import ProtocolError
        try:
            pending_receipt(folder)
            raise AssertionError('Empty folder cannot own a pending import')
        except ProtocolError as error:
            assert str(error) == 'pending-import-count'
        from .sync.artwork import prepare
        picture=prepare(fixtures/'covered-aac.m4a',folder/'prepared-artwork','M4A')
        assert picture and Path(picture['path']).read_bytes().startswith(b'\xff\xd8')
        try:
            run_transfer('repair',[],folder/'unowned',lambda *args:None)
            raise AssertionError('Metadata updates need an owned receipt')
        except TransferError as error:
            assert 'metadata-no-owned-tracks' in error.diagnostic
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
        for column in (0,4,5):
            window.table.sortItems(column,Qt.SortOrder.DescendingOrder)
            identifiers=[]
            for row in range(window.table.rowCount()):
                identifier=window.table.item(row,0).data(Qt.ItemDataRole.UserRole)
                identifiers.append(identifier)
                assert window.table.item(row,0).text()==window.tracks[identifier]['title']
                assert window.table.item(row,5).data(SORT_ROLE)==window.tracks[identifier]['size']
            assert set(identifiers)==set(window.tracks)
        assert {track['format'] for track in window.tracks.values()} == {'MP3', 'WAV', 'AIFF', 'ALAC', 'AAC'}
        covered_row = next(row for row in range(window.table.rowCount()) if window.table.item(row,0).text() == 'M4A con portada')
        assert not window.table.item(covered_row,0).icon().isNull()
        window.table.selectRow(covered_row)
        app.processEvents()
        assert window.now_title.text() == 'M4A con portada'
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
        window.show_library([{'is_local':True,'id': 'test', 'title': 'Canción sintética', 'artist': 'Prueba', 'album': 'Prueba', 'duration': 1}])
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
            rows=read_catalogue(catalogue, diagnostics)
            for row in rows:row['is_local']=True
            return rows
        try:
            globals()['read_phone_library'] = simulated_catalogue
            window.devices_found([{'token':'simulated-attach'}])
            deadline = time.monotonic()+10
            while window.library_worker is not None or window.after_artwork is not None:
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
        assert window.pages.currentIndex() == 0 and window.library_ready
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
        window.navigate(0)
        assert window.import_phone.isEnabled()
        window.show_library([{'id':'synthetic','title':'USB audio','artist':'Prueba','album':'Prueba',
                             'duration':1,'afc_path':'iTunes_Control/Music/F00/AAAA.m4a'}])
        window.navigate(0)
        window.library_table.selectRow(0)
        window.library_model.setData(window.library_model.index(0,0),Qt.CheckState.Checked,Qt.ItemDataRole.CheckStateRole)
        assert window.export_phone.isEnabled()
        original_transfer = globals()['run_transfer']
        original_backup = window.backup_root
        def simulated_transfer(mode, selected, destination, progress):
            if mode == 'export':
                assert selected[0]['afc_path'].endswith('.m4a')
            else:
                assert mode in ('resume','repair') and selected[0]['id'] == track['id']
            progress(1,2,'Transferencia de prueba',track['id'])
            # Return no completion claim in the resume UI smoke: the real
            # verifier is covered by metadata-first transport replay tests.
            if mode in ('resume','repair'):
                return {}
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
            window.backup_root.mkdir()
            window.update_buttons()
            window.navigate(1)
            assert window.resume_import.isEnabled()
            for button in (window.resume_import,window.repair_metadata):
                button.click()
                deadline = time.monotonic()+10
                while window.transfer_worker is not None:
                    app.processEvents()
                    if time.monotonic() > deadline:
                        raise RuntimeError('Maintenance control did not finish')
                    time.sleep(0.005)
        finally:
            globals()['run_transfer'] = original_transfer
            window.backup_root = original_backup
        window.show_library_error('Error de prueba\nDiagnóstico: usb:ConnectionRefusedError')
        window.device_status.setText('Otro estado de prueba')
        window.copy_diagnostic.click()
        assert QApplication.clipboard().text() == 'Error de prueba\nDiagnóstico: usb:ConnectionRefusedError'
        # Exercise the actual frozen translations, not only source-level mocks.
        assert not app._tupaq_qt_translator.isEmpty()
        queued=set(window.tracks);marked=set(window.library_model.checked)
        window.language_choice.setCurrentIndex(1)
        assert window.heading.text()=='Library' and window.nav_buttons[1].text()=='Settings'
        assert window.table.horizontalHeaderItem(0).text()=='Song'
        assert window.library_model.headerData(5,Qt.Orientation.Horizontal)=='Size'
        assert queued==set(window.tracks) and marked==window.library_model.checked
        window.language_choice.setCurrentIndex(0)
        assert window.heading.text()=='Biblioteca' and not app._tupaq_qt_translator.isEmpty()


def main():
    parser = argparse.ArgumentParser(description='TUPAQ: aplicación de escritorio')
    parser.add_argument('--smoke-fixtures', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-report', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--smoke-screenshot', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    app.setApplicationName('TUPAQ')
    app.setOrganizationName('TUPAQ')
    from .visuals import app_icon
    app.setWindowIcon(app_icon())
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
