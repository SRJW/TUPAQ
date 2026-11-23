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
import time
import uuid

from .library import LibraryError, copy_catalogue
from .cancellation import CURRENT,TransferControl,TransferCancelled,checkpoint,begin_commit
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
        from .devices import device_token
        lockdown._tupaq_device_token=device_token(devices[0].serial)
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
    checkpoint()
    before = await afc.stat(path)
    size = before.get('st_size')
    require(before.get('st_ifmt') == 'S_IFREG' and type(size) is int and 0 <= size <= limit, 'remote-file-size')
    handle = await afc.fopen(path,'r')
    digest, blocks, done = hashlib.sha256(), [], 0
    try:
        while done < size:
            checkpoint()
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


def _safe_component(text, fallback='Sin nombre'):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', str(text or '')).strip(' .')[:100] or fallback
    if value.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        value = '_'+value
    return value


def export_name(track):
    title = f"{track.get('artist') or 'Sin artista'} - {track.get('title') or 'Sin título'}"
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_',title).strip(' .')[:120] or 'Canción'
    if title.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        title = '_'+title
    return title+PurePosixPath(track['afc_path']).suffix.lower()


def export_relative_path(track, structure='flat'):
    """Return relative target Path inside the destination folder."""
    if structure == 'artist_album':
        artist = _safe_component(track.get('artist') or 'Sin artista', 'Sin artista')
        album = _safe_component(track.get('album') or 'Sin álbum', 'Sin álbum')
        title = _safe_component(track.get('title') or 'Sin título', 'Canción')
        num = track.get('track_number')
        prefix = f'{num:02d} - ' if type(num) is int and 0 < num <= 999 else ''
        suffix = PurePosixPath(track['afc_path']).suffix.lower()
        return Path(artist) / album / f'{prefix}{title}{suffix}'
    return Path(export_name(track))


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
    from .bulk import MAX_SELECTION
    folder = Path(folder).resolve()
    require(folder.is_dir() and 1 <= len(selected) <= MAX_SELECTION, 'export-selection')
    from .audio import EXTENSIONS
    from .search import FORMAT_EXTENSIONS, matches_format, suffix_matches_format
    from .remote_details import audio_details, detect_file_format_label
    require(all(PurePosixPath(t.get('afc_path') or '').suffix.casefold() in EXTENSIONS for t in selected),'export-format')
    for chosen in selected:
        expected = chosen.get('expected_format')
        if expected is not None:
            require(isinstance(expected,str) and expected.strip().lstrip('.').casefold() in FORMAT_EXTENSIONS,'export-format')
    result = [];covers_embedded=0;skipped_format=0;skipped_existing=0;format_updates={};m3u_entries=[]
    playlist_name = next((c.get('playlist_name') for c in selected if c.get('playlist_name')), None)
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
                require(PurePosixPath(current['afc_path']).suffix.casefold() in EXTENSIONS,'export-format')
            for index, chosen in enumerate(selected):
                from .cancellation import wait_if_paused
                await wait_if_paused(progress)
                checkpoint()
                track = fresh[chosen['id']]
                structure = chosen.get('folder_structure') or 'flat'
                incremental = bool(chosen.get('incremental'))
                expected_format = chosen.get('expected_format')
                if expected_format:
                    if not suffix_matches_format(track['afc_path'],expected_format):
                        if hasattr(afc,'fseek'):
                            info = await audio_details(afc,track)
                            if info.get('format_source') == 'header':
                                format_updates[track['id']] = {'format_label':info.get('format_label'),'format_source':'header'}
                        skipped_format += 1
                        progress((index+1)*100,len(selected)*100,'Omitida por formato distinto: '+track['title'])
                        continue
                    if hasattr(afc,'fseek'):
                        info = await audio_details(afc,track)
                        if info.get('format_source') == 'header':
                            detected = info.get('format_label')
                            defer_m4a_codec = detected == 'M4A' and expected_format.strip().lstrip('.').casefold() in ('aac','alac')
                            if not defer_m4a_codec and not matches_format({'format_label':detected,'format_source':'header','afc_path':track['afc_path']},expected_format):
                                format_updates[track['id']] = {'format_label':detected,'format_source':'header'}
                                skipped_format += 1
                                progress((index+1)*100,len(selected)*100,'Omitida por formato distinto: '+track['title'])
                                continue
                rel_target = export_relative_path(track, structure)
                target_dir = (folder / rel_target.parent).resolve()
                require(target_dir == folder or folder in target_dir.parents, 'export-selection')
                destination_name = rel_target.name
                if incremental and (target_dir / destination_name).is_file():
                    skipped_existing += 1
                    m3u_entries.append({'title':track['title'],'artist':track.get('artist'),'duration':track.get('duration'),'relative_path':rel_target})
                    progress((index+1)*100,len(selected)*100,'Omitida (ya exportada): '+track['title'])
                    continue
                temporary_audio = Path(temporary)/'audio.part'
                def bytes_progress(done,total):
                    progress(index*100+int(done*80/total),len(selected)*100,'Exportando: '+track['title'])
                with temporary_audio.open('wb') as output:
                    _, digest, size = await read_remote(afc,track['afc_path'],output=output,progress=bytes_progress)
                require(size > 0, 'export-empty-audio')
                _, check, check_size = await read_remote(afc,track['afc_path'])
                require(size == check_size and digest == check == local_hash(temporary_audio), 'export-hash')
                checkpoint()
                if expected_format:
                    actual_label = detect_file_format_label(temporary_audio)
                    if not matches_format({'format_label':actual_label,'format_source':'header','afc_path':track['afc_path']},expected_format):
                        format_updates[track['id']] = {'format_label':actual_label,'format_source':'header'}
                        temporary_audio.unlink(missing_ok=True)
                        skipped_format += 1
                        progress((index+1)*100,len(selected)*100,'Omitida por formato distinto: '+track['title'])
                        continue
                if chosen.get('embed_artwork'):
                    from .remote_artwork import cover_for_track
                    from .export_artwork import embed
                    picture=await cover_for_track(afc,track,assets=True,catalogue_only=True)
                    if picture and embed(temporary_audio,picture.get('cover')):covers_embedded+=1
                target_dir.mkdir(parents=True, exist_ok=True)
                retained=retain_export(temporary_audio,target_dir,destination_name)
                require(local_hash(retained)==local_hash(temporary_audio),'export-hash')
                result.append(str(retained))
                m3u_entries.append({'title':track['title'],'artist':track.get('artist'),'duration':track.get('duration'),'relative_path':retained.relative_to(folder)})
                control=CURRENT.get()
                if control is not None:control.files=list(result)
                temporary_audio.unlink()
                progress((index+1)*100,len(selected)*100,'Exportada: '+track['title'])
    playlist_file = None
    if playlist_name and m3u_entries:
        from .playlists import write_m3u8
        safe_pl = _safe_component(playlist_name, 'Playlist')
        playlist_file = str(write_m3u8(folder / f'{safe_pl}.m3u8', m3u_entries))
    summary = {'exported':len(result),'files':result,'covers_embedded':covers_embedded}
    if skipped_format:
        summary['skipped_format'] = skipped_format
    if skipped_existing:
        summary['skipped_existing'] = skipped_existing
    if format_updates:
        summary['format_updates'] = format_updates
    if playlist_file:
        summary['playlist_file'] = playlist_file
    return summary


