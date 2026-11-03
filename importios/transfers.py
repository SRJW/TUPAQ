"""USB audio export and bounded, additive ATC import with local receipts.

ATC mechanisms follow rustunes 057ee8fc (MIT); see sync/protocol.py and
third_party/rustunes-LICENSE.txt. Never writes SQLite on the phone, never sends
a reset sync and never retries a metadata transaction automatically.
"""
import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shutil
import string
import tempfile
import uuid

from .library import LibraryError, copy_catalogue
from .phone_paths import media_path
from .sync.catalogue import snapshot, verify_before_after
from .sync.protocol import Atc, ProtocolError, require, library_identity, saved_anchors, handshake, encode_operations, validate_manifest
from .sync.source import inspect_source

CHUNK = 1024*1024
MAX_AUDIO = 2*1024*1024*1024
MEDIA = '/iTunes_Control/Sync/Media'
PREF = '/iTunes_Control/iTunes/'


class TransferError(LibraryError):
    pass


@asynccontextmanager
async def device():
    from pymobiledevice3 import usbmux
    from pymobiledevice3.lockdown import create_using_usbmux
    from pymobiledevice3.services.afc import AfcService
    devices = [d for d in await usbmux.list_devices() if d.is_usb]
    require(len(devices) == 1, 'usb-device-count')
    lockdown = await create_using_usbmux(serial=devices[0].serial, connection_type='USB',autopair=False,label='TUPAQ')
    async with lockdown:
        require(lockdown.paired and lockdown.session_id, 'trust-missing')
        async with AfcService(lockdown) as afc:
            yield lockdown, afc


async def missing(afc, path):
    from pymobiledevice3.services.afc import AfcFileNotFoundError
    try:
        await afc.stat(path)
        return False
    except (FileNotFoundError, AfcFileNotFoundError):
        return True


async def read_remote(afc, path, output=None, limit=MAX_AUDIO, progress=None):
    before = await afc.stat(path)
    size = before.get('st_size')
    require(before.get('st_ifmt') == 'S_IFREG' and type(size) is int and 0 <= size <= limit, 'remote-file-size')
    handle = await afc.fopen(path,'r')
    digest, blocks, done = hashlib.sha256(), [], 0
    try:
        while done < size:
            block = await afc.fread(handle,min(CHUNK,size-done))
            require(bool(block) and len(block) <= size-done, 'remote-file-truncated')
            digest.update(block)
            if output is not None:
                output.write(block)
            elif limit <= 64*1024*1024:
                blocks.append(block)
            done += len(block)
            if progress:
                progress(done,max(1,size))
    finally:
        await afc.fclose(handle)
    after = await afc.stat(path)
    require(all(before.get(k) == after.get(k) for k in ('st_size','st_mtime','st_ifmt')), 'remote-file-changed')
    return b''.join(blocks), digest.hexdigest(), size


def local_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def export_name(track):
    title = f"{track.get('artist') or 'Sin artista'} - {track.get('title') or 'Sin título'}"
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',title).strip(' .')[:120] or 'Canción'
    if title.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        title = '_'+title
    return title+PurePosixPath(track['afc_path']).suffix.lower()


def retain_export(temporary, folder, filename):
    """Exclusive creation, including on FAT/exFAT; never replaces an existing song."""
    proposed = Path(filename)
    for counter in range(10000):
        name = filename if counter == 0 else f'{proposed.stem} ({counter+1}){proposed.suffix}'
        destination = folder/name
        try:
            target = destination.open('xb')
        except FileExistsError:
            continue
        try:
            with target, Path(temporary).open('rb') as source:
                shutil.copyfileobj(source,target,CHUNK)
                target.flush()
                os.fsync(target.fileno())
        except BaseException:
            destination.unlink(missing_ok=True)
            raise
        return destination
    raise ProtocolError('export-name-collisions')


