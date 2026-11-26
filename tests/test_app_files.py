"""Tests for USB app Documents management (house_arrest + installation_proxy) and UI."""
import asyncio
from datetime import datetime
import hashlib
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, MagicMock, create_autospec, patch

from PySide6.QtCore import QEvent, QMimeData, QPointF, Qt, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QMessageBox

from pymobiledevice3.services.afc import AfcFileNotFoundError, AfcService
from pymobiledevice3.services.installation_proxy import InstallationProxyService

from importios.app_files import (
    AppFilesError,
    TEMP_PREFIX,
    create_folder,
    delete_entries,
    documents_path,
    export_entries,
    list_folder,
    list_sharing_apps,
    normalize_relative,
    parent_relative,
    run_app_action,
    upload_paths,
    validate_bundle_id,
    validate_name,
)
from importios.cancellation import CURRENT, TransferControl
from importios.i18n import set_language
from importios.native import Window
from test_native_connection import APP


def _not_found(path):
    return AfcFileNotFoundError(path, 8)


class MemoryAfc:
    """In-memory /Documents filesystem backed by an autospecced AfcService interface."""

    def __init__(self, corrupt_write=False):
        self.dirs = {'/Documents'}
        self.files = {}
        self.links = {}
        self.mtimes = {}
        self.handles = {}
        self.next_handle = 1
        self.corrupt_write = corrupt_write
        self.removed_single = []
        self.removed_tree = []

    def as_afc(self):
        afc = create_autospec(AfcService, instance=True, spec_set=True)
        afc.listdir = AsyncMock(side_effect=self.listdir)
        afc.stat = AsyncMock(side_effect=self.stat)
        afc.makedirs = AsyncMock(side_effect=self.makedirs)
        afc.fopen = AsyncMock(side_effect=self.fopen)
        afc.fread = AsyncMock(side_effect=self.fread)
        afc.fwrite = AsyncMock(side_effect=self.fwrite)
        afc.fclose = AsyncMock(side_effect=self.fclose)
        afc.rename = AsyncMock(side_effect=self.rename)
        afc.rm_single = AsyncMock(side_effect=self.rm_single)
        afc.rm = AsyncMock(side_effect=self.rm)
        return afc

    def add_dir(self, path, mtime=None):
        self.dirs.add(path)
        if mtime:
            self.mtimes[path] = mtime

    def add_file(self, path, data, mtime=None):
        self.files[path] = bytearray(data)
        if mtime:
            self.mtimes[path] = mtime

    def add_link(self, path, target):
        self.links[path] = target

    async def listdir(self, path):
        if path not in self.dirs:
            raise _not_found(path)
        prefix = path.rstrip('/') + '/'
        names = {'.', '..'}
        for group in (self.dirs, self.files, self.links):
            for item in group:
                if item.startswith(prefix):
                    rest = item[len(prefix):]
                    if '/' not in rest and rest:
                        names.add(rest)
        return sorted(names)

    async def stat(self, path):
        if path in self.dirs:
            return {'st_ifmt': 'S_IFDIR', 'st_size': 0, 'st_mtime': self.mtimes.get(path)}
        if path in self.files:
            return {'st_ifmt': 'S_IFREG', 'st_size': len(self.files[path]), 'st_mtime': self.mtimes.get(path)}
        if path in self.links:
            return {'st_ifmt': 'S_IFLNK', 'st_size': len(self.links[path]), 'st_mtime': self.mtimes.get(path)}
        raise _not_found(path)

    async def makedirs(self, path):
        parts = [p for p in path.split('/') if p]
        cur = ''
        for part in parts:
            cur += '/' + part
            self.dirs.add(cur)

    async def fopen(self, path, mode='r'):
        hid = self.next_handle
        self.next_handle += 1
        if mode == 'w':
            self.files[path] = bytearray()
            self.handles[hid] = ('w', path, 0)
        elif mode == 'r':
            if path not in self.files:
                raise _not_found(path)
            self.handles[hid] = ('r', path, 0)
        else:
            raise ValueError(mode)
        return hid

    async def fwrite(self, handle, data):
        _, path, _ = self.handles[handle]
        chunk = bytes(data)
        if self.corrupt_write and chunk:
            chunk = bytes([chunk[0] ^ 0xFF]) + chunk[1:]
        self.files[path].extend(chunk)

    async def fread(self, handle, size):
        mode, path, pos = self.handles[handle]
        data = bytes(self.files[path][pos:pos + size])
        self.handles[handle] = (mode, path, pos + len(data))
        return data

    async def fclose(self, handle):
        self.handles.pop(handle, None)

    async def rename(self, source, target):
        if source not in self.files:
            raise _not_found(source)
        self.files[target] = self.files.pop(source)

    async def rm_single(self, path, force=False):
        self.removed_single.append(path)
        if path in self.files:
            del self.files[path]
        elif path in self.links:
            del self.links[path]
        elif not force:
            raise _not_found(path)

    async def rm(self, path, force=False):
        self.removed_tree.append(path)
        prefix = path.rstrip('/') + '/'
        for group in (self.files, self.links):
            for key in [k for k in group if k == path or k.startswith(prefix)]:
                del group[key]
        self.dirs = {d for d in self.dirs if d != path and not d.startswith(prefix)}