async def export_to_ios_app(selected, destination, progress):
    """Copy selected iPhone Music tracks into an iOS app's /Documents folder song-by-song."""
    from .bulk import MAX_SELECTION
    from .audio import EXTENSIONS
    from .search import FORMAT_EXTENSIONS, matches_format, suffix_matches_format
    from .remote_details import audio_details, detect_file_format_label
    from .app_files import (
        CONFLICT_POLICIES,
        app_documents_on_lockdown,
        documents_path,
        ensure_remote_dir,
        normalize_relative,
        upload_local_file_to_app,
        validate_bundle_id,
        validate_name,
        _stat_or_none,
    )
    require(isinstance(destination, dict) and 1 <= len(selected) <= MAX_SELECTION, 'export-selection')
    bundle_id = validate_bundle_id(destination.get('bundle_id'))
    subfolder = normalize_relative(destination.get('subfolder') or '')
    structure = 'artist_album' if destination.get('structure') == 'artist_album' else 'flat'
    policy = destination.get('conflict_policy') if destination.get('conflict_policy') in CONFLICT_POLICIES else 'skip'
    require(all(PurePosixPath(t.get('afc_path') or '').suffix.casefold() in EXTENSIONS for t in selected), 'export-format')
    for chosen in selected:
        expected = chosen.get('expected_format')
        if expected is not None:
            require(isinstance(expected, str) and expected.strip().lstrip('.').casefold() in FORMAT_EXTENSIONS, 'export-format')
    copied = []
    covers_embedded = 0
    skipped_format = 0
    skipped_existing = 0
    format_updates = {}
    async with device() as (lockdown, afc):
        async with app_documents_on_lockdown(lockdown, bundle_id) as app_afc:
            await ensure_remote_dir(app_afc, subfolder)
            with tempfile.TemporaryDirectory(prefix='tupaq-ios-copy-') as temporary:
                catalogue = Path(temporary) / 'catalogue'
                catalogue.mkdir()
                from pymobiledevice3.services.afc import AfcFileNotFoundError
                tracks = await copy_catalogue(afc, catalogue, (FileNotFoundError, AfcFileNotFoundError))
                fresh = {t['id']: t for t in tracks}
                for chosen in selected:
                    current = fresh.get(chosen.get('id'))
                    require(current is not None and all(current.get(k) == chosen.get(k) for k in ('title', 'artist', 'afc_path')),
                            'export-stale-selection')
                    require(bool(current.get('afc_path')), 'export-no-usb-file')
                    require(PurePosixPath(current['afc_path']).suffix.casefold() in EXTENSIONS, 'export-format')
                for index, chosen in enumerate(selected):
                    from .cancellation import wait_if_paused
                    await wait_if_paused(progress)
                    checkpoint()
                    track = fresh[chosen['id']]
                    expected_format = chosen.get('expected_format')
                    if expected_format:
                        if not suffix_matches_format(track['afc_path'], expected_format):
                            if hasattr(afc, 'fseek'):
                                info = await audio_details(afc, track)
                                if info.get('format_source') == 'header':
                                    format_updates[track['id']] = {'format_label': info.get('format_label'), 'format_source': 'header'}
                            skipped_format += 1
                            progress((index + 1) * 100, len(selected) * 100, 'Omitida por formato distinto: ' + track['title'])
                            continue
                        if hasattr(afc, 'fseek'):
                            info = await audio_details(afc, track)
                            if info.get('format_source') == 'header':
                                detected = info.get('format_label')
                                defer_m4a_codec = detected == 'M4A' and expected_format.strip().lstrip('.').casefold() in ('aac', 'alac')
                                if not defer_m4a_codec and not matches_format({'format_label': detected, 'format_source': 'header', 'afc_path': track['afc_path']}, expected_format):
                                    format_updates[track['id']] = {'format_label': detected, 'format_source': 'header'}
                                    skipped_format += 1
                                    progress((index + 1) * 100, len(selected) * 100, 'Omitida por formato distinto: ' + track['title'])
                                    continue
                    rel_parts = [validate_name(part) for part in export_relative_path(track, structure).parts]
                    rel_str = '/'.join(rel_parts)
                    remote_rel = f'{subfolder}/{rel_str}' if subfolder else rel_str
                    remote_target = documents_path(remote_rel)
                    if policy == 'skip' and await _stat_or_none(app_afc, remote_target) is not None:
                        skipped_existing += 1
                        progress((index + 1) * 100, len(selected) * 100, 'Omitida (ya exportada): ' + track['title'])
                        continue
                    temporary_audio = Path(temporary) / 'audio.part'
                    try:
                        def read_progress(done, total):
                            progress(index * 100 + int(done * 45 / total), len(selected) * 100, 'Leyendo del iPhone: ' + track['title'])
                        with temporary_audio.open('wb') as output:
                            _, digest, size = await read_remote(afc, track['afc_path'], output=output, progress=read_progress)
                        require(size > 0, 'export-empty-audio')
                        _, check, check_size = await read_remote(afc, track['afc_path'])
                        require(size == check_size and digest == check == local_hash(temporary_audio), 'export-hash')
                        checkpoint()
                        if expected_format:
                            actual_label = detect_file_format_label(temporary_audio)
                            if not matches_format({'format_label': actual_label, 'format_source': 'header', 'afc_path': track['afc_path']}, expected_format):
                                format_updates[track['id']] = {'format_label': actual_label, 'format_source': 'header'}
                                skipped_format += 1
                                progress((index + 1) * 100, len(selected) * 100, 'Omitida por formato distinto: ' + track['title'])
                                continue
                        if chosen.get('embed_artwork'):
                            from .remote_artwork import cover_for_track
                            from .export_artwork import embed
                            picture = await cover_for_track(afc, track, assets=True, catalogue_only=True)
                            if picture and embed(temporary_audio, picture.get('cover')):
                                covers_embedded += 1
                        def write_progress(done, total):
                            progress(index * 100 + 45 + int(done * 50 / total), len(selected) * 100, 'Copiando a carpeta del iPhone: ' + track['title'])
                        status, final_remote = await upload_local_file_to_app(
                            app_afc,
                            temporary_audio,
                            remote_rel,
                            conflict_policy=policy,
                            byte_progress=write_progress,
                        )
                        if status == 'skipped':
                            skipped_existing += 1
                            progress((index + 1) * 100, len(selected) * 100, 'Omitida (ya exportada): ' + track['title'])
                        else:
                            copied.append(final_remote)
                            control = CURRENT.get()
                            if control is not None:
                                control.files = list(copied)
                            progress((index + 1) * 100, len(selected) * 100, 'Exportada: ' + track['title'])
                    finally:
                        temporary_audio.unlink(missing_ok=True)
    summary = {
        'copied_to_app': len(copied),
        'bundle_id': bundle_id,
        'subfolder': subfolder,
        'files': copied,
        'covers_embedded': covers_embedded,
    }
    if skipped_format:
        summary['skipped_format'] = skipped_format
    if skipped_existing:
        summary['skipped_existing'] = skipped_existing
    if format_updates:
        summary['format_updates'] = format_updates
    return summary


