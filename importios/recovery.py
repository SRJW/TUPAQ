"""Explicit recovery of a TUPAQ-owned insertion; never edits remote SQLite.

An existing pathless owned item can request its audio in an unchanged-anchor
empty delta. This mechanism is experimental on native devices. If iOS already
removed every owned item, reconcile the original catalogue before a fresh import.
Independent protocol reference: rustunes 057ee8fc (MIT), session/pending_completion.
"""
from contextlib import suppress
from pathlib import Path
import json
import tempfile

from .phone_paths import media_path
from .sync.catalogue import snapshot, verify_originals, verify_before_after, metadata_differences
from .sync.protocol import require, library_identity, handshake
from .sync.source import inspect_source

TERMINAL = ('completed','observed-present','before-write-failed','resolved-items-removed')


def pending_receipt(root):
    pending = []
    for journal in sorted(Path(root).glob('*/journal.json')):
        receipt = json.loads(journal.read_text(encoding='utf-8'))
        if receipt.get('phase') not in TERMINAL:
            pending.append((journal,receipt))
    require(len(pending) == 1, 'pending-import-count')
    journal,receipt = pending[0]
    require(1 <= len(receipt.get('entries',[])) <= 49, 'pending-no-entries')
    return journal,receipt


def classify(before, current, entries):
    verify_originals(before,current)
    require(current['anchor'] == before['anchor']+1, 'recovery-anchor')
    require(len({entry['track_id'] for entry in entries}) == len(entries)
            and len({entry['destination'] for entry in entries}) == len(entries), 'recovery-duplicate-entry')
    statuses,owned_items = [],set()
    for entry in entries:
        wire = str(entry['track_id'])
        require(type(entry['track_id']) is int and 0 < entry['track_id'] < 2**63
                and entry['track_id'] not in before['ids'], 'recovery-owned-id')
        base,_,leaf = entry['destination'].rpartition('/')
        require(media_path(base,leaf) == entry['destination'], 'recovery-destination')
        item_id = current['wire_to_item'].get(wire)
        if item_id is None:
            statuses.append('removed')
            continue
        owned_items.add(item_id)
        require(item_id not in before['originals'], 'recovery-original-target')
        track = current['tracks'].get(item_id)
        require(track is not None and not metadata_differences(track,entry['source']),
                'recovery-owned-metadata')
        require(current['groups'].get(wire) == (entry['album_id'],entry['artist_id']), 'recovery-owned-groups')
        if track.get('afc_path') == entry['destination']:
            statuses.append('complete')
        else:
            require(not track.get('afc_path'), 'recovery-unexpected-file')
            require(current['states'].get(item_id) == (0,1,0,1,0), 'recovery-pending-state')
            statuses.append('pending')
    require(current['originals'] == before['originals'] | owned_items, 'recovery-unexpected-items')
    require(len(set(statuses)) == 1, 'recovery-mixed-state')
    return statuses[0]


def saved_identity(directory):
    values = [library_identity((directory/name).read_bytes()) for name in ('iTunesPrefs','iTunesPrefs.plist')
              if (directory/name).is_file()]
    require(bool(values) and all(value == values[0] for value in values), 'recovery-saved-identity')
    return values[0]


def bind_sources(entries, selected):
    chosen = {item['id']:item['path'] for item in selected}
    for entry in entries:
        source = entry['source']
        path = chosen.get(source['id'],source['path'])
        require(Path(path).is_file(), 'recovery-source-missing')
        fresh = inspect_source(path,source['id'])
        for key in ('size','format','extension','samples','sample_rate','channels','audio_format','bit_rate'):
            require(fresh[key] == source[key], 'recovery-source-profile')
        # Preserve the original declared metadata, even if an untagged original
        # was relocated/renamed. Byte identity and audio headers were rechecked.
        source['path'] = fresh['path']


async def check_audio(afc, entries):
    from .transfers import read_remote
    for entry in entries:
        _,digest,size = await read_remote(afc,entry['destination'])
        require((digest,size) == (entry['source']['id'],entry['source']['size']), 'verify-permanent-audio')


