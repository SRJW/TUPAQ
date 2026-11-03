"""Read support facts from the extracted sample, without executing any module."""
import argparse
import binascii
import hashlib
import json
from pathlib import Path
import struct

import pefile

EXPECTED = {
    '3uTools.exe': '2bc4b58583b982aa59add702e200b7df4fc5058ca10e075ce277975acc786e83',
    'idm_media.dll': '6fdaeb62646cba0e3fa72228fe320d63ce740440e36a5c31180e5494296496d2',
}


def inspect(root):
    samples = {}
    for name, expected in EXPECTED.items():
        data = (root/name).read_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError('Unexpected sample version: '+name)
        samples[name] = data, pefile.PE(data=data)
    main, pe = samples['3uTools.exe']
    strings = []
    for rva in [0x12b2390, 0x12b23a8, 0x12b23c0, 0x12b1420]:
        offset = pe.get_offset_from_rva(rva)
        strings.append({'rva': hex(rva), 'value': main[offset:offset+160].split(b'\0')[0].decode('ascii')})
    media, pe = samples['idm_media.dll']
    offset = pe.get_offset_from_rva(0x1bbb0)
    table = struct.unpack_from('<256H', media, offset)
    matches = all(table[i] == binascii.crc_hqx(bytes([i]), 0) for i in range(256))
    names = {p.name.lower() for p in root.rglob('*') if p.is_file()}
    return {'sample_sha256': EXPECTED, 'caller_constants': strings,
            'crc_table': {'rva': '0x1bbb0', 'all_256_entries_match_crc_hqx': matches},
            'required_names_present': {name: name.lower() in names
                for name in ['CoreFP.dll', 'AirTrafficHost.dll', 'iTunes.dll']},
            'limitations': 'Static evidence only; no HTTP request or DLL execution.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(json.dumps(inspect(args.directory), indent=2)+'\n', encoding='utf-8')