async def fetch_preview_audio(afc_path, target_path):
    """Read-only download of a single track from the iPhone into a temp file for local preview playback."""
    from .audio import EXTENSIONS
    require(bool(afc_path) and PurePosixPath(afc_path).suffix.casefold() in EXTENSIONS, 'export-format')
    async with device() as (_, afc):
        with Path(target_path).open('wb') as output:
            _, _, size = await read_remote(afc, afc_path, output=output)
        require(size > 0, 'export-empty-audio')
    return Path(target_path)


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


async def verified_import_catalogue(afc,directory,before,entries,receipt,progress):
    """Allow bounded catalogue settling, never resend or bypass another failure."""
    for attempt in range(3):
        name='after' if attempt==0 else f'after-metadata-recheck-{attempt}'
        after=await capture(afc,directory/name)
        try:
            verify_before_after(before,after,entries)
        except ProtocolError as error:
            if str(error) not in ('verify-new-metadata','verify-lyrics-registration') or attempt==2:raise
            progress(90,100,'Esperando la actualización de metadatos de Música…')
            await asyncio.sleep(.5*(attempt+1))
        else:
            receipt['verified_catalogue']=name+'/1/MediaLibrary.sqlitedb'
            return after


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
        # This is a host-generated snapshot, not the live ATC anchor. Its
        # Media counter can differ in either direction and must never choose
        # the request/revision. Use SQLite, require ReadyForSync equality and
        # recapture the live catalogue before staging any metadata instead.
        require(host is None or (parsed['database'],parsed['voice']) == (host['database'],host['voice']), 'host-anchor-conflict')
        host = parsed
        target = directory/name
        target.write_bytes(data)
        target.chmod(0o600)
    require(host is not None and host['voice'] == 1, 'host-anchor-unavailable')
    return identity,host['voice']


