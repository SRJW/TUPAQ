"""Read-only instruction pins for the user-supplied AMPDevicesAgent 1.7.0.155.
No execution, native loading, USB access or binary redistribution.
"""
import argparse,hashlib,json
from pathlib import Path

REFERENCE="9503c6084a662f594e79a22201dc579d127040ae38b56996b682d49e28710b10"
PINS={
    0x1bd00c:"488d0d29d38000ff15c75b680048890538b99c00", # Lyrics literal initializes the selected global
    0x32f36b:"420fb70c4f420fb6444f0166c1e108660bc86643890c4e", # Swap UTF-16 code units to big endian
    0x32f397:"e8fc233b00", # Checksum calls hash with selector 1
    0x6e1594:"83e901745a", # Hash selector 1 branch
    0x6e15f3:"488d0ddaf3ffff488d15dff3ffff488d05b8f3ffff", # MD5 callback table
    0x6e09d8:"e943430b00", # MD5 update trampoline
    0x794dbb:"e890000000", # Streaming calls MD5 block routine
    0x794f42:"4181c078a46ad7", # MD5 first constant d76aa478
    0x794f54:"41c1c007", # MD5 first rotation 7
    0x32f464:"33fb", # XOR digest words
    0x32f497:"33df", # XOR digest words
    0x32f4bf:"3bd374048bf233f3", # Nonempty zero fold maps to 1
    0x32f5a1:"4533c941b800010008488bd333c9ff155b3a5100", # Exact CFString UTF-8 external representation, loss byte zero
    0x466c06:"e8ed88ecff", # USB preparation calls this serializer
    0x466cde:"e835640100", # Same preparation obtains filename from AssetID
    0x466d28:"4c8d4d904d8bc5488bd6488b4c2478ff542430", # Writer receives CFData, folder and name
    0x466ee7:"837c243002480f441d641a7200", # Track class 2 selects Lyrics subfolder global
    0x466f08:"e8c7e0ffff", # Folder helper called for Media/Lyrics
    0x466f32:"e8e5f9ffff", # Dispatch invokes USB lyrics preparation
    0x47cf6a:"41b86c726961", # Airlock folder type
    0x47d18e:"e8d52a2500", # Filename copies AssetID without extension
    0x467032:"41b908000000", # Completion accounts for part 8
    0x464d9e:"418bc7f7d04423f00f84cd000000", # Completion removes finished bit and waits for remaining parts
    0x472304:"418b5f7c488d0d21eb5300", # Metadata reads checksum field and checksum key
    0x47232b:"488d0d0aeb5300", # Metadata nests under lyrics key
}

def inspect(path):
    import pefile # research only; not a desktop dependency
    data=Path(path).read_bytes();digest=hashlib.sha256(data).hexdigest()
    if digest!=REFERENCE:raise ValueError("unsupported-reference-hash")
    pe=pefile.PE(data=data,fast_load=True)
    if pe.FILE_HEADER.Machine!=0x8664 or pe.OPTIONAL_HEADER.ImageBase!=0x140000000:raise ValueError("unsupported-reference-profile")
    for rva,expected in PINS.items():
        value=bytes.fromhex(expected)
        if pe.get_data(rva,len(value))!=value:raise ValueError(f"unsupported-reference-pin:{rva:x}")
    if pe.get_data(0x9ca33c,7)!=b"Lyrics\0":raise ValueError("unsupported-folder-literal")
    return {"sha256":digest,"instruction_pins_checked":len(PINS),
            "encoding":"UTF-8 CFString external representation",
            "track_staging_path":"/Airlock/Media/Lyrics/<bare AssetID>",
            "metadata":"item.lyrics.checksum", "asset_part":8,
            "timed_usb_delivery_verified":False,"native_iphone_validation":False}

if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("exe",type=Path)
    print(json.dumps(inspect(parser.parse_args().exe),indent=2))
