"""Local-vs-cloud counts and value sorting without losing song identity."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from PySide6.QtCore import Qt,QItemSelectionModel
from importios.library import read_catalogue
from importios.library_fields import local_tracks
from importios.models import LibraryModel
from test_native_connection import APP,Window
from test_transfers import initial_catalogue


class LibraryViewTests(unittest.TestCase):
    def test_downloaded_subscription_audio_is_local_even_without_unprotected_asset(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'library.db';path.write_bytes(initial_catalogue())
            with closing(sqlite3.connect(path)) as db:
                db.executescript('''CREATE TABLE item_state(item_pid PRIMARY KEY,is_placeholder,is_library_added,
                    has_non_purgeable_asset,has_non_purgeable_subscription_protected_local_asset);
                    INSERT INTO item_state VALUES(1,0,1,0,1);''');db.commit()
            self.assertEqual(len(local_tracks(read_catalogue(path))),1)

    def test_cloud_copy_and_unfilled_item_do_not_count_as_downloaded_audio(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'library.db';path.write_bytes(initial_catalogue())
            with closing(sqlite3.connect(path)) as db:
                db.executescript('''CREATE TABLE item_state(item_pid INTEGER PRIMARY KEY,is_placeholder,is_library_added,has_non_purgeable_asset);
                    INSERT INTO item_state VALUES(1,0,1,1);
                    INSERT INTO item SELECT 2,media_type,item_artist_pid,album_pid,0,0 FROM item WHERE item_pid=1;
                    INSERT INTO item SELECT 3,media_type,item_artist_pid,album_pid,0,0 FROM item WHERE item_pid=1;
                    INSERT INTO item_extra SELECT 2,title,total_time_ms,NULL,0 FROM item_extra WHERE item_pid=1;
                    INSERT INTO item_extra SELECT 3,title,total_time_ms,NULL,0 FROM item_extra WHERE item_pid=1;
                    INSERT INTO item_state VALUES(2,0,1,0),(3,1,1,0);
                    INSERT INTO item_playback VALUES(1,301);''');db.commit()
            diagnostics={};all_tracks=read_catalogue(path,diagnostics)
            self.assertEqual(len(all_tracks),3)
            self.assertEqual([t['id'] for t in local_tracks(all_tracks)],['1'])
            self.assertEqual(diagnostics['local_tracks'],1)
            self.assertEqual(all_tracks[0]['format_label'],'MP3')

    def test_same_title_different_files_are_preserved_but_same_file_reference_is_counted_once(self):
        rows=[{'id':str(n),'title':'La misma canción','is_local':True,'afc_path':path} for n,path in
            enumerate(['iTunes_Control/Music/F00/AAAA.mp3','iTunes_Control/Music/F01/BBBB.mp3','iTunes_Control/Music/F00/AAAA.mp3'])]
        self.assertEqual([row['id'] for row in local_tracks(rows)],['0','1'])

    def test_numeric_sort_and_persistent_selection_follow_song_ids(self):
        window=Window(auto_connect=False);window.show();APP.processEvents()
        try:
            rows=[{'id':'a','title':'Árbol','artist':'Z','album':'A','duration':60,'size':9*1024**2,'is_local':True},
                  {'id':'b','title':'Barco','artist':'A','album':'B','duration':601,'size':12*1024**2,'is_local':True}]
            window.show_library(rows);window.library_table.selectRow(0)
            self.assertEqual(window.library_model.tracks[window.library_table.selectionModel().selectedRows()[0].row()]['id'],'a')
            for column in (0,1,2,4,5):
                window.library_table.sortByColumn(column,Qt.SortOrder.DescendingOrder);APP.processEvents()
                selected=window.library_table.selectionModel().selectedRows()
                self.assertEqual(len(selected),1)
                self.assertEqual(window.library_model.tracks[selected[0].row()]['id'],'a')
            self.assertEqual(window.library_model.tracks[0]['id'],'b')
            window.library_model.set_details('a',{'size':20*1024**2,'size_source':'usb'})
            self.assertEqual(window.library_model.tracks[0]['id'],'a')
            self.assertEqual(window.library_model.data(window.library_model.index(0,5)),'20.0 MB')
        finally:window.close();window.deleteLater();APP.processEvents()

    def test_reference_navigation_preserves_library_transfer_actions(self):
        window=Window(auto_connect=False);window.show();APP.processEvents()
        try:
            self.assertEqual([button.text() for button in window.nav_buttons],['Biblioteca','Preferencias','Importar','Diagnóstico'])
            self.assertTrue(window.choose.isVisible());self.assertTrue(window.import_phone.isVisible());self.assertTrue(window.export_phone.isVisible())
            rows=[{'id':'local','title':'Local','artist':'A','album':'B','duration':1,'is_local':True,'usb_exists':True},
                  {'id':'cloud','title':'Local','artist':'A','album':'B','duration':1,'is_local':False}]
            window.show_library(rows)
            self.assertEqual(window.library_model.rowCount(),1)
            self.assertFalse(hasattr(window,'phone_filter'))
            self.assertNotIn('Archivo por USB',[window.library_model.headerData(i,Qt.Orientation.Horizontal) for i in range(window.library_model.columnCount())])
            self.assertEqual(window.library_model.rowCount(),1)
            window.search.setText('absent')
            self.assertEqual(window.library_model.rowCount(),0)
            window.search.setText('local')
            self.assertEqual(window.library_model.rowCount(),1)
            window.library_table.selectRow(0)
            self.assertEqual(window.now_title.text(),'Local')
        finally:window.close();window.deleteLater();APP.processEvents()

    def test_unknown_duration_is_not_displayed_as_zero(self):
        from importios.models import duration_label
        self.assertEqual(duration_label(None),'—')
        self.assertEqual(duration_label(0),'—')
        self.assertEqual(duration_label(.1),'0:01')
        self.assertEqual(duration_label(148),'2:28')

    def test_playback_frame_count_recovers_missing_duration(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'library.db';path.write_bytes(initial_catalogue())
            with closing(sqlite3.connect(path)) as db:
                db.executescript("ALTER TABLE item_playback ADD COLUMN duration; ALTER TABLE item_playback ADD COLUMN sample_rate; UPDATE item_extra SET total_time_ms=0; INSERT INTO item_playback VALUES(1,301,6526800,44100);")
                db.commit()
            self.assertEqual(read_catalogue(path)[0]['duration'],148)