async def check_empty_staging(afc):
    require(not await missing(afc,MEDIA), 'staging-directory-missing')
    files = await afc.listdir(MEDIA)
    require(all(name in ('.','..') for name in files), 'staging-not-empty')


def music_folders(before):
    return sorted({str(PurePosixPath(t['afc_path']).parent) for t in before['tracks'].values()
        if t.get('afc_path') and re.fullmatch(r'iTunes_Control/Music/F[0-9]{2}',str(PurePosixPath(t['afc_path']).parent))}) or ['iTunes_Control/Music/F00']


async def available_path(afc,before,source,reserved_paths=None,folders=None):
    folders=music_folders(before) if folders is None else folders
    occupied={t['afc_path'].lower() for t in before['tracks'].values() if t.get('afc_path')} if reserved_paths is None else reserved_paths
    for folder in folders:
        if await missing(afc,folder):continue
        require((await afc.stat(folder)).get('st_ifmt')=='S_IFDIR','music-directory-kind')
        for _ in range(128):
            leaf=''.join(secrets.choice(string.ascii_uppercase) for _ in range(4))+source['extension']
            destination=media_path(folder,leaf)
            require(destination is not None,'music-path')
            if destination.lower() not in occupied and await missing(afc,destination):
                occupied.add(destination.lower());return destination
    raise ProtocolError('music-directory-unavailable')


def allocate_id(reserved):
    while True:
        identifier = secrets.randbits(63)
        if identifier >= 1000 and identifier not in reserved:
            reserved.add(identifier)
            return identifier


async def plan_entries(afc, before, sources, directory):
    reserved = set(before['ids'])
    artists = {k:v[0] for k,v in before['artists'].items() if len(v) == 1}
    albums = {k:v[0] for k,v in before['albums'].items() if len(v) == 1}
    entries, destinations = [], set()
    occupied={t['afc_path'].lower() for t in before['tracks'].values() if t.get('afc_path')}
    folders=music_folders(before)
    artwork_ids = set(before['artwork_ids'])
    for source in sources:
        artist = source['album_artist']
        if artist not in artists:
            artists[artist] = allocate_id(reserved)
        album = (source['album'],artist)
        if album not in albums:
            albums[album] = allocate_id(reserved)
        destination = await available_path(afc,before,source,occupied,folders)
        require(destination.lower() not in destinations, 'plan-path-collision')
        destinations.add(destination.lower())
        entry = {'track_id':allocate_id(reserved),'album_id':albums[album],'artist_id':artists[artist],
                 'destination':destination,'source':source,'added_at':int(time.time())}
        from .sync.lyrics import prepare as prepare_lyrics
        lyrics=prepare_lyrics(source,directory/'lyrics')
        require(local_hash(source['path'])==source['id'],'source-changed-before-upload')
        if lyrics:
            require(before.get('lyrics_records') is not None,'lyrics-catalogue-schema')
            entry['lyrics']=lyrics
            require(await missing(afc,f"/Airlock/Media/Lyrics/{entry['track_id']}"),'lyrics-staging-collision')
        custom_cover = source.get('custom_artwork_path')
        if (source.get('has_artwork') or custom_cover) and source.get('send_artwork',True):
            from .sync.artwork import prepare
            require(before['artwork_known'],'artwork-catalogue-schema')
            raw_cover = Path(custom_cover).read_bytes() if custom_cover and Path(custom_cover).is_file() else None
            picture = prepare(source['path'],directory/'artwork',source['container'],raw_data=raw_cover)
            require(local_hash(source['path'])==source['id'],'source-changed-before-upload')
            if picture:
                from .sync.artwork import allocate_cache_id
                picture['cache_id']=allocate_cache_id(artwork_ids);entry['artwork']=picture
                require(await missing(afc,f"/Airlock/Media/Artwork/{entry['track_id']}"),'artwork-staging-collision')
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
    _, digest, size = await read_remote(afc,path,limit=5*1024*1024)
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


async def transact(afc, channel, before, identity, voice, entries, receipt, directory, progress,
                   operation=None, artwork_only=False, deleting=False):
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
                current['originals'] == before['originals'] and current['wire_to_item'] == before['wire_to_item'] and
                current['artwork_ids'] == before['artwork_ids'] and current['artwork_tokens'] == before['artwork_tokens'], 'catalogue-changed-before-stage')
        if operation is None:operation = encode_operations(before['database'],before['primary'],before['anchor'],entries)
        signature = signer.sign(operation)
        begin_commit()
        receipt['phase'] = 'staging'
        save_receipt(directory,receipt)
        await write_bytes(afc,MEDIA+'/Sync_00000000.plist',operation)
        await write_bytes(afc,MEDIA+'/Sync_00000000.plist.cig',signature)
        receipt['phase'] = 'metadata-announced'
        save_receipt(directory,receipt)
        announced_at=time.perf_counter_ns()
        await channel.send({'Command':'FinishedSyncingMetadata','Session':2,'Params':{
            'DataclassAnchors':{'Media':str(before['anchor']+1),'VoiceMemo':str(voice)},
            'SyncTypes':{'Media':1,'Book':0,'Keybag':1}}})
        assets=[entry for entry in entries if entry.get('artwork')] if artwork_only else entries
        await deliver_assets(afc,channel,before,assets,receipt,directory,progress,artwork_only=artwork_only,
                             forbidden={str(value) for e in entries for value in (e['track_id'],e.get('wire_pid',e['track_id']))} if deleting else None,announced_at=announced_at)
    finally:
        signer.close()


