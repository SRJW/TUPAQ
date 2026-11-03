"""Reproduce static evidence for the supplied idm_media.dll without loading it.

Requires pefile==2024.8.26 and GNU objdump. No third-party binary is distributed.
Known function boundaries below apply only to the SHA-256 checked here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import pefile

EXPECTED = '6fdaeb62646cba0e3fa72228fe320d63ce740440e36a5c31180e5494296496d2'
REGIONS = {
    'initialize_support': (0x7fe0, 0x8440),
    'http_transport': (0x8bd0, 0x8fa0),
    'alternate_processing': (0xa150, 0xa470),
    'open_services': (0x9110, 0x9390),
    'negotiate_sync': (0x9390, 0x9780),
    'build_metadata': (0xa7b0, 0xb060),
    'finish_metadata': (0xb060, 0xb1a0),
    'process_manifest': (0xc320, 0xc6d0),
    'add_media': (0xc6d0, 0xd230),
}
SELECTED = {
    'com.apple.afc', 'com.apple.atc', 'RequestingSync', 'ReadyForSync',
    'SyncAllowed', 'SyncFailed', 'Grappa', 'LibraryID', 'FinishedSyncingMetadata',
    'update_db_info', 'insert_track', 'operation', 'operations', 'revision',
    'timestamp', 'title', 'artist', 'album', 'total_time_ms', 'audio_format',
    'sample_rate', 'avformat_info', 'item_stats', 'location',
    'AssetManifest', 'AssetID', 'FileError', 'SyncFinished',
    '/iTunes_Control/Sync/Media/Sync_00000000.plist',
    '/iTunes_Control/Sync/Media/Sync_00000000.plist.cig',
    '\\iTunes.dll', '\\AirTrafficHost.dll', '\\CoreFP.dll',
}


def inspect(path):
    data = path.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    if digest != EXPECTED:
        raise ValueError('This module differs from the analyzed version; fixed function ranges do not apply.')
    pe = pefile.PE(data=data)
    base = pe.OPTIONAL_HEADER.ImageBase
    imports = {item.address: item.name.decode('ascii')
               for entry in pe.DIRECTORY_ENTRY_IMPORT for item in entry.imports if item.name}
    labels = {}
    for pattern, encoding, terminator in [(rb'[\x20-\x7e]{4,}\x00', 'ascii', 1),
                                         (rb'(?:[\x20-\x7e]\x00){4,}\x00\x00', 'utf-16le', 2)]:
        for match in re.finditer(pattern, data):
            value = match.group()[:-terminator].decode(encoding)
            if value in SELECTED:
                address = base + pe.get_rva_from_offset(match.start())
                labels[address] = {'value': value, 'file_offset': hex(match.start()),
                                   'rva': hex(address-base)}
    disassembly = subprocess.check_output(['objdump', '-d', '-M', 'intel', str(path)], text=True)
    regions = {key: {'start_rva': hex(lo), 'end_rva': hex(hi), 'references': [], 'calls': []}
               for key, (lo, hi) in REGIONS.items()}
    for line in disassembly.splitlines():
        instruction = re.match(r'\s*([0-9a-f]+):', line)
        if not instruction:
            continue
        address = int(instruction[1], 16)
        rva = address-base
        for name, (lo, hi) in REGIONS.items():
            if not lo <= rva < hi:
                continue
            ref = re.search(r'# (0x[0-9a-f]+)', line)
            target = int(ref[1], 16) if ref else None
            if target in labels:
                regions[name]['references'].append({'instruction_rva': hex(rva), **labels[target]})
            if re.search(r'\bcall\s', line):
                direct = re.search(r'\bcall\s+(0x[0-9a-f]+)', line)
                call = {'instruction_rva': hex(rva)}
                if target in imports:
                    call['import'] = imports[target]
                elif direct:
                    call['target_rva'] = hex(int(direct[1], 16)-base)
                elif target is not None:
                    call['indirect_slot_rva'] = hex(target-base)
                else:
                    call['unresolved'] = True
                regions[name]['calls'].append(call)
    return {'module': path.name, 'sha256': digest, 'preferred_image_base': hex(base),
            'method': 'static parsing and disassembly only; module not executed',
            'regions': regions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    report = inspect(args.module)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Static evidence written:', args.output)


if __name__ == '__main__':
    main()