async def resume_pending(root, selected, progress):
    from .transfers import (device, capture, preferences, check_empty_staging, missing,
        save_receipt, deliver_assets, Atc, import_selected)
    from pymobiledevice3.services.afc import AFC_LOCK_EX, AFC_LOCK_UN
    root = Path(root)
    journal,receipt = pending_receipt(root)
    require(receipt.get('operation')!='delete','delete-recovery-readonly')
    require(receipt.get('operation')!='metadata-update','recovery-metadata-only')
    directory,entries = journal.parent,receipt['entries']
    require(receipt.get('import_phase',receipt['phase']) in ('metadata-announced','verifying'), 'recovery-phase')
    before = snapshot(directory/'before'/'1'/'MediaLibrary.sqlitedb')
    require((receipt.get('database'),receipt.get('primary'),receipt.get('anchor')) ==
            (before['database'],before['primary'],before['anchor']), 'recovery-receipt-identity')
    identity = saved_identity(directory)
    retry = False
    async with device() as (lockdown,afc):
        lock = await afc.fopen('/com.apple.itunes.lock_sync','a+')
        locked = False
        try:
            await afc.lock(lock,AFC_LOCK_EX);locked = True
            with tempfile.TemporaryDirectory(prefix='tupaq-recovery-') as temporary:
                temporary = Path(temporary)
                current = await capture(afc,temporary/'current')
                status = classify(before,current,entries)
                prefs = temporary/'preferences';prefs.mkdir()
                live_identity,voice = await preferences(afc,prefs,current)
                require(live_identity == identity, 'recovery-library-identity')
                await check_empty_staging(afc)
                if status == 'complete':
                    verify_before_after(before,current,entries)
                    await check_audio(afc,entries)
                    from .sync.artwork import verify as verify_artwork
                    await verify_artwork(afc,current,entries)
                else:
                    bind_sources(entries,selected)
                    # Never overwrite a permanent file or a previous upload.
                    for entry in entries:
                        for path in (entry['destination'],f"/Airlock/Media/{entry['track_id']}",
                                     f"/Airlock/Media/{entry['track_id']}{entry['source']['extension']}"):
                            require(await missing(afc,path), 'recovery-file-exists')
                    if status == 'removed':
                        # The retired owned rows are absent. Retain evidence;
                        # permit a new, fully checked import with fresh IDs.
                        receipt['phase'] = 'resolved-items-removed'
                        save_receipt(directory,receipt)
                        retry = True
                    else:
                        receipt.setdefault('import_phase',receipt['phase'])
                        receipt['phase'] = 'resuming-audio'
                        save_receipt(directory,receipt)
                        connection = await lockdown.start_lockdown_service('com.apple.atc')
                        async with Atc(connection) as channel:
                            signer = await handshake(channel,identity,current['anchor'],voice)
                            try:
                                checked = await capture(afc,temporary/'rechecked')
                                require(checked == current, 'recovery-catalogue-changed')
                                checked_prefs = temporary/'rechecked-preferences';checked_prefs.mkdir()
                                checked_identity,checked_voice = await preferences(afc,checked_prefs,checked)
                                require((checked_identity,checked_voice) == (identity,voice), 'recovery-identity-changed')
                                await check_empty_staging(afc)
                                # No insert, signed operation, staging or anchor increment.
                                await channel.send({'Command':'FinishedSyncingMetadata','Session':2,'Params':{
                                    'DataclassAnchors':{'Media':str(current['anchor']),'VoiceMemo':str(voice)},
                                    'SyncTypes':{'Media':1,'Book':0,'Keybag':1}}})
                                await deliver_assets(afc,channel,current,entries,receipt,directory,progress)
                            finally:
                                signer.close()
                        after = await capture(afc,temporary/'after')
                        verify_before_after(before,after,entries)
                        await check_audio(afc,entries)
                        from .sync.artwork import verify as verify_artwork
                        await verify_artwork(afc,after,entries)
            if not retry:
                receipt['phase'] = 'completed'
                save_receipt(directory,receipt)
                return {'verified':len(entries),'source_ids':[e['source']['id'] for e in entries],'backup':str(directory)}
        finally:
            if locked:
                with suppress(Exception):await afc.lock(lock,AFC_LOCK_UN)
            await afc.fclose(lock)
    require(retry, 'recovery-state')
    return await import_selected([{'id':e['source']['id'],'path':e['source']['path']} for e in entries],root,progress,
                                 expected_snapshot=current)
