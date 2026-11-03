"""Bounded ATC delta-insert protocol, adapted from rustunes (MIT).

Reference: fbiba/rustunes 057ee8fc, protocol/{templates,alac,mpeg,session}.rs
and catalogue/{identity,anchor}.rs. Copyright (c) 2026 Feim Biba.
See third_party/rustunes-LICENSE.txt. No Apple/3uTools DLL is executed.
"""
import asyncio
from contextlib import suppress
from datetime import datetime, timezone
import plistlib
import struct
import zlib

from .signing import HOST_REQUEST, FixedHostSession


class ProtocolError(Exception):
    """Only fixed diagnostic codes, never remote payloads or private identities."""


def require(condition, code):
    if not condition:
        raise ProtocolError(code)


def library_identity(data):
    require(len(data) <= 1024*1024, 'identity-size')
    if not data.startswith(b'frpd'):
        try:
            data = plistlib.loads(data).get('iPodPrefs')
        except Exception:
            raise ProtocolError('identity-plist') from None
    require(isinstance(data, bytes) and len(data) == 1232, 'identity-layout')
    require(data[:4] == b'frpd' and struct.unpack_from('<HH', data, 4) == (1,25), 'identity-version')
    require(data[8] == 1, 'identity-not-configured')
    first, second = struct.unpack_from('<QQ', data, 12)
    require(first and second and first != second, 'identity-zero')
    return (first, second)


def saved_anchors(data):
    require(244 <= len(data) <= 64*1024*1024, 'host-catalogue-size')
    endian = '<' if data[:4] == b'mhbd' else '>' if data[:4] == b'dbhm' else None
    require(endian is not None, 'host-catalogue-magic')
    def number(offset):
        return struct.unpack_from(endian+'I', data, offset)[0]
    require(number(4) == 244 and number(8) == len(data) and number(16) == 117, 'host-catalogue-layout')
    count = number(20)
    require(1 <= count <= 4096, 'host-catalogue-sections')
    database = struct.unpack_from(endian+'Q', data, 72)[0]
    major, compressed = number(12), data[168]
    body = data[244:]
    if (major, compressed) == (2,1):
        decoder = zlib.decompressobj()
        body = decoder.decompress(body, 256*1024*1024+1)
        require(len(body) <= 256*1024*1024 and decoder.eof and not decoder.unused_data and not decoder.unconsumed_tail,
                'host-catalogue-compression')
    else:
        require((major,compressed) == (1,0), 'host-catalogue-version')
    anchors = None
    offset = 0
    for _ in range(count):
        require(offset+16 <= len(body), 'host-section-truncated')
        magic, header, total, kind = struct.unpack_from(endian+'IIII', body, offset)
        require(magic == 0x6473686d and 16 <= header <= total <= len(body)-offset, 'host-section-layout')
        if kind == 11:
            require(anchors is None and header == 96 and total == 144, 'host-anchor-layout')
            anchors = struct.unpack_from(endian+'IIII', body, offset+header)
        offset += total
    require(offset == len(body) and anchors is not None, 'host-anchor-missing')
    return {'database': database, 'media': anchors[0], 'voice': anchors[2]}


def request_template(identity, anchor, voice):
    require(type(anchor) is int and 0 < anchor < 0xffffffff and voice == 1, 'anchor-not-qualified')
    return {'Command':'RequestingSync','Session':2,'Params':{
        'Dataclasses':['Media','Book','Keybag'],
        'DataclassAnchors':{'Media':str(anchor),'VoiceMemo':str(voice)},
        'HostInfo':{'Type':'iTunes','Version':'13.2.4.123','WindowsOSVersion':'10.0',
                    'SyncHostName':'TUPAQ','LibraryID':f'{identity[0]^identity[1]:016X}',
                    'SyncedDataclasses':['Media'],'SyncedAssetTypes':['Music'],
                    'Wakeable':0,'Grappa':HOST_REQUEST}}}