class AppFilesBackendTests(unittest.TestCase):
    def test_validation_rejects_traversal_and_invalid_names(self):
        self.assertEqual(validate_bundle_id('org.videolan.vlc-ios'), 'org.videolan.vlc-ios')
        for bad in ('', '../evil', 'com..app', 'com.app.', 'com/app', 'a b'):
            with self.assertRaises(AppFilesError):
                validate_bundle_id(bad)
        self.assertEqual(validate_name('Música 2026.pdf'), 'Música 2026.pdf')
        for bad in ('', '   ', '.', '..', 'a/b', 'a\\b', 'a\x00b', 'x' * 256):
            with self.assertRaises(AppFilesError):
                validate_name(bad)
        self.assertEqual(normalize_relative('/Sub/Carpeta/'), 'Sub/Carpeta')
        self.assertEqual(documents_path(''), '/Documents')
        self.assertEqual(documents_path('Sub/A'), '/Documents/Sub/A')
        self.assertEqual(parent_relative('Sub/A'), 'Sub')
        self.assertEqual(parent_relative('Sub'), '')

    def test_list_sharing_apps_filters_and_sorts_using_real_proxy_spec(self):
        proxy = create_autospec(InstallationProxyService, instance=True, spec_set=True)
        proxy.get_apps = AsyncMock(return_value={
            'com.hidden.app': {'CFBundleIdentifier': 'com.hidden.app', 'CFBundleDisplayName': 'Oculta', 'UIFileSharingEnabled': False},
            'org.videolan.vlc-ios': {'CFBundleIdentifier': 'org.videolan.vlc-ios', 'CFBundleDisplayName': 'VLC', 'CFBundleShortVersionString': '3.5', 'UIFileSharingEnabled': True},
            'com.alpha.notes': {'CFBundleIdentifier': 'com.alpha.notes', 'CFBundleName': 'Árbol', 'UIFileSharingEnabled': 1},
            'bad/id': {'CFBundleIdentifier': 'bad/id', 'CFBundleDisplayName': 'Bad', 'UIFileSharingEnabled': True},
        })
        apps = asyncio.run(list_sharing_apps(proxy))
        proxy.get_apps.assert_awaited_once_with(application_type='User')
        self.assertEqual([a['bundle_id'] for a in apps], ['com.alpha.notes', 'org.videolan.vlc-ios'])
        self.assertEqual(apps[1]['version'], '3.5')

    def test_list_folder_hides_temp_files_and_sorts_dirs_first(self):
        fs = MemoryAfc()
        ts = datetime(2026, 5, 1, 10, 30)
        fs.add_dir('/Documents/Zeta', ts)
        fs.add_file('/Documents/alfa.txt', b'hello', ts)
        fs.add_file(f'/Documents/{TEMP_PREFIX}abc', b'partial')
        fs.add_link('/Documents/alias', '/etc/hosts')
        entries = asyncio.run(list_folder(fs.as_afc(), ''))
        self.assertEqual([(e['name'], e['kind'], e['size']) for e in entries], [
            ('Zeta', 'dir', None),
            ('alfa.txt', 'file', 5),
            ('alias', 'link', None),
        ])

    def test_create_folder_uses_makedirs_and_rejects_existing(self):
        fs = MemoryAfc()
        afc = fs.as_afc()
        rel = asyncio.run(create_folder(afc, '', 'Proyectos'))
        self.assertEqual(rel, 'Proyectos')
        afc.makedirs.assert_awaited_once_with('/Documents/Proyectos')
        with self.assertRaises(AppFilesError):
            asyncio.run(create_folder(afc, '', 'Proyectos'))

    def test_upload_files_and_folders_verifies_sha256_skips_existing_and_ignores_symlinks(self):
        fs = MemoryAfc()
        fs.add_file('/Documents/existing.txt', b'keep-me')
        afc = fs.as_afc()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            existing = root / 'existing.txt'
            existing.write_bytes(b'new-overwrite-attempt')
            doc = root / 'guia.pdf'
            doc.write_bytes(b'%PDF-1.7 sample bytes')
            folder = root / 'Album'
            (folder / 'Sub').mkdir(parents=True)
            (folder / 'Sub' / 'nota.txt').write_bytes(b'hola mundo')
            link = folder / 'skip-link.txt'
            os.symlink(doc, link)
            events = []
            summary = asyncio.run(upload_paths(afc, '', [existing, doc, folder], progress=lambda v, t, m: events.append((v, t, m))))
        self.assertEqual(summary, {'uploaded': 2, 'skipped': 1, 'folders_created': 2, 'cancelled': False})
        self.assertEqual(bytes(fs.files['/Documents/existing.txt']), b'keep-me')
        self.assertEqual(bytes(fs.files['/Documents/guia.pdf']), b'%PDF-1.7 sample bytes')
        self.assertEqual(bytes(fs.files['/Documents/Album/Sub/nota.txt']), b'hola mundo')
        self.assertNotIn('/Documents/Album/skip-link.txt', fs.files)
        self.assertTrue(any(TEMP_PREFIX not in k for k in fs.files))
        self.assertFalse(any(TEMP_PREFIX in k for k in fs.files))
        self.assertTrue(events and events[-1][0] == 100)

    def test_upload_cleans_up_temp_file_on_hash_mismatch(self):
        fs = MemoryAfc(corrupt_write=True)
        afc = fs.as_afc()
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'data.bin'
            source.write_bytes(b'integrity check payload')
            with self.assertRaises(AppFilesError) as ctx:
                asyncio.run(upload_paths(afc, '', [source]))
        self.assertEqual(ctx.exception.diagnostic, 'app-files:upload-hash')
        self.assertEqual(fs.files, {})
        self.assertTrue(any(TEMP_PREFIX in path for path in fs.removed_single))

    def test_large_files_up_to_128gb_and_skip_full_readback_above_threshold(self):
        from importios.app_files import MAX_FILE_BYTES
        self.assertEqual(MAX_FILE_BYTES, 128 * 1024**3)
        fs = MemoryAfc()
        afc = fs.as_afc()
        with tempfile.TemporaryDirectory() as tmp:
            movie = Path(tmp) / 'movie.mkv'
            movie.write_bytes(b'MKV-4K-VIDEO-DATA' * 100)
            with patch('importios.app_files.HASH_VERIFY_MAX_BYTES', 100):
                summary = asyncio.run(upload_paths(afc, '', [movie]))
        self.assertEqual(summary['uploaded'], 1)
        self.assertIn('/Documents/movie.mkv', fs.files)
        # Above HASH_VERIFY_MAX_BYTES, verification checks exact remote size via stat without re-reading the file over USB
        afc.fread.assert_not_awaited()

    def test_upload_cancellation_cleans_temp_file_and_preserves_partial_count(self):
        fs = MemoryAfc()
        afc = fs.as_afc()
        control = TransferControl()
        orig_rename = fs.rename

        async def cancel_after_first(src, dst):
            await orig_rename(src, dst)
            control.request()

        afc.rename = AsyncMock(side_effect=cancel_after_first)
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a.txt'
            b = Path(tmp) / 'b.txt'
            a.write_bytes(b'one')
            b.write_bytes(b'two')
            token = CURRENT.set(control)
            try:
                summary = asyncio.run(upload_paths(afc, '', [a, b]))
            finally:
                CURRENT.reset(token)
        self.assertEqual(summary['uploaded'], 1)
        self.assertTrue(summary['cancelled'])
        self.assertIn('/Documents/a.txt', fs.files)
        self.assertNotIn('/Documents/b.txt', fs.files)

    def test_export_files_and_folders_skips_symlinks_and_existing_local_files(self):
        fs = MemoryAfc()
        fs.add_file('/Documents/readme.txt', b'remote-readme')
        fs.add_dir('/Documents/Pack')
        fs.add_file('/Documents/Pack/clip.bin', b'\x00\x01\x02\x03')
        fs.add_link('/Documents/Pack/badlink', '/etc/passwd')
        afc = fs.as_afc()
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp)
            (dest / 'readme.txt').write_bytes(b'local-keep')
            summary = asyncio.run(export_entries(afc, ['readme.txt', 'Pack'], dest))
            self.assertEqual(summary, {'exported': 1, 'skipped': 1, 'cancelled': False})
            self.assertEqual((dest / 'readme.txt').read_bytes(), b'local-keep')
            self.assertEqual((dest / 'Pack' / 'clip.bin').read_bytes(), b'\x00\x01\x02\x03')
            self.assertFalse((dest / 'Pack' / 'badlink').exists())
            with self.assertRaises(AppFilesError):
                asyncio.run(export_entries(afc, [''], dest))

    def test_delete_entries_refuses_root_and_uses_rm_for_dirs_and_rm_single_for_files(self):
        fs = MemoryAfc()
        fs.add_dir('/Documents/Old')
        fs.add_file('/Documents/Old/inside.txt', b'x')
        fs.add_file('/Documents/note.txt', b'y')
        afc = fs.as_afc()
        with self.assertRaises(AppFilesError) as ctx:
            asyncio.run(delete_entries(afc, ['']))
        self.assertEqual(ctx.exception.diagnostic, 'app-files:delete-root')
        summary = asyncio.run(delete_entries(afc, ['Old', 'note.txt']))
        self.assertEqual(summary, {'deleted': 2, 'cancelled': False})
        self.assertEqual(fs.removed_tree, ['/Documents/Old'])
        self.assertEqual(fs.removed_single, ['/Documents/note.txt'])
        self.assertEqual(fs.files, {})
        self.assertEqual(fs.dirs, {'/Documents'})

    def test_run_app_action_cancelled_upload_skips_post_list_folder(self):
        fs = MemoryAfc()
        afc = fs.as_afc()
        control = TransferControl()
        orig_rename = fs.rename

        async def cancel_after_first(src, dst):
            await orig_rename(src, dst)
            control.request()

        afc.rename = AsyncMock(side_effect=cancel_after_first)

        class FakeCtx:
            async def __aenter__(self):
                return afc

            async def __aexit__(self, *args):
                return False

        def progress(*args):
            pass

        progress.control = control
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / 'a.txt'
            b = Path(tmp) / 'b.txt'
            a.write_bytes(b'123')
            b.write_bytes(b'456')
            with patch('importios.app_files.app_documents', return_value=FakeCtx()):
                result = run_app_action('upload', 'org.videolan.vlc-ios', '', [str(a), str(b)], progress=progress)
        self.assertTrue(result['cancelled'])
        self.assertEqual(result['uploaded'], 1)
        self.assertIsNone(result['entries'])
        afc.listdir.assert_not_awaited()