async def export_selected(selected, folder, progress):
    folder = Path(folder).resolve()
    require(folder.is_dir() and 1 <= len(selected) <= 1000, 'export-selection')
    result = []
    async with device() as (_, afc):
        with tempfile.TemporaryDirectory(prefix='.tupaq-export-',dir=folder) as temporary:
            catalogue = Path(temporary)/'catalogue'
            catalogue.mkdir()
            from pymobiledevice3.services.afc import AfcFileNotFoundError
            tracks = await copy_catalogue(afc,catalogue,(FileNotFoundError,AfcFileNotFoundError))
            fresh = {t['id']:t for t in tracks}
            # Validate the full selection before exporting the first file.
            for chosen in selected:
                current = fresh.get(chosen.get('id'))
                require(current is not None and all(current.get(k) == chosen.get(k) for k in ('title','artist','afc_path')),
                        'export-stale-selection')
                require(bool(current.get('afc_path')), 'export-no-usb-file')
            for index, chosen in enumerate(selected):
                track = fresh[chosen['id']]
                destination_name = export_name(track)
                temporary_audio = Path(temporary)/'audio.part'
                def bytes_progress(done,total):
                    progress(index*100+int(done*80/total),len(selected)*100,'Exportando: '+track['title'])
                with temporary_audio.open('wb') as output:
                    _, digest, size = await read_remote(afc,track['afc_path'],output=output,progress=bytes_progress)
                require(size > 0, 'export-empty-audio')
                _, check, check_size = await read_remote(afc,track['afc_path'])
                require(size == check_size and digest == check == local_hash(temporary_audio), 'export-hash')
                result.append(str(retain_export(temporary_audio,folder,destination_name)))
                temporary_audio.unlink()
                progress((index+1)*100,len(selected)*100,'Exportada: '+track['title'])
    return {'exported':len(result),'files':result}