async def deliver_assets(afc,channel,before,entries,receipt,directory,progress,artwork_only=False,forbidden=None,announced_at=None):
    own = {} if forbidden is not None else {str(e['track_id']):e for e in entries}
    manifest_seen, completed = False, set()
    settled_at = (announced_at or time.perf_counter_ns()) if not own else None
    for _ in range(256):
        message = await channel.receive()
        require(message.get('Session') == 2, 'terminal-session')
        command = message.get('Command')
        require(command not in ('SyncFailed','ConnectionInvalid','FileError'), 'device-sync-failed')
        if command == 'AssetManifest':
            require(not manifest_seen, 'manifest-repeated')
            existing_music = {wire for wire,item in before['wire_to_item'].items() if item in before['tracks'] and wire not in (forbidden or set())}
            existing_music.update(str(int(wire)&((1<<64)-1)) for wire in list(existing_music))
            declared = {identifier:2 if artwork_only else 1 | (2 if entry.get('artwork') else 0) | (8 if entry.get('lyrics') else 0)
                        for identifier,entry in own.items()}
            audio, ancillary = validate_manifest(message,set(own),existing_music,declared)
            manifest_seen = True
            receipt['manifest_parts'] = sorted({asset['Variant']['AssetParts'] for asset in message['Params']['AssetManifest']['Media']})
            save_receipt(directory,receipt)
            # Every request is checked before any completion/refusal is sent.
            for index, identifier in enumerate(audio):
                entry = own[identifier]
                if entry.get('lyrics') and not artwork_only:
                    lyrics=entry['lyrics'];path=Path(lyrics['path'])
                    from .sync.lyrics import MAX_TEXT_BYTES
                    require(path.stat().st_size==lyrics['size'] and 0<lyrics['size']<=MAX_TEXT_BYTES,'lyrics-source-changed')
                    data=path.read_bytes()
                    require(hashlib.sha256(data).hexdigest()==lyrics['id'],'lyrics-source-changed')
                    folder='/Airlock/Media/Lyrics'
                    if await missing(afc,folder):await afc.makedirs(folder)
                    require((await afc.stat(folder)).get('st_ifmt')=='S_IFDIR','lyrics-staging-directory')
                    await write_bytes(afc,f'{folder}/{identifier}',data)
                if entry.get('artwork'):
                    picture=entry['artwork']
                    data=Path(picture['path']).read_bytes()
                    require(len(data)==picture['size'] and hashlib.sha256(data).hexdigest()==picture['id'],'artwork-source-changed')
                    folder='/Airlock/Media/Artwork'
                    if await missing(afc,folder):await afc.makedirs(folder)
                    require((await afc.stat(folder)).get('st_ifmt')=='S_IFDIR','artwork-staging-directory')
                    await write_bytes(afc,f"{folder}/{identifier}",data)
                def bytes_progress(done,total):
                    progress(index*100+int(done*80/max(1,total)),len(entries)*100,'Importando: '+entry['source']['title'],entry['source']['id'])
                if not artwork_only:await upload_audio(afc,entry,bytes_progress)
                if index==len(audio)-1 and not ancillary:settled_at=time.perf_counter_ns()
                await channel.send({'Command':'FileComplete','Session':2,'Params':{
                    'AssetID':identifier,'Dataclass':'Media','AssetPath':'' if artwork_only else entry['destination']}})
                completed.add(identifier)
                receipt['completed_assets'] = sorted(completed)
                save_receipt(directory,receipt)
            for index,identifier in enumerate(ancillary):
                if index==len(ancillary)-1:settled_at=time.perf_counter_ns()
                await channel.send({'Command':'FileError','Session':2,'Params':{
                    'AssetID':identifier,'Dataclass':'Media','ErrorCode':16,'ErrorIsVisible':False}})
        elif command == 'SyncFinished':
            observed = getattr(channel,'last_received_at',None)
            require(settled_at is not None and (observed is None or observed >= settled_at), 'terminal-before-settlement')
            require(completed == set(own), 'finished-without-audio')
            receipt['phase'] = 'verifying'
            save_receipt(directory,receipt)
            return
        elif command != 'SyncAllowed':
            raise ProtocolError('terminal-command')
    raise ProtocolError('terminal-limit')