class AppFilesUITests(unittest.TestCase):
    def setUp(self):
        self.window = Window(auto_connect=False)
        self.window.show()
        APP.processEvents()

    def tearDown(self):
        self.window.tracks.clear()
        self.window.close()
        self.window.deleteLater()
        APP.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        APP.processEvents()
        set_language('es')

    def test_app_files_navigation_browsing_and_actions(self):
        w = self.window
        w.navigate(4)
        APP.processEvents()
        self.assertEqual(w.pages.currentIndex(), 4)
        self.assertFalse(w.app_add_files.isEnabled())
        self.assertFalse(w.app_export.isEnabled())
        self.assertFalse(w.app_delete.isEnabled())

        w.connection_token = 'phone-1'
        w.app_action_result({
            'action': 'list_apps',
            'apps': [{'bundle_id': 'org.videolan.vlc-ios', 'name': 'VLC', 'version': '3.5'}],
        })
        self.assertEqual(w.app_current_bundle, 'org.videolan.vlc-ios')
        self.assertTrue(w.app_pending_refresh)
        self.assertTrue(w.app_add_files.isEnabled())

        ts = datetime(2026, 5, 1, 14, 0)
        w.app_action_result({
            'action': 'list_folder',
            'bundle_id': 'org.videolan.vlc-ios',
            'relative': 'Videos',
            'entries': [
                {'name': 'Clips', 'relative': 'Videos/Clips', 'kind': 'dir', 'size': None, 'modified': ts},
                {'name': 'Demo.mp4', 'relative': 'Videos/Demo.mp4', 'kind': 'file', 'size': 2048, 'modified': ts},
            ],
        })
        self.assertEqual(w.app_path_label.text(), '/Documents/Videos')
        self.assertEqual(w.app_table.rowCount(), 2)
        self.assertTrue(w.app_up.isEnabled())

        with patch.object(w, 'start_app_action') as start:
            w.app_entry_activated(0, 0)
            start.assert_called_once_with('list_folder', 'org.videolan.vlc-ios', 'Videos/Clips')
            start.reset_mock()
            w.app_entry_activated(1, 0)
            start.assert_not_called()
            w.app_go_up()
            start.assert_called_once_with('list_folder', 'org.videolan.vlc-ios', '')

        w.app_table.selectRow(1)
        APP.processEvents()
        self.assertTrue(w.app_export.isEnabled())
        self.assertTrue(w.app_delete.isEnabled())

        with patch('importios.native.QInputDialog.getText', return_value=('Nueva', True)), \
             patch.object(w, 'start_app_action') as start:
            w.create_app_folder()
            start.assert_called_once_with('create_folder', 'org.videolan.vlc-ios', 'Videos', 'Nueva')

        dest_dir = str(Path(tempfile.gettempdir()))
        with patch('importios.native.QFileDialog.getExistingDirectory', return_value=dest_dir), \
             patch.object(w, 'start_app_action') as start:
            w.export_app_entries()
            start.assert_called_once_with('export', 'org.videolan.vlc-ios', 'Videos', (['Videos/Demo.mp4'], dest_dir))

        with patch('importios.native.QMessageBox.exec', return_value=QMessageBox.StandardButton.Cancel), \
             patch.object(w, 'start_app_action') as start:
            w.delete_app_entries()
            start.assert_not_called()

        with patch('importios.native.QMessageBox.exec', return_value=QMessageBox.StandardButton.Yes), \
             patch.object(w, 'start_app_action') as start:
            w.delete_app_entries()
            start.assert_called_once_with('delete', 'org.videolan.vlc-ios', 'Videos', ['Videos/Demo.mp4'])

    def test_contextual_drop_on_app_files_page_and_disconnect_reset(self):
        w = self.window
        w.navigate(4)
        sample_file = str(Path(tempfile.gettempdir()) / 'sample.pdf')
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(sample_file)])
        enter = QDragEnterEvent(QPointF(10, 10).toPoint(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        w.dragEnterEvent(enter)
        self.assertFalse(enter.isAccepted())

        w.app_current_bundle = 'org.videolan.vlc-ios'
        w.app_current_path = 'Inbox'
        enter2 = QDragEnterEvent(QPointF(10, 10).toPoint(), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        w.dragEnterEvent(enter2)
        self.assertTrue(enter2.isAccepted())
        self.assertEqual(w.drop_veil.title.text(), 'Suelta archivos o carpetas aquí')

        drop = QDropEvent(QPointF(10, 10), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        with patch.object(w, 'start_app_action') as start, patch.object(w, 'add_paths') as add_music:
            w.dropEvent(drop)
            start.assert_called_once_with('upload', 'org.videolan.vlc-ios', 'Inbox', [sample_file])
            add_music.assert_not_called()

        w.devices_found([])
        self.assertIsNone(w.app_current_bundle)
        self.assertEqual(w.app_table.rowCount(), 0)
        self.assertEqual(w.app_path_label.text(), '/Documents')

    def test_live_language_switch_translates_app_files_page(self):
        w = self.window
        w.navigate(4)
        w.app_action_result({
            'action': 'list_folder',
            'bundle_id': 'org.videolan.vlc-ios',
            'relative': '',
            'entries': [
                {'name': 'CarpetaReal', 'relative': 'CarpetaReal', 'kind': 'dir', 'size': None, 'modified': None},
                {'name': 'ArchivoReal.pdf', 'relative': 'ArchivoReal.pdf', 'kind': 'file', 'size': 1024, 'modified': None},
                {'name': 'SinExt', 'relative': 'SinExt', 'kind': 'file', 'size': 128, 'modified': None},
            ],
        })
        w.language_choice.setCurrentIndex(1)
        self.assertEqual(w.nav_buttons[4].text(), 'App files')
        self.assertEqual(w.app_table.horizontalHeaderItem(0).text(), 'Name')
        self.assertEqual(w.app_table.item(0, 0).text(), 'CarpetaReal')
        self.assertEqual(w.app_table.item(0, 1).text(), 'Folder')
        self.assertEqual(w.app_table.item(1, 1).text(), 'PDF file')
        self.assertEqual(w.app_table.item(2, 1).text(), 'File')
        self.assertEqual(w.app_format_filter.itemText(0), 'All types')
        self.assertEqual(w.app_format_filter.itemText(1), 'Folders (1)')
        self.assertEqual(w.app_add_files.text(), 'Add files')
        w.language_choice.setCurrentIndex(0)
        self.assertEqual(w.nav_buttons[4].text(), 'Archivos de apps')
        self.assertEqual(w.app_table.item(0, 1).text(), 'Carpeta')
        self.assertEqual(w.app_table.item(1, 1).text(), 'Archivo PDF')
        self.assertEqual(w.app_table.item(2, 1).text(), 'Archivo')
        self.assertEqual(w.app_format_filter.itemText(0), 'Todos los tipos')
        self.assertEqual(w.app_format_filter.itemText(1), 'Carpetas (1)')

    def test_app_files_format_filter_and_type_grouping(self):
        w = self.window
        w.navigate(4)
        w.app_action_result({
            'action': 'list_folder',
            'bundle_id': 'org.videolan.vlc-ios',
            'relative': '',
            'entries': [
                {'name': 'Diagnostics', 'relative': 'Diagnostics', 'kind': 'dir', 'size': None, 'modified': None},
                {'name': 'Alpha.mp3', 'relative': 'Alpha.mp3', 'kind': 'file', 'size': 1700000, 'modified': None},
                {'name': 'Beta.flac', 'relative': 'Beta.flac', 'kind': 'file', 'size': 9500000, 'modified': None},
                {'name': 'Gamma.mp3', 'relative': 'Gamma.mp3', 'kind': 'file', 'size': 1600000, 'modified': None},
                {'name': 'Notas.pdf', 'relative': 'Notas.pdf', 'kind': 'file', 'size': 25000, 'modified': None},
                {'name': 'README', 'relative': 'README', 'kind': 'file', 'size': 512, 'modified': None},
            ],
        })
        self.assertEqual(w.app_table.rowCount(), 6)
        self.assertEqual(w.app_entries_count.text(), '6 elementos')

        # Verify dynamic filter options: Todos los tipos, Carpetas (1), Audio (3), FLAC (1), MP3 (2), PDF (1), Sin extensión (1)
        options = [(w.app_format_filter.itemText(i), w.app_format_filter.itemData(i)) for i in range(w.app_format_filter.count())]
        self.assertEqual(options, [
            ('Todos los tipos', ''),
            ('Carpetas (1)', 'dir'),
            ('Audio (3)', 'audio'),
            ('FLAC (1)', 'ext:FLAC'),
            ('MP3 (2)', 'ext:MP3'),
            ('PDF (1)', 'ext:PDF'),
            ('Sin extensión (1)', 'no_ext'),
        ])

        # Filter by MP3
        w.app_format_filter.setCurrentIndex(w.app_format_filter.findData('ext:MP3'))
        self.assertEqual(w.app_table.rowCount(), 2)
        self.assertEqual([w.app_table.item(r, 0).text() for r in range(w.app_table.rowCount())], ['Alpha.mp3', 'Gamma.mp3'])
        self.assertEqual(w.app_entries_count.text(), '2 de 6 elementos')

        # Filter by Audio (includes both MP3 and FLAC)
        w.app_format_filter.setCurrentIndex(w.app_format_filter.findData('audio'))
        self.assertEqual(w.app_table.rowCount(), 3)
        self.assertEqual([w.app_table.item(r, 0).text() for r in range(w.app_table.rowCount())], ['Alpha.mp3', 'Beta.flac', 'Gamma.mp3'])

        # Filter by Folders
        w.app_format_filter.setCurrentIndex(w.app_format_filter.findData('dir'))
        self.assertEqual(w.app_table.rowCount(), 1)
        self.assertEqual(w.app_table.item(0, 0).text(), 'Diagnostics')

        # Reset filter and sort by column 1 (Tipo) to group by file type
        w.app_format_filter.setCurrentIndex(0)
        w.app_table.sortByColumn(1, Qt.SortOrder.AscendingOrder)
        grouped = [(w.app_table.item(r, 0).text(), w.app_table.item(r, 1).text()) for r in range(w.app_table.rowCount())]
        self.assertEqual(grouped, [
            ('Diagnostics', 'Carpeta'),
            ('Beta.flac', 'Archivo FLAC'),
            ('Alpha.mp3', 'Archivo MP3'),
            ('Gamma.mp3', 'Archivo MP3'),
            ('Notas.pdf', 'Archivo PDF'),
            ('README', 'Archivo'),
        ])

    def test_close_is_blocked_while_app_worker_is_running(self):
        w = self.window
        w.app_worker = MagicMock()
        event = MagicMock()
        try:
            w.closeEvent(event)
            event.ignore.assert_called_once()
        finally:
            w.app_worker = None


if __name__ == '__main__':
    unittest.main()
