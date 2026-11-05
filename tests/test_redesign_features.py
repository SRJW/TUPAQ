"""Real preferences and read-only checks behind the reference UI."""
import asyncio
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch,Mock
from PySide6.QtCore import QEvent,Qt
from PySide6.QtGui import QFontMetrics
from mutagen import File as AudioFile
from test_native_connection import APP,TRACK
from test_deletion import Phone
from test_selected_assets import cover
from importios.native import Window
from importios.audio import inspect_audio,read_artwork
from importios.transfers import run_transfer,TransferError,PREF
from importios.library import read_catalogue
from importios.cancellation import TransferControl
from importios.export_artwork import embed
from importios.preparation import expand
from importios.history import record,recent

FIXTURES=Path(__file__).parent/'fixtures'


def call(phone,mode,selected,root,progress=lambda *args:None):
    with patch('importios.transfers.device',phone.device),patch('importios.transfers.Atc',lambda peer:peer):return run_transfer(mode,selected,root,progress)


def selection(name,**kwargs):
    path=FIXTURES/name
    return dict(path=str(path),id=hashlib.sha256(path.read_bytes()).hexdigest(),**kwargs)


class NativePreferenceTests(unittest.TestCase):
    def test_filename_metadata_policy_changes_projection_without_rewriting_original(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();source=FIXTURES/'sample.mp3';original=source.read_bytes()
            result=call(phone,'import',[selection('sample.mp3',metadata_policy='filename')],Path(root))
            self.assertEqual(result['imported'],1);self.assertEqual(phone.operations[0]['item']['title'],'sample')
            self.assertEqual(source.read_bytes(),original)

    def test_disabling_artwork_omits_catalogue_asset_and_keeps_embedded_original(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();source=FIXTURES/'covered-aac.m4a';original=source.read_bytes()
            result=call(phone,'import',[selection('covered-aac.m4a',send_artwork=False)],Path(root))
            self.assertEqual(result['imported'],1);self.assertNotIn('artwork_cache_id',phone.operations[0]['item'])
            receipt=json.loads((Path(result['backup'])/'journal.json').read_text())
            self.assertEqual(phone.files['/'+receipt['entries'][0]['destination']],original)
            self.assertEqual(source.read_bytes(),original)

    def test_import_bound_to_another_phone_stops_before_remote_writes(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone()
            with self.assertRaises(TransferError):call(phone,'import',[selection('sample.mp3',required_device_token='b'*64)],Path(root))
            self.assertFalse(phone.writes);self.assertFalse(phone.sent)

    def test_export_embedding_changes_only_a_verified_local_copy(self):
        from unittest.mock import AsyncMock
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();original=phone.files['/iTunes_Control/Music/F00/AAAA.mp3'];data=cover(90,90)
            database=Path(root)/'catalogue.db';database.write_bytes(phone.files[PREF+'MediaLibrary.sqlitedb']);chosen=read_catalogue(database)[0];chosen['embed_artwork']=True
            with patch('importios.remote_artwork.cover_for_track',new=AsyncMock(return_value={'cover':data})):
                result=call(phone,'export',[chosen],Path(root))
            self.assertEqual(result['exported'],1);self.assertEqual(result['covers_embedded'],1)
            self.assertEqual(read_artwork(result['files'][0]),data)
            self.assertEqual(phone.files['/iTunes_Control/Music/F00/AAAA.mp3'],original)
            self.assertFalse(phone.writes);self.assertFalse(phone.sent)

    def test_embedding_preserves_existing_covers_and_all_supported_audio_timings(self):
        data=cover(90,90)
        with tempfile.TemporaryDirectory() as root:
            for name in ('sample.mp3','sample.wav','sample.aiff','sample.m4a','covered-aac.m4a'):
                with self.subTest(name=name):
                    path=Path(root)/name;path.write_bytes((FIXTURES/name).read_bytes());info=AudioFile(path).info;before=(info.length,info.sample_rate,info.channels)
                    existing=read_artwork(path);result=embed(path,data)
                    self.assertEqual(result,not bool(existing));self.assertEqual(read_artwork(path),existing or data)
                    info=AudioFile(path).info;self.assertEqual((info.length,info.sample_rate,info.channels),before)

    def test_diagnostics_read_entire_original_without_metadata_or_audio_writes(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();original=dict(phone.files)
            result=call(phone,'diagnose',[],Path(root))
            self.assertEqual(result['diagnosed'],1);self.assertEqual(result['files_failed'],0);self.assertTrue(result['catalogue_checked'])
            self.assertEqual(phone.files,original);self.assertFalse(phone.writes);self.assertFalse(phone.sent);self.assertFalse(phone.handles)

    def test_diagnostics_detect_corruption_against_an_owned_import_receipt(self):
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();result=call(phone,'import',[selection('sample.m4a')],Path(root))
            receipt=json.loads((Path(result['backup'])/'journal.json').read_text());path='/'+receipt['entries'][0]['destination']
            body=phone.files[path];phone.files[path]=body[:-1]+bytes([body[-1]^1]);original=dict(phone.files);sent=len(phone.sent)
            result=call(phone,'diagnose',[],Path(root))
            self.assertEqual(result['hash_mismatches'],1);self.assertEqual(result['files_failed'],1)
            self.assertEqual(phone.files,original);self.assertEqual(len(phone.sent),sent);self.assertFalse(phone.handles)

    def test_pause_waits_at_boundary_and_cancel_releases_paused_job(self):
        control=TransferControl();control.pause_requested.set();seen=[]
        def progress(*args):seen.append(args[2]);control.request()
        progress.control=control
        with tempfile.TemporaryDirectory() as root:
            phone=Phone();result=call(phone,'diagnose',[],Path(root),progress)
            self.assertTrue(result['cancelled']);self.assertIn('Pausado entre lotes.',seen);self.assertFalse(phone.sent);self.assertFalse(phone.handles)

    def test_pause_requested_during_import_finishes_native_batch_before_waiting(self):
        from mutagen.id3 import ID3,TIT2
        import sqlite3
        from contextlib import closing
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);phone=Phone();chosen=[];control=TransferControl();requested=[];observed=[]
            for n in range(51):
                path=root/f'{n}.mp3';path.write_bytes((FIXTURES/'sample.mp3').read_bytes());tags=ID3(path);tags.add(TIT2(encoding=3,text=f'Pause {n}'));tags.save(path)
                chosen.append({'path':str(path),'id':hashlib.sha256(path.read_bytes()).hexdigest()})
            def progress(value,total,label,*args):
                if 'Importando:' in label and not requested:requested.append(True);control.pause_requested.set()
                if label=='Pausado entre lotes.':
                    self.assertFalse(control.committed)
                    with closing(sqlite3.connect(':memory:')) as db:
                        db.deserialize(phone.files[PREF+'MediaLibrary.sqlitedb']);observed.append(db.execute('SELECT count(*) FROM item').fetchone()[0])
                    control.pause_requested.clear()
            progress.control=control
            result=call(phone,'import',chosen,root/'backups',progress)
            self.assertEqual(observed,[50]);self.assertEqual(result['imported'],51);self.assertFalse(result.get('bulk_stopped'))


class PreparationHistoryTests(unittest.TestCase):
    def test_folder_expansion_excludes_flac_and_is_bounded_before_preparation(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);(root/'nested').mkdir()
            (root/'one.mp3').write_bytes(b'fixture');(root/'nested'/'two.WAV').write_bytes(b'fixture');(root/'skip.flac').write_bytes(b'fixture')
            self.assertEqual({p.name for p in expand([root])},{'one.mp3','two.WAV'})
            with self.assertRaises(ValueError):expand([root],limit=1)
            self.assertEqual(expand([root],lambda:True),[])

    def test_change_probe_uses_only_two_stat_requests(self):
        from importios.library import catalogue_stamp
        from unittest.mock import AsyncMock
        afc=Mock();afc.stat=AsyncMock(side_effect=[{'st_size':100,'st_mtime':1},FileNotFoundError()])
        result=asyncio.run(catalogue_stamp(afc))
        self.assertEqual(result,((100,'1'),None));self.assertEqual(afc.stat.await_count,2);afc.fopen.assert_not_called()

    def test_storage_figures_use_only_valid_device_reported_values(self):
        from importios.library import device_volume
        self.assertEqual(device_volume({'FSTotalBytes':'256000000000','FSFreeBytes':'120000000000'}),{'total_bytes':256000000000,'free_bytes':120000000000})
        for values in ({},{'FSTotalBytes':'0','FSFreeBytes':'0'},{'FSTotalBytes':'100','FSFreeBytes':'101'},{'FSTotalBytes':'100','FSFreeBytes':'-1'},{'FSTotalBytes':'9'*30,'FSFreeBytes':'1'},None):
            with self.subTest(values=values):self.assertEqual(device_volume(values),{})

    def test_history_is_aggregate_and_never_prunes_catalogue_receipts(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);saved=root/'catalogue-backups'/'old';saved.mkdir(parents=True);(saved/'journal.json').write_text('preserve')
            record(root,'import',5,{'imported':4,'bulk_stopped':True,'source_ids':['private song'],'files':['private path']})
            row=recent(root)[0];self.assertEqual(row['status'],'stopped');self.assertEqual(row['confirmed'],4)
            body=next((root/'history').glob('*.json')).read_text();self.assertNotIn('private',body);self.assertEqual((saved/'journal.json').read_text(),'preserve')


class ReferenceUITests(unittest.TestCase):
    def setUp(self):self.w=Window(auto_connect=False);self.w.show();APP.processEvents()
    def tearDown(self):
        self.w.tracks.clear();self.w.close();self.w.deleteLater();APP.sendPostedEvents(None,QEvent.Type.DeferredDelete);APP.processEvents()

    def test_reference_pages_are_usable_in_both_appearances_at_minimum_width(self):
        w=self.w;w.resize(1080,720);w.show_library([dict(TRACK,id=str(n)) for n in range(12)]);w.library_model.checked.add('2')
        for appearance in (1,2):
            w.theme_choice.setCurrentIndex(appearance)
            for page in (0,2,3,1):
                w.navigate(page);APP.processEvents();self.assertEqual(w.pages.currentIndex(),page)
                for control in w.nav_buttons+w.settings_buttons:
                    required=QFontMetrics(control.font()).horizontalAdvance(control.text())+36
                    self.assertGreaterEqual(control.width(),required,control.text())
                self.assertEqual(w.library_model.checked,{'2'})
        self.assertGreaterEqual(w.library_table.columnWidth(3),QFontMetrics(w.library_table.font()).horizontalAdvance('M4A · ALAC')+18)

    def test_format_and_content_filters_keep_actual_selection(self):
        w=self.w;w.show_library([dict(TRACK,id='a',format_label='M4A · ALAC',has_artwork=True),dict(TRACK,id='b',format_label='MP3',afc_path='iTunes_Control/Music/F00/BBBB.mp3')])
        w.library_model.checked.add('a');w.format_filter.setCurrentIndex(w.format_filter.findText('MP3'));self.assertEqual([t['id'] for t in w.library_model.tracks],['b'])
        w.format_filter.setCurrentIndex(0);w.content_filter.setCurrentIndex(1);self.assertEqual([t['id'] for t in w.library_model.tracks],['a']);self.assertEqual(w.library_model.checked,{'a'})

    def test_automatic_import_requires_the_same_loaded_device_and_explicit_setting(self):
        w=self.w;w.connection_token='one';w.library_ready=True;w.device_details={'_device_token':'a'*64}
        with patch.object(w,'import_songs') as send:
            w.auto_import_prepared('one');send.assert_not_called()
            w.auto_import.setChecked(True);w.auto_import_prepared('other');send.assert_not_called()
            w.auto_import_prepared('one');send.assert_called_once()
            send.reset_mock();w.accept_track(inspect_audio(FIXTURES/'sample.mp3','sample.mp3'));w.preparation_count_before=len(w.tracks);w.auto_target_token='one'
            w.read_finished();APP.processEvents();send.assert_not_called()

    def test_manual_library_read_and_unknown_hashes_are_reported_truthfully(self):
        w=self.w;w.show_library([dict(TRACK)])
        self.assertTrue(w.usb_connected);self.assertEqual(w.diagnostic_fields['connection'].text(),'Conectado por USB')
        self.assertTrue(w.health_fields['permissions'].property('passed'));self.assertFalse(w.health_fields['integrity'].property('passed'))
        w.diagnostic_result={'diagnosed':1,'files_failed':0,'hash_verified':0,'hash_mismatches':0};w.update_diagnostics()
        self.assertEqual(w.health_fields['integrity'].text(),'Sin recibos previos');self.assertFalse(w.health_fields['integrity'].property('passed'))

    def test_detected_catalogue_change_refreshes_without_blank_rows(self):
        w=self.w;w.show_library([dict(TRACK)]);w.connection_token='one';w.library_ready=True
        w.device_details={'_catalogue_stamp':((100,'a'),None)}
        with patch.object(w,'load_library') as refresh:
            w.devices_found([{'token':'one','catalogue_stamp':((100,'a'),None)}]);refresh.assert_not_called()
            w.devices_found([{'token':'one','catalogue_stamp':((100,'b'),None)}]);refresh.assert_called_once_with(automatic=True)
            self.assertEqual(w.library_model.rowCount(),1)
        w.library_ready=True;w.refresh_after_transfer.setChecked(False)
        with patch.object(w,'load_library') as refresh:w.devices_found([{'token':'one','catalogue_stamp':((200,'c'),None)}]);refresh.assert_not_called()

    def test_turning_off_refresh_never_removes_transfer_verification(self):
        w=self.w;w.refresh_after_transfer.setChecked(False)
        with tempfile.TemporaryDirectory() as root:
            w.backup_root=Path(root)/'catalogue-backups';w.transfer_worker=Mock(mode='import',selected=[]);w.transfer_outcome={'imported':1,'source_ids':[]}
            with patch.object(w,'load_library') as refresh:w.transfer_finished();refresh.assert_not_called()
            self.assertEqual(recent(Path(root))[0]['confirmed'],1)
            w.show_library([dict(TRACK,id='a'),dict(TRACK,id='b',afc_path='iTunes_Control/Music/F00/BBBB.mp3')]);w.transfer_worker=Mock(mode='delete',selected=[]);w.transfer_outcome={'deleted':1,'item_ids':['a']}
            with patch.object(w,'load_library') as refresh:w.transfer_finished();refresh.assert_not_called()
            self.assertEqual([t['id'] for t in w.library_model.tracks],['b'])