async def import_selected(selected, backup_root, progress, expected_snapshot=None):
    require(1 <= len(selected) <= 49, 'import-selection-limit')
    require(sum(Path(chosen['path']).stat().st_size for chosen in selected) <= 2*1024*1024*1024, 'import-batch-size')
    sources, hashes = [], set()
    for chosen in selected:
        checkpoint()
        source = inspect_source(chosen['path'],chosen.get('id'))
        require(source['id'] not in hashes, 'duplicate-source')
        hashes.add(source['id'])
        if chosen.get('metadata_policy')=='filename':
            title=Path(source['path']).stem
            require(0<len(title)<=4096 and not any(ord(c)<32 for c in title),'metadata-text')
            source['title']=title
        overrides = chosen.get('metadata_overrides')
        if isinstance(overrides, dict):
            for field in ('title','artist','album','album_artist','genre','composer'):
                if field in overrides and isinstance(overrides[field], str):
                    val = overrides[field].strip()
                    if val:
                        require(len(val)<=4096 and not any(ord(c)<32 for c in val),'metadata-text')
                        source[field] = val
                    elif field in ('genre','composer'):
                        source[field] = ''
            if 'artist' in overrides and 'album_artist' not in overrides and overrides.get('artist','').strip():
                source['album_artist'] = source['artist']
            for int_field, low, high in (('year',1,9999),('track_number',1,65535),('track_count',1,65535),('disc_number',1,65535),('disc_count',1,65535)):
                if int_field in overrides:
                    val = overrides[int_field]
                    if val is None or val == '':
                        source.pop(int_field, None)
                    elif type(val) is int and low <= val <= high:
                        source[int_field] = val
        if chosen.get('custom_artwork_path'):
            source['custom_artwork_path'] = str(chosen['custom_artwork_path'])
            source['has_artwork'] = True
        source['send_artwork']=chosen.get('send_artwork',True)
        source['send_lyrics']=chosen.get('send_lyrics',True)
        sources.append(source)
    require(sum(s['size'] for s in sources) <= 2*1024*1024*1024, 'import-batch-size')
    root = Path(backup_root)
    root.mkdir(parents=True,exist_ok=True)
    directory = root/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    receipt = {'phase':'preflight','entries':[]}
    save_receipt(directory,receipt)
    try:
        async with device() as (lockdown, afc):
            required={t['required_device_token'] for t in selected if t.get('required_device_token') is not None}
            require(not required or required=={getattr(lockdown,'_tupaq_device_token',None)},'bulk-device-changed')
            # The OS library lock coordinates with other desktop sync clients.
            from pymobiledevice3.services.afc import AFC_LOCK_EX, AFC_LOCK_UN
            lock = await afc.fopen('/com.apple.itunes.lock_sync','a+')
            locked = False
            try:
                await afc.lock(lock,AFC_LOCK_EX)
                locked = True
                progress(0,100,'Leyendo el estado actual de Música…')
                before = await capture(afc,directory/'before')
                from .bulk import validate_binding
                validate_binding(lockdown,before)
                require(expected_snapshot is None or before == expected_snapshot, 'recovery-catalogue-changed')
                identity, voice = await preferences(afc,directory,before)
                from .reconciliation import reconcile,ensure_resolved
                progress(0,100,'Comprobando operaciones anteriores…')
                checkpoint()
                reconciliation = await reconcile(root,afc,before,identity,progress,exclude=directory)
                ensure_resolved(reconciliation)
                progress(0,100,'Buscando canciones ya importadas…')
                completed_receipts, retired_receipts = [], []
                for journal in root.glob('*/journal.json'):
                    record = json.loads(journal.read_text(encoding='utf-8'))
                    if record.get('operation')=='delete':continue
                    if record.get('phase') == 'resolved-items-removed':
                        retired_receipts.append(record)
                    if record.get('phase') in ('completed','observed-present'):
                        matches = [{'track_id':e['track_id'],'destination':e['destination'],
                                    'source':{'id':e['source']['id'],'size':e['source']['size']}}
                                   for e in record.get('entries',[]) if e['source']['id'] in hashes]
                        if matches:
                            completed_receipts.append({'database':record.get('database'),'primary':record.get('primary'),'entries':matches})
                for retired in retired_receipts:
                    if retired.get('database') == before['database']:
                        require(not any(str(e['track_id']) in before['wire_to_item'] for e in retired.get('entries',[])),
                                'recovery-retired-item-returned')
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
                    return {'imported':0,'already_imported':len(already),'source_ids':list(hashes),'backup':str(directory),'reconciled':reconciliation['reconciled'],'metadata_unverified':reconciliation['metadata_unverified'],'metadata_diagnostics':reconciliation['metadata_diagnostics']}
                from .library import MAX_TRACKS
                require(len(before['tracks'])+len(sources)<=MAX_TRACKS,'import-catalogue-limit')
                await check_empty_staging(afc)
                checkpoint()
                progress(0,100,'Preparando el envío de canciones…')
                entries = await plan_entries(afc,before,sources,directory)
                receipt.update(entries=entries,anchor=before['anchor'],database=before['database'],primary=before['primary'])
                save_receipt(directory,receipt)
                connection = await lockdown.start_lockdown_service('com.apple.atc')
                async with Atc(connection) as channel:
                    await transact(afc,channel,before,identity,voice,entries,receipt,directory,progress)
                progress(90,100,'Comprobando las canciones en la biblioteca…')
                after = await verified_import_catalogue(afc,directory,before,entries,receipt,progress)
                for entry in entries:
                    _, digest, size = await read_remote(afc,entry['destination'])
                    require(size == entry['source']['size'] and digest == entry['source']['id'], 'verify-permanent-audio')
                receipt['audio_verified']=True
                save_receipt(directory,receipt)
                from .sync.artwork import verify as verify_artwork
                try:
                    await verify_artwork(afc,after,entries)
                except ProtocolError as error:
                    error.facts={**(error.facts or {}),'audio_verified':True}
                    raise
                receipt['phase'] = 'completed'
                save_receipt(directory,receipt)
                progress(100,100,'Importación comprobada en el catálogo.')
                return {'imported':len(entries),'lyrics_registered':sum(bool(e.get('lyrics')) for e in entries),
                        'already_imported':len(already),'source_ids':list(hashes),'backup':str(directory),'reconciled':reconciliation['reconciled'],'metadata_unverified':reconciliation['metadata_unverified'],'metadata_diagnostics':reconciliation['metadata_diagnostics']}
            finally:
                if locked:
                    with suppress(Exception):
                        await afc.lock(lock,AFC_LOCK_UN)
                await afc.fclose(lock)
    except BaseException as error:
        from .reconciliation import note_failure
        note_failure(receipt,error)
        if receipt['phase'] == 'preflight':
            receipt['phase'] = 'before-write-failed'
        save_receipt(directory,receipt)
        raise