def save_receipt(directory, receipt):
    temporary = directory/'journal.next'
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(receipt,stream,ensure_ascii=True,indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    os.replace(temporary,directory/'journal.json')


async def capture(afc, directory):
    directory.mkdir()
    from pymobiledevice3.services.afc import AfcFileNotFoundError
    await copy_catalogue(afc,directory,(FileNotFoundError,AfcFileNotFoundError))
    return snapshot(directory/'1'/'MediaLibrary.sqlitedb')


async def preferences(afc, directory, before):
    identity = None
    for name in ('iTunesPrefs','iTunesPrefs.plist'):
        path = PREF+name
        if await missing(afc,path):
            continue
        data, _, _ = await read_remote(afc,path,limit=1024*1024)
        value = library_identity(data)
        require(identity is None or value == identity, 'identity-conflict')
        identity = value
        target = directory/name
        target.write_bytes(data)
        target.chmod(0o600)
    require(identity is not None, 'identity-missing')
    host = None
    for name in ('iTunesCDB','iTunesDB'):
        path = PREF+name
        if await missing(afc,path):
            continue
        data, _, _ = await read_remote(afc,path,limit=64*1024*1024)
        parsed = saved_anchors(data)
        require(parsed['database'] == (before['database'] & ((1<<64)-1)), 'host-catalogue-identity')
        require(host is None or parsed == host, 'host-anchor-conflict')
        host = parsed
        target = directory/name
        target.write_bytes(data)
        target.chmod(0o600)
    require(host is not None and host['voice'] == 1 and host['media'] <= before['anchor'], 'host-anchor-unavailable')
    return identity,host['voice']


async def check_empty_staging(afc):
    require(not await missing(afc,MEDIA), 'staging-directory-missing')
    files = await afc.listdir(MEDIA)
    require(all(name in ('.','..') for name in files), 'staging-not-empty')


async def available_path(afc, before, source):
    folders = sorted({str(PurePosixPath(t['afc_path']).parent) for t in before['tracks'].values()
        if t.get('afc_path') and re.fullmatch(r'iTunes_Control/Music/F[0-9]{2}',str(PurePosixPath(t['afc_path']).parent))})
    if not folders:
        folders = ['iTunes_Control/Music/F00']
    for folder in folders:
        if await missing(afc,folder):
            continue
        require((await afc.stat(folder)).get('st_ifmt') == 'S_IFDIR', 'music-directory-kind')
        for _ in range(128):
            leaf = ''.join(secrets.choice(string.ascii_uppercase) for _ in range(4))+source['extension']
            destination = media_path(folder,leaf)
            require(destination is not None, 'music-path')
            if await missing(afc,destination) and not any(t.get('afc_path','').lower() == destination.lower()
                    for t in before['tracks'].values() if t.get('afc_path')):
                return destination
    raise ProtocolError('music-directory-unavailable')


def allocate_id(reserved):
    while True:
        identifier = secrets.randbits(63)
        if identifier >= 1000 and identifier not in reserved:
            reserved.add(identifier)
            return identifier


async def plan_entries(afc, before, sources):
    reserved = set(before['ids'])
    artists = {k:v[0] for k,v in before['artists'].items() if len(v) == 1}
    albums = {k:v[0] for k,v in before['albums'].items() if len(v) == 1}
    entries, destinations = [], set()
    for source in sources:
        artist = source['album_artist']
        if artist not in artists:
            artists[artist] = allocate_id(reserved)
        album = (source['album'],artist)
        if album not in albums:
            albums[album] = allocate_id(reserved)
        destination = await available_path(afc,before,source)
        require(destination.lower() not in destinations, 'plan-path-collision')
        destinations.add(destination.lower())
        entry = {'track_id':allocate_id(reserved),'album_id':albums[album],'artist_id':artists[artist],
                 'destination':destination,'source':source}
        for suffix in (source['extension'],''):
            require(await missing(afc,f"/Airlock/Media/{entry['track_id']}{suffix}"), 'airlock-collision')
        entries.append(entry)
    return entries


async def write_bytes(afc, path, data):
    require(await missing(afc,path), 'staged-file-exists')
    handle = await afc.fopen(path,'w')
    try:
        await afc.fwrite(handle,data)
    finally:
        await afc.fclose(handle)
    _, digest, size = await read_remote(afc,path,limit=4*1024*1024)
    require(size == len(data) and digest == hashlib.sha256(data).hexdigest(), 'staged-file-hash')


async def upload_audio(afc, entry, progress):
    source = entry['source']
    path = f"/Airlock/Media/{entry['track_id']}{source['extension']}"
    bare = f"/Airlock/Media/{entry['track_id']}"
    require(await missing(afc,path) and await missing(afc,bare) and await missing(afc,entry['destination']), 'upload-collision')
    require(local_hash(source['path']) == source['id'], 'source-changed-before-upload')
    handle = await afc.fopen(path,'w')
    digest, done = hashlib.sha256(), 0
    try:
        with Path(source['path']).open('rb') as stream:
            while block := stream.read(CHUNK):
                await afc.fwrite(handle,block)
                digest.update(block)
                done += len(block)
                progress(done,source['size'])
    finally:
        await afc.fclose(handle)
    require(done == source['size'] and digest.hexdigest() == source['id'], 'source-changed-during-upload')
    _, check, size = await read_remote(afc,path)
    require(size == source['size'] and check == source['id'], 'upload-hash')
    require(await missing(afc,bare), 'airlock-rename-collision')
    await afc.rename(path,bare)


async def transact(afc, channel, before, identity, voice, entries, receipt, directory, progress):
    await check_empty_staging(afc)
    signer = await handshake(channel,identity,before['anchor'],voice)
    try:
        await check_empty_staging(afc)
        # Reconcile the live catalogue once more before any operation is staged.
        with tempfile.TemporaryDirectory(prefix='tupaq-recheck-') as temporary:
            current = await capture(afc,Path(temporary)/'catalogue')
            checked_prefs = Path(temporary)/'preferences'
            checked_prefs.mkdir()
            current_identity, current_voice = await preferences(afc,checked_prefs,current)
            require(current_identity == identity and current_voice == voice, 'identity-changed-before-stage')
        require(current['anchor'] == before['anchor'] and current['database'] == before['database'] and
                current['primary'] == before['primary'] and current['tracks'] == before['tracks'] and
                current['originals'] == before['originals'] and current['wire_to_item'] == before['wire_to_item'], 'catalogue-changed-before-stage')
        operation = encode_operations(before['database'],before['primary'],before['anchor'],entries)
        signature = signer.sign(operation)
        receipt['phase'] = 'staging'
        save_receipt(directory,receipt)
        await write_bytes(afc,MEDIA+'/Sync_00000000.plist',operation)
        await write_bytes(afc,MEDIA+'/Sync_00000000.plist.cig',signature)
        receipt['phase'] = 'metadata-announced'
        save_receipt(directory,receipt)
        await channel.send({'Command':'FinishedSyncingMetadata','Session':2,'Params':{
            'DataclassAnchors':{'Media':str(before['anchor']+1),'VoiceMemo':str(voice)},
            'SyncTypes':{'Media':1,'Book':0,'Keybag':1}}})
        own = {str(e['track_id']):e for e in entries}
        manifest_seen, completed = False, set()
        for _ in range(256):
            message = await channel.receive()
            require(message.get('Session') == 2, 'terminal-session')
            command = message.get('Command')
            require(command not in ('SyncFailed','ConnectionInvalid','FileError'), 'device-sync-failed')
            if command == 'AssetManifest':
                require(not manifest_seen, 'manifest-repeated')
                existing_music = {wire for wire,item in before['wire_to_item'].items() if item in before['tracks']}
                audio, ancillary = validate_manifest(message,set(own),existing_music)
                manifest_seen = True
                # Every request is checked before any completion/refusal is sent.
                for index, identifier in enumerate(audio):
                    entry = own[identifier]
                    def bytes_progress(done,total):
                        progress(index*100+int(done*80/max(1,total)),len(entries)*100,'Importando: '+entry['source']['title'],entry['source']['id'])
                    await upload_audio(afc,entry,bytes_progress)
                    await channel.send({'Command':'FileComplete','Session':2,'Params':{
                        'AssetID':identifier,'Dataclass':'Media','AssetPath':entry['destination']}})
                    completed.add(identifier)
                    receipt['completed_assets'] = sorted(completed)
                    save_receipt(directory,receipt)
                for identifier in ancillary:
                    await channel.send({'Command':'FileError','Session':2,'Params':{
                        'AssetID':identifier,'Dataclass':'Media','ErrorCode':16,'ErrorIsVisible':False}})
            elif command == 'SyncFinished':
                require(completed == set(own), 'finished-without-audio')
                receipt['phase'] = 'verifying'
                save_receipt(directory,receipt)
                return
            elif command != 'SyncAllowed':
                raise ProtocolError('terminal-command')
        raise ProtocolError('terminal-limit')
    finally:
        signer.close()


async def import_selected(selected, backup_root, progress):
    require(1 <= len(selected) <= 49, 'import-selection-limit')
    require(sum(Path(chosen['path']).stat().st_size for chosen in selected) <= 2*1024*1024*1024, 'import-batch-size')
    sources, hashes = [], set()
    for chosen in selected:
        source = inspect_source(chosen['path'],chosen.get('id'))
        require(source['id'] not in hashes, 'duplicate-source')
        hashes.add(source['id'])
        sources.append(source)
    require(sum(s['size'] for s in sources) <= 2*1024*1024*1024, 'import-batch-size')
    root = Path(backup_root)
    root.mkdir(parents=True,exist_ok=True)
    completed_receipts = []
    for journal in root.glob('*/journal.json'):
        record = json.loads(journal.read_text(encoding='utf-8'))
        require(record.get('phase') in ('completed','before-write-failed'), 'previous-import-unverified')
        if record.get('phase') == 'completed':
            matches = [{'track_id':e['track_id'],'destination':e['destination'],
                        'source':{'id':e['source']['id'],'size':e['source']['size']}}
                       for e in record.get('entries',[]) if e['source']['id'] in hashes]
            if matches:
                completed_receipts.append({'database':record.get('database'),'primary':record.get('primary'),'entries':matches})
    directory = root/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    receipt = {'phase':'preflight','entries':[]}
    save_receipt(directory,receipt)
    try:
        async with device() as (lockdown, afc):
            # The OS library lock coordinates with other desktop sync clients.
            from pymobiledevice3.services.afc import AFC_LOCK_EX, AFC_LOCK_UN
            lock = await afc.fopen('/com.apple.itunes.lock_sync','a+')
            locked = False
            try:
                await afc.lock(lock,AFC_LOCK_EX)
                locked = True
                progress(0,100,'Guardando una copia del catálogo…')
                before = await capture(afc,directory/'before')
                already = set()
                for old in completed_receipts:
                    if (old.get('database'),old.get('primary')) != (before['database'],before['primary']):
                        continue
                    for entry in old.get('entries',[]):
                        if entry['source']['id'] not in hashes:
                            continue
                        identifier = before['wire_to_item'].get(str(entry['track_id']))
                        track = before['tracks'].get(identifier,{})
                        if track.get('afc_path') != entry['destination'] or await missing(afc,entry['destination']):
                            continue
                        _, check, size = await read_remote(afc,entry['destination'])
                        if check == entry['source']['id'] and size == entry['source']['size']:
                            already.add(check)
                sources = [s for s in sources if s['id'] not in already]
                if not sources:
                    receipt.update(phase='completed',database=before['database'],primary=before['primary'])
                    save_receipt(directory,receipt)
                    return {'imported':0,'already_imported':len(already),'source_ids':list(hashes),'backup':str(directory)}
                identity, voice = await preferences(afc,directory,before)
                await check_empty_staging(afc)
                entries = await plan_entries(afc,before,sources)
                receipt.update(entries=entries,anchor=before['anchor'],database=before['database'],primary=before['primary'])
                save_receipt(directory,receipt)
                connection = await lockdown.start_lockdown_service('com.apple.atc')
                async with Atc(connection) as channel:
                    await transact(afc,channel,before,identity,voice,entries,receipt,directory,progress)
                progress(90,100,'Comprobando las canciones en la biblioteca…')
                after = await capture(afc,directory/'after')
                verify_before_after(before,after,entries)
                for entry in entries:
                    _, digest, size = await read_remote(afc,entry['destination'])
                    require(size == entry['source']['size'] and digest == entry['source']['id'], 'verify-permanent-audio')
                receipt['phase'] = 'completed'
                save_receipt(directory,receipt)
                progress(100,100,'Importación comprobada en el catálogo.')
                return {'imported':len(entries),'already_imported':len(already),'source_ids':list(hashes),'backup':str(directory)}
            finally:
                if locked:
                    with suppress(Exception):
                        await afc.lock(lock,AFC_LOCK_UN)
                await afc.fclose(lock)
    except BaseException:
        if receipt['phase'] == 'preflight':
            receipt['phase'] = 'before-write-failed'
        save_receipt(directory,receipt)
        raise


def transfer_error(error, mode):
    code = str(error) if isinstance(error,ProtocolError) else type(error).__name__
    status = getattr(error,'status',None)
    if status is not None and not isinstance(error,ProtocolError):
        with suppress(TypeError,ValueError):
            if 0 <= int(status) <= 65535:
                code += '-'+str(int(status))
    if mode == 'export':
        message = 'No se completó la exportación. Los archivos ya exportados se conservan; no se modificó el iPhone.'
    else:
        message = 'La importación se detuvo o no pudo verificarse. Revisa el diagnóstico y el respaldo del catálogo antes de repetirla.'
    messages = {
        'previous-import-unverified':'Hay una importación anterior sin comprobar. Pulsa Revisar importación antes de enviar otra.',
        'identity-not-configured':'No se encontró una identidad de sincronización configurada en el iPhone. No se ha enviado una actualización de biblioteca.',
        'identity-missing':'No se encontró la identidad existente de la biblioteca. No se ha enviado una actualización de biblioteca.',
        'host-anchor-unavailable':'El estado de sincronización guardado no es compatible todavía. No se ha enviado una actualización de biblioteca.',
        'import-selection-limit':'Selecciona entre 1 y 49 canciones por importación.',
        'export-no-usb-file':'Ese audio no está disponible como archivo accesible por USB. Puede conservar metadatos aunque iOS no exponga el archivo.',
        'export-stale-selection':'La biblioteca cambió. Vuelve a leerla y selecciona otra vez las canciones que quieras exportar.',
        'pending-import-count':'No se encontró una única importación pendiente para comprobar. Consulta Ver respaldo.',
        'source-changed':'El archivo del ordenador cambió desde que lo elegiste. Quítalo de la lista y vuelve a añadirlo.',
        'pcm-profile':'La importación de WAV/AIFF admite PCM de 8, 16 o 24 bits, mono o estéreo. Este archivo necesita otro perfil.',
        'wav-not-integer-pcm':'Este WAV no usa el perfil PCM entero admitido por esta versión. No se ha enviado una actualización de biblioteca.',
        'aac-profile':'El perfil AAC de este M4A no está admitido por la importación actual.',
        'alac-profile':'El perfil ALAC de este archivo no está admitido por la importación actual.',
    }
    message = messages.get(code,message)
    return TransferError(message, mode+':'+code)


async def verify_pending(backup_root, progress):
    root = Path(backup_root)
    pending = []
    for journal in sorted(root.glob('*/journal.json')):
        record = json.loads(journal.read_text(encoding='utf-8'))
        if record.get('phase') not in ('completed','before-write-failed'):
            pending.append((journal,record))
    require(len(pending) == 1, 'pending-import-count')
    journal, receipt = pending[0]
    require(bool(receipt.get('entries')), 'pending-no-entries')
    before = snapshot(journal.parent/'before'/'1'/'MediaLibrary.sqlitedb')
    async with device() as (_,afc):
        with tempfile.TemporaryDirectory(prefix='tupaq-verify-') as temporary:
            after = await capture(afc,Path(temporary)/'catalogue')
            verify_before_after(before,after,receipt['entries'])
        for index, entry in enumerate(receipt['entries']):
            _, digest, size = await read_remote(afc,entry['destination'])
            require(digest == entry['source']['id'] and size == entry['source']['size'], 'verify-permanent-audio')
            progress(index+1,len(receipt['entries']),'Comprobando la importación pendiente…')
    receipt['phase'] = 'completed'
    save_receipt(journal.parent,receipt)
    return {'verified':len(receipt['entries']),'source_ids':[e['source']['id'] for e in receipt['entries']],'backup':str(journal.parent)}


def run_transfer(mode, selected, destination, progress):
    try:
        require(mode in ('import','export','verify'), 'transfer-mode')
        work = (import_selected(selected,destination,progress) if mode == 'import' else
                verify_pending(destination,progress) if mode == 'verify' else export_selected(selected,destination,progress))
        return asyncio.run(asyncio.wait_for(work,timeout=1800))
    except Exception as error:
        raise transfer_error(error,mode) from None
