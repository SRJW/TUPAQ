import plistlib
import unittest

from importios.devices import HEADER, DiscoveryError, read_devices


class FakeStream:
    def __init__(self, reply):
        self.reply = reply
        self.sent = b''

    def sendall(self, data):
        self.sent += data

    def recv(self, size):
        # Exercise partial header and payload reads.
        data = self.reply[:min(size, 7)]
        self.reply = self.reply[len(data):]
        return data


def response(value):
    body = plistlib.dumps(value)
    return HEADER.pack(len(body)+HEADER.size, 1, 8, 1)+body


class DiscoveryTests(unittest.TestCase):
    def test_lists_usb_only_and_does_not_expose_identifiers(self):
        stream = FakeStream(response({'DeviceList': [
            {'DeviceID': 4, 'Properties': {'ConnectionType': 'USB', 'SerialNumber': 'private'}},
            {'DeviceID': 5, 'Properties': {'ConnectionType': 'Network'}}]}))
        self.assertEqual(read_devices(stream), [{'connection': 'USB'}])
        request = plistlib.loads(stream.sent[HEADER.size:])
        self.assertEqual(request['MessageType'], 'ListDevices')
        self.assertEqual(len(stream.sent), HEADER.unpack_from(stream.sent)[0])

    def test_empty_list_is_valid(self):
        self.assertEqual(read_devices(FakeStream(response({'DeviceList': []}))), [])

    def test_optional_connection_token_changes_on_replug_without_returning_serial(self):
        def token(device_id):
            stream = FakeStream(response({'DeviceList':[{'DeviceID':device_id,
                'Properties':{'ConnectionType':'USB','SerialNumber':'private-serial'}}]}))
            return read_devices(stream,fingerprint=True)
        first = token(1)
        self.assertEqual(first,token(1))
        self.assertNotEqual(first,token(2))
        self.assertEqual(len(first[0]['token']),64)
        self.assertNotIn('private-serial',repr(first))

    def test_service_error_is_not_treated_as_no_devices(self):
        for value in [{'MessageType': 'Result', 'Number': 1}, {'DeviceList': ['invalid entry']}]:
            with self.subTest(value=value), self.assertRaises(DiscoveryError):
                read_devices(FakeStream(response(value)))

    def test_reject_truncation_wrong_type_tag_and_large_replies(self):
        for wire in [b'', HEADER.pack(1024*1024+1, 1, 8, 1),
                     HEADER.pack(30, 1, 8, 2), HEADER.pack(30, 1, 1, 1),
                     HEADER.pack(18, 1, 8, 1)+b'xx']:
            with self.subTest(wire=wire), self.assertRaises(DiscoveryError):
                read_devices(FakeStream(wire))
