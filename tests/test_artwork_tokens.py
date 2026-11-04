"""Keep heterogeneous existing artwork tokens without rewriting or collisions."""
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
import test_transfers as support
from importios.sync.catalogue import snapshot

class ArtworkTokenTests(unittest.TestCase):
    def test_existing_tokens_can_be_opaque_numeric_or_null(self):
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)/'catalogue';path.write_bytes(support.initial_catalogue())
            with closing(sqlite3.connect(path)) as db:
                db.executescript('DROP TABLE artwork; CREATE TABLE artwork(artwork_token, artwork_source_type, artwork_type, artwork_variant_type, relative_path);')
                for token in ('hash-token','000145',None,'0','4294967296','0x1234',4000000000):
                    db.execute('INSERT INTO artwork VALUES(?,300,6,0,NULL)',(token,))
                db.execute("INSERT INTO artwork_token VALUES(1,0,'hash-token',300,6,0)");db.commit()
            result=snapshot(path)
            self.assertEqual(result['artwork_ids'],{0,145,4000000000});self.assertEqual(len(result['artwork_tokens']),7)
            self.assertNotIn('77',result['artwork_tracks'])

    def test_covered_import_reserves_existing_numeric_alias_and_preserves_opaque_reference(self):
        with tempfile.TemporaryDirectory() as root:
            phone=support.Phone()
            with closing(sqlite3.connect(':memory:')) as db:
                db.deserialize(phone.files[support.PREF+'MediaLibrary.sqlitedb'])
                db.executescript("INSERT INTO artwork VALUES('000150',300,6,0,NULL); INSERT INTO artwork VALUES('opaque',300,6,0,NULL);")
                db.commit();phone.files[support.PREF+'MediaLibrary.sqlitedb']=db.serialize()
            chosen=support.TransferTests.selected(self,'covered-aac.m4a')
            result=support.TransferTests.call(self,phone,'import',[chosen],root)
            self.assertEqual(result['imported'],1)
            self.assertEqual(phone.operations[0]['item']['artwork_cache_id'],151)

    def test_high_cache_id_does_not_exhaust_free_lower_ids(self):
        from importios.sync.artwork import allocate_cache_id
        reserved={100,101,0xffffffff}
        self.assertEqual(allocate_cache_id(reserved),102)
        self.assertEqual(allocate_cache_id(reserved),103)
