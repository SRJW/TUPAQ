import hashlib
from pathlib import Path
import plistlib
import unittest

from importios.sync.signing import FixedHostSession, HOST_REQUEST, MAX_OPERATION_BYTES


class SigningTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vectors = plistlib.loads((Path(__file__).parent/'fixtures/sync/grappa-fixed-vectors.plist').read_bytes())

    def test_request_matches_published_contract(self):
        self.assertEqual(len(HOST_REQUEST), 84)
        self.assertEqual(hashlib.sha256(HOST_REQUEST).hexdigest(),
                         '6c3f39f3efbf1d2a29a983f58a974c43f1f5b05b529f8ba0c116f9d51842d348')

    def test_all_four_independent_vectors(self):
        self.assertEqual(len(self.vectors), 4)
        for vector in self.vectors:
            with self.subTest(operation=hashlib.sha256(vector['operation']).hexdigest()):
                session = FixedHostSession(vector['request'], vector['reply'])
                self.assertEqual(session.sign(vector['operation']), vector['sidecar'])

    def test_rejects_every_single_byte_change_to_request(self):
        for index in range(84):
            changed = bytearray(HOST_REQUEST)
            changed[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                FixedHostSession(bytes(changed), self.vectors[0]['reply'])

    def test_rejects_other_reply_lengths_and_envelopes(self):
        reply = self.vectors[0]['reply']
        for length in [0, 1, 2, 18, 19, 64, 82, 84, 4096]:
            with self.subTest(length=length), self.assertRaises(ValueError):
                FixedHostSession(HOST_REQUEST, (reply+b'\0'*4096)[:length])
        for index in [0, 1, 18]:
            changed = bytearray(reply)
            changed[index] ^= 1
            with self.subTest(index=index), self.assertRaises(ValueError):
                FixedHostSession(HOST_REQUEST, bytes(changed))

    def test_exact_operation_bytes_and_bounds(self):
        session = FixedHostSession(HOST_REQUEST, self.vectors[0]['reply'])
        baseline = session.sign(b'<plist/>\n')
        for operation in [b'<plist/>', b'<plist/>\r\n', b'<plist/>\n\0']:
            self.assertNotEqual(session.sign(operation), baseline)
        for invalid in [b'', b'x'*(MAX_OPERATION_BYTES+1)]:
            with self.assertRaises(ValueError):
                session.sign(invalid)
        self.assertEqual(len(session.sign(b'x'*MAX_OPERATION_BYTES)), 21)

    def test_closed_session_cannot_sign_and_repr_does_not_expose_material(self):
        session = FixedHostSession(HOST_REQUEST, self.vectors[0]['reply'])
        self.assertNotIn(self.vectors[0]['key'].hex(), repr(session))
        session.close()
        with self.assertRaises(ValueError):
            session.sign(b'operation')