def encode_operations(database, primary, anchor, entries):
    require(database and primary and 1 <= len(entries) <= 49, 'operation-scope')
    operations = [{'operation':'update_db_info','pid':database,'db_info':{'primary_container_pid':primary}}]
    for entry in entries:
        source = entry['source']
        item = {'album_pid':entry['album_id'],'artist_pid':entry['artist_id'],
                'title':source['title'],'artist':source['artist'],'album':source['album'],
                'sort_name':source['title'],'sort_artist':source['artist'],'sort_album':source['album'],
                'album_artist':source['album_artist'],'sort_album_artist':source['album_artist'],
                'is_song':True,'remember_bookmark':False,'artwork_checksum':0,
                'total_time_ms':source['samples']*1000//source['sample_rate']}
        for key in ['genre','composer','year','track_number','track_count','disc_number','disc_count']:
            if source.get(key):
                item[key] = source[key]
        if item.get('composer'):
            item['sort_composer'] = item['composer']
        audio = {'audio_format':source['audio_format'],'bit_rate':source['bit_rate'],
                 'sample_rate':float(source['sample_rate']),'channels':source['channels'],
                 'duration':source['samples']}
        if source['format'] == 'MP3':
            # No independent Xing/LAME gapless projection is implemented here.
            # Use the qualified Timing::Omitted form; let iOS parse the MP3.
            audio.pop('duration')
            item.pop('total_time_ms')
        if source['format'] == 'ALAC':
            audio.update(gapless_encoding_delay=0,gapless_encoding_drain=0,
                         gapless_heuristic_info=1,gapless_last_frame_resynch=0,analysis_inhibit_flags=2)
        operations.append({'operation':'insert_track','pid':entry['track_id'],'item':item,
                           'avformat_info':audio,'location':{'kind':source['kind']},
                           'item_stats':{'play_count_recent':0,'play_count_user':0,'skip_count_recent':0,
                                         'skip_count_user':0,'has_been_played':False}})
    result = plistlib.dumps({'revision':anchor+1,'timestamp':datetime.now(timezone.utc).replace(tzinfo=None),'operations':operations},
                           fmt=plistlib.FMT_BINARY,sort_keys=False)
    require(len(result) <= 4*1024*1024, 'operation-size')
    return result


class Atc:
    def __init__(self, connection):
        self.connection = connection
        self.queue = asyncio.Queue(128)
        self.write_lock = asyncio.Lock()
        self.task = None
        self.broken = False

    async def __aenter__(self):
        self.task = asyncio.create_task(self._pump())
        return self

    async def __aexit__(self, *ignored):
        self.broken = True
        self.task.cancel()
        with suppress(asyncio.CancelledError):
            await self.task
        await self.connection.close()

    async def send(self, message):
        require(not self.broken, 'atc-closed')
        raw = plistlib.dumps(message,fmt=plistlib.FMT_BINARY,sort_keys=False)
        require(len(raw) <= 16*1024*1024, 'atc-frame-size')
        try:
            async with self.write_lock:
                await self.connection.sendall(struct.pack('<I',len(raw))+raw)
        except BaseException:
            self.broken = True
            raise

    async def _pump(self):
        try:
            while True:
                header = await self.connection.recvall(4)
                require(len(header) == 4, 'atc-header')
                size = struct.unpack('<I',header)[0]
                require(0 < size <= 16*1024*1024, 'atc-frame-size')
                raw = await self.connection.recvall(size)
                require(len(raw) == size and raw.startswith(b'bplist00'), 'atc-payload')
                message = plistlib.loads(raw)
                require(isinstance(message,dict) and type(message.get('Session')) is int, 'atc-envelope')
                if message.get('Command') == 'Ping':
                    require(message['Session'] == 2, 'atc-ping-session')
                    await self.send({'Command':'Pong','Session':2})
                elif message.get('Command') not in ('Progress','AssetMetrics','InstalledAssets'):
                    self.queue.put_nowait(message)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            self.broken = True
            if self.queue.full():
                self.queue.get_nowait()
            self.queue.put_nowait(error)

    async def receive(self):
        result = await asyncio.wait_for(self.queue.get(), timeout=90)
        if isinstance(result, Exception):
            raise result
        if result.get('Command') in ('SyncFailed','ConnectionInvalid','FileError'):
            code = result.get('Params',{}).get('ErrorCode')
            suffix = '-'+str(code) if type(code) is int and 0 <= code <= 255 else ''
            raise ProtocolError('atc-device-rejected'+suffix)
        return result


async def handshake(channel, identity, anchor, voice):
    await channel.send({'Command':'Ping','Session':1})
    pong = capable = allowed = requested = False
    for _ in range(64):
        message = await channel.receive()
        command, params = message.get('Command'), message.get('Params',{})
        require(isinstance(params,dict), 'handshake-params')
        if command == 'Pong':
            require(not requested, 'handshake-late-pong')
            pong = True
        elif command == 'Capabilities':
            require(params.get('GrappaSupportInfo') == {'version':1,'deviceType':0,'protocolVersion':1}, 'grappa-capabilities')
            capable = True
        elif command == 'SyncAllowed':
            require(params.get('DataProtected') is False and
                    (params.get('ManualSync') is True or params.get('AutoSync') is True) and
                    'Music' not in params.get('DisabledAssetTypes',[]), 'sync-not-allowed')
            allowed = True
        elif command == 'ReadyForSync':
            require(requested and message.get('Session') == 2, 'ready-session')
            require(params.get('DataclassAnchors',{}).get('Media') == str(anchor), 'anchor-mismatch')
            reply = params.get('DeviceInfo',{}).get('Grappa')
            require(isinstance(reply,bytes), 'grappa-reply')
            try:
                return FixedHostSession(HOST_REQUEST,reply)
            except ValueError:
                raise ProtocolError('grappa-envelope') from None
        else:
            raise ProtocolError('handshake-command')
        if pong and capable and allowed and not requested:
            await channel.send(request_template(identity,anchor,voice))
            requested = True
    raise ProtocolError('handshake-limit')


def validate_manifest(message, own_ids, existing_ids):
    require(message.get('Session') == 2, 'manifest-session')
    manifest = message.get('Params',{}).get('AssetManifest',{})
    require(isinstance(manifest,dict) and set(manifest) == {'Media'}, 'manifest-dataclasses')
    assets = manifest['Media']
    require(isinstance(assets,list) and 1 <= len(assets) <= 1024, 'manifest-size')
    seen, audio, ancillary = set(), [], []
    for asset in assets:
        require(isinstance(asset,dict) and asset.get('AssetType') == 'Music' and asset.get('IsDownload') is True, 'manifest-kind')
        identifier, parts = asset.get('AssetID'), asset.get('Variant',{}).get('AssetParts')
        require(isinstance(identifier,str) and identifier not in seen and type(parts) is int, 'manifest-record')
        seen.add(identifier)
        if identifier in own_ids:
            require(parts == 1, 'manifest-own-parts')
            audio.append(identifier)
        else:
            require(identifier in existing_ids and parts in (2,4), 'manifest-unknown-asset')
            ancillary.append(identifier)
    require(set(audio) == set(own_ids), 'manifest-missing-audio')
    return audio, ancillary
