"""Read-only instruction pins for the exact user-provided iTunes.dll.

No native code execution, USB, uploads or unqualified lyrics transfer.
The checksum model is implemented independently in importios.sync.lyrics.
"""
import argparse,hashlib,json,struct
from pathlib import Path

REFERENCE='09c79c46f5bf77ce6ca7872ceaa9807104df03311c4ea3ea90abbcbdc35cc7c8'
# Small instruction pins identify each edge of the data flow, not string hits.
PINS={
    0xf5c3da:'e8a145a8ff', # call checksum producer
    0xf5c3e4:'894368', # store return value at record+0x68
    0x26236a:'837f6800', # builder tests the same field
    0x26239f:'ff7768', # its value is announced as lyrics.checksum
    0x2623a2:'68e46b4511', # checksum literal
    0x2623c2:'68c06b4511', # lyrics literal
    0x9e09ba:'e821ebf2ff', # copy CFString's UTF16 code units
    0x9e09dc:'e84f000000', # call reduction helper
    0x9e0a5a:'8d043f', # exactly length*2 bytes, no terminator
    0x9e0a90:'668b068d76020fb64eff66c1e008660bc866894c32fe4f75e7', # swap each UTF16 unit to BE
    0x9e0aa9:'ba01000000', # hash selector 1
    0x9e0ab4:'e857e1a8ff', # hash initializer
    0x46ec46:'c7460840e04610', # selector 1 -> MD5 initializer
    0x46ec51:'c7460ca0e04610', # MD5 final callback
    0x46ec58:'c7461080e04610', # MD5 update callback
    0x46e094:'e8c7b3bd00', # update -> MD5 streaming implementation
    0x1049506:'e8f54c2300', # streaming blocks -> compression
    0x127e22c:'8d842878a46ad7', # first MD5 round constant
    0x127e239:'c1c007', # MD5 first rotation 7
    0x46e0d4:'c7410410000000', # digest length 16 bytes
    0x9e0aef:'6a048d45dc', # four bytes at digest offset 0 (descriptor+8)
    0x9e0b2d:'8d45e06a04', # next word
    0x9e0b6b:'8d45e46a04', # next word
    0x9e0bab:'8d45e86a04', # last word
    0x9e0b77:'33da', # XOR word 2
    0x9e0bb7:'33da', # XOR word 3
    0x9e0beb:'33da7505bb01000000', # XOR word 4; zero -> 1
}


def inspect(path):
    import pefile # optional research dependency, not a desktop dependency
    data=Path(path).read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=REFERENCE:raise ValueError('unsupported-reference-hash')
    pe=pefile.PE(data=data)
    if pe.FILE_HEADER.Machine!=0x14c or pe.OPTIONAL_HEADER.ImageBase!=0x10000000:raise ValueError('unsupported-reference-profile')
    for rva,value in PINS.items():
        if pe.get_data(rva,len(bytes.fromhex(value)))!=bytes.fromhex(value):raise ValueError(f'unsupported-reference-pin:{rva:x}')
    return {'sha256':digest,'instruction_pins_checked':len(PINS),
            'host_checksum':'xor4be(md5(utf16be(text))); nonempty zero maps to one',
            'empty_checksum':0,'normalization':'none','bom':False,'terminator':False,
            'usb_asset_encoding_confirmed':False,'usb_asset_path_confirmed':False,
            'native_iphone_validation':False}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('dll',type=Path)
    print(json.dumps(inspect(parser.parse_args().dll),indent=2))