async def import_with_recovery(selected, backup_root, progress):
    """Retry only a matching interrupted insertion; keep every durable receipt.

    Recovery rechecks library identity, anchors, originals, destinations and
    source bytes. An unrelated/ambiguous operation still requires review.
    """
    try:
        return await import_selected(selected,backup_root,progress)
    except ProtocolError as error:
        if str(error)!='previous-import-unverified':raise
        from .recovery import pending_receipt,resume_pending
        _,receipt=pending_receipt(backup_root)
        if (receipt.get('operation') or receipt.get('phase')!='metadata-announced'
                or receipt.get('last_error_code')!='AttributeError'):
            raise error
        pending={entry['source']['id'] for entry in receipt['entries']}
        if not pending <= {item.get('id') for item in selected}:raise error
    # The previous session and its OS lock have closed before opening recovery.
    await resume_pending(backup_root,selected,progress)
    return await import_selected(selected,backup_root,progress)


def transfer_error(error, mode):
    code = str(error) if isinstance(error,ProtocolError) else error.diagnostic if isinstance(error,LibraryError) else type(error).__name__
    status = getattr(error,'status',None)
    if status is not None and not isinstance(error,ProtocolError):
        with suppress(TypeError,ValueError):
            if 0 <= int(status) <= 65535:
                code += '-'+str(int(status))
    if mode == 'delete':
        message='La eliminación se detuvo o no pudo verificarse. Actualiza la biblioteca y conserva el registro de la operación.'
    elif mode == 'export':
        message = 'No se completó la exportación. Los archivos ya exportados se conservan; no se modificó el iPhone.'
    elif mode == 'export_app':
        if isinstance(error, LibraryError) and str(error):
            return TransferError(str(error), 'export_app:' + error.diagnostic)
        message = 'No se completó la copia a la carpeta del iPhone. Las canciones ya copiadas se conservan.'
    elif mode == 'diagnose':
        message='No se completaron las comprobaciones de lectura. No se modificó el iPhone.'
    elif mode == 'repair':
        message = 'La actualización de portadas y fecha se detuvo o no pudo verificarse. Conserva el respaldo y copia el diagnóstico.'
    else:
        message = 'La importación se detuvo o no pudo verificarse. Revisa el diagnóstico y el respaldo del catálogo antes de repetirla.'
    messages = {
        'verify-new-metadata':'Los metadatos leídos del iPhone no coinciden con los enviados. La canción puede estar ya importada. Conserva el respaldo y usa Revisar operación pendiente en Diagnóstico.',
        'catalogue:changing':'Música sigue actualizando su catálogo y no se pudo obtener una lectura estable. Conserva los registros y vuelve a actualizar la biblioteca.',
        'delete-stale-selection':'La biblioteca o el dispositivo cambió. Actualiza la lista y vuelve a marcar las canciones.',
        'import-catalogue-limit':'Este lote excedería el máximo de canciones que TUPAQ puede comprobar. No se ha enviado.',
        'bulk-device-binding':'No se pudo vincular la operación masiva al iPhone.',
        'bulk-device-changed':'Cambió el iPhone o su catálogo. Se detuvieron los siguientes lotes.',
        'bulk-selection-limit':'Selecciona entre 1 y 50.000 canciones.',
        'bulk-duplicate-selection':'La selección contiene identificadores duplicados. Actualiza la biblioteca.',
        'bulk-local-space':'No hay suficiente espacio local para conservar las copias de catálogo. Se detuvieron los siguientes lotes.',
        'bulk-batch-unverified':'El lote necesita una revisión. No se enviaron los siguientes lotes.',
        'delete-selection-limit':'Marca entre 1 y 100 canciones para eliminarlas.',
        'delete-recovery-readonly':'Una eliminación pendiente se comprueba con Revisar operación; no se reenvía audio.',
        'previous-import-unverified':'Hay una operación anterior sin confirmar. En Diagnóstico → Mostrar opciones avanzadas de recuperación → Revisar operación pendiente puedes comprobarla. Si falta audio, Completar importación pendiente utiliza el original.',
        'manifest-own-parts':'El iPhone solicitó componentes que esta versión no puede entregar. No repitas la importación. Copia el diagnóstico completo; los metadatos podrían estar ya en Música.',
        'lyrics-catalogue-schema':'No se reconoce el registro de letras de este catálogo. No se han enviado cambios. Copia el diagnóstico.',
        'lyrics-source-size':'Una letra incrustada supera el límite de 256 KB. No se ha enviado el lote. Puedes desactivar el envío de letras en Preferencias.',
        'lyrics-source-encoding':'Una letra contiene texto que no se puede codificar sin alterarlo. No se ha enviado el lote.',
        'verify-lyrics-registration':'El texto de la letra no pudo verificarse en el catálogo del iPhone. La canción puede estar ya importada. Conserva el respaldo y usa Revisar operación pendiente en Diagnóstico; no repitas el envío ni borres los registros.',
        'recovery-source-missing':'No se encuentra el archivo original. Añádelo con Elegir canciones y vuelve a usar Diagnóstico → Completar importación pendiente.',
        'recovery-pending-state':'La canción no tiene el estado local pendiente admitido para completar su audio. No se ha reenviado la canción. Copia el diagnóstico.',
        'recovery-mixed-state':'La operación contiene canciones en estados diferentes. No se ha reenviado. Conserva el respaldo y copia el diagnóstico.',
        'recovery-file-exists':'Ya hay un archivo en el destino o en el área de envío. Se detuvo la recuperación para evitar sobrescribirlo. Prueba Revisar importación y copia el diagnóstico si falla.',
        'recovery-anchor':'La biblioteca avanzó o cambió desde la operación pendiente. No se ha reenviado. Conserva los registros y copia el diagnóstico.',
        'metadata-no-owned-tracks':'No hay importaciones registradas por TUPAQ en este ordenador que se puedan actualizar.',
        'metadata-selection-limit':'No se encontraron canciones registradas para actualizar o son más de 49. Añade con Elegir canciones los originales del lote que quieras actualizar y vuelve a Diagnóstico.',
        'metadata-owned-track-changed':'Una canción cambió desde su importación. Se detuvo la actualización; conserva el registro y copia el diagnóstico.',
        'recovery-metadata-only':'Esta operación actualiza portadas y fechas. Usa Revisar importación pendiente para comprobar su resultado; no requiere reenviar el audio.',
        'artwork-image-profile':'La portada incrustada no tiene un formato o unas dimensiones admitidas. No se ha enviado una actualización de biblioteca.',
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
    if mode=='diagnose' and code=='export-stale-selection':message='La biblioteca cambió. Actualiza la lista antes de comprobarla.'
    if mode=='import' and code in ('verify-artwork-original','verify-artwork-registration') and isinstance(getattr(error,'facts',None),dict) and error.facts.get('audio_verified') is True:
        message='El audio y los metadatos están verificados en el iPhone, pero no se pudo confirmar la carátula. Conserva el registro y usa Revisar operación pendiente antes de repetir el envío.'
    if isinstance(error,ProtocolError) and error.facts is not None:
        code += '\nDatos del protocolo: '+json.dumps(error.facts,sort_keys=True)
    return TransferError(message, mode+':'+code)


async def verify_pending(backup_root, progress):
    from .reconciliation import reconcile,ensure_resolved
    async with device() as (_,afc):
        with tempfile.TemporaryDirectory(prefix='tupaq-verify-') as temporary:
            directory=Path(temporary)
            current=await capture(afc,directory/'catalogue')
            prefs=directory/'preferences';prefs.mkdir()
            identity,_=await preferences(afc,prefs,current)
            result=await reconcile(backup_root,afc,current,identity,progress,recheck_metadata=True)
            ensure_resolved(result)
    return result


def run_transfer(mode, selected, destination, progress):
    control=getattr(progress,'control',None) or TransferControl()
    token=CURRENT.set(control)
    try:
        checkpoint()
        require(mode in ('import','export','export_app','verify','resume','repair','delete','diagnose'), 'transfer-mode')
        from .deletion import delete_selected
        from .recovery import resume_pending
        from .metadata_update import repair_imported
        bulk=mode in ('import','delete') and (len(selected)>(49 if mode=='import' else 100) or (mode=='import' and sum(Path(t['path']).stat().st_size for t in selected)>2*1024**3))
        if mode=='diagnose':
            from .diagnostics import check
            return asyncio.run(check(selected,progress,destination))
        if bulk:
            from .bulk import execute
            return asyncio.run(execute(mode,selected,destination,progress))
        work = (delete_selected(selected,destination,progress) if mode=='delete' else
                import_with_recovery(selected,destination,progress) if mode == 'import' else
                verify_pending(destination,progress) if mode == 'verify' else
                repair_imported(destination,selected,progress) if mode == 'repair' else
                resume_pending(destination,selected,progress) if mode == 'resume' else
                export_to_ios_app(selected,destination,progress) if mode == 'export_app' else
                export_selected(selected,destination,progress))
        result=asyncio.run(asyncio.wait_for(work,timeout=1800))
        if control.event.is_set() and control.committed:result['cancel_deferred']=True
        return result
    except TransferCancelled:
        result={'cancelled':True,'before_changes':not control.committed}
        if mode=='export':result.update(exported=len(control.files),files=control.files)
        elif mode=='export_app':result.update(copied_to_app=len(control.files),files=control.files)
        return result
    except Exception as error:
        raise transfer_error(error,mode) from None
    finally:CURRENT.reset(token)
