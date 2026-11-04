"""Update cover and insertion date only for byte-verified TUPAQ-owned songs."""
from contextlib import suppress
from copy import deepcopy
from datetime import datetime,timezone
from pathlib import Path
import json
import plistlib
import time
import uuid

from .sync.protocol import require
from .sync.catalogue import verify_before_after
from .sync.artwork import prepare,verify as verify_artwork
from .recovery import TERMINAL,saved_identity,bind_sources,check_audio


async def repair_imported(root, selected, progress):
    from .transfers import device,capture,preferences,save_receipt,transact,Atc,local_hash
    from pymobiledevice3.services.afc import AFC_LOCK_EX,AFC_LOCK_UN
    root=Path(root);records=[]
    for journal in sorted(root.glob('*/journal.json'),reverse=True):
        record=json.loads(journal.read_text(encoding='utf-8'))
        if record.get('phase') in ('completed','observed-present'):records.append((journal.parent,record))
    require(bool(records) or any(root.glob('*/journal.json')),'metadata-no-owned-tracks')
    requested={track['id'] for track in selected}
    directory=root/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8])
    directory.mkdir(mode=0o700)
    receipt={'phase':'preflight','operation':'metadata-update','entries':[]};save_receipt(directory,receipt)
    try:
        async with device() as (lockdown,afc):
            lock=await afc.fopen('/com.apple.itunes.lock_sync','a+');locked=False
            try:
                await afc.lock(lock,AFC_LOCK_EX);locked=True
                before=await capture(afc,directory/'before')
                identity,voice=await preferences(afc,directory,before)
                from .reconciliation import reconcile,ensure_resolved
                summary=await reconcile(root,afc,before,identity,progress,exclude=directory)
                ensure_resolved(summary)
                records=[]
                for journal in sorted(root.glob('*/journal.json'),reverse=True):
                    record=json.loads(journal.read_text(encoding='utf-8'))
                    if record.get('phase') in ('completed','observed-present'):records.append((journal.parent,record))
                entries=[];seen=set()
                for saved,record in records:
                    if (record.get('database'),record.get('primary'))!=(before['database'],before['primary']):continue
                    for original in record.get('entries',[]):
                        wire=str(original['track_id'])
                        if wire in seen or (requested and original['source']['id'] not in requested):continue
                        item=before['wire_to_item'].get(wire);track=before['tracks'].get(item)
                        if not track or track.get('afc_path')!=original['destination']:continue
                        require(all(track[key]==original['source'][key] for key in ('title','artist','album')),'metadata-owned-track-changed')
                        require(saved_identity(saved)==identity,'metadata-library-identity')
                        seen.add(wire);entries.append(deepcopy(original))
                require(1<=len(entries)<=49,'metadata-selection-limit')
                require(sum(e['source']['size'] for e in entries)<=2*1024**3,'import-batch-size')
                bind_sources(entries,selected)
                await check_audio(afc,entries)
                reserved=set(before['artwork_ids'])
                for entry in entries:
                    entry['added_at']=int(time.time());entry.pop('artwork',None)
                    picture=prepare(entry['source']['path'],directory/'artwork',entry['source']['container'])
                    require(local_hash(entry['source']['path'])==entry['source']['id'],'source-changed-before-upload')
                    if picture:
                        require(before['artwork_known'],'artwork-catalogue-schema')
                        cache=max(reserved|{99})+1;require(cache<=0xffffffff,'artwork-cache-range')
                        reserved.add(cache);picture['cache_id']=cache;entry['artwork']=picture
                receipt.update(entries=entries,anchor=before['anchor'],database=before['database'],primary=before['primary'])
                save_receipt(directory,receipt)
                operations=[{'operation':'update_db_info','pid':before['database'],'db_info':{'primary_container_pid':before['primary']}}]
                for entry in entries:
                    created=datetime.fromtimestamp(entry['added_at'],timezone.utc).replace(tzinfo=None)
                    item={'date_created':created,'date_modified':created}
                    if entry.get('artwork'):item.update(artwork_cache_id=entry['artwork']['cache_id'],artwork_checksum=entry['artwork']['checksum'])
                    operations.append({'operation':'update_track','pid':entry['track_id'],'item':item})
                operation=plistlib.dumps({'revision':before['anchor']+1,'timestamp':datetime.now(timezone.utc).replace(tzinfo=None),
                    'operations':operations},fmt=plistlib.FMT_BINARY,sort_keys=False)
                connection=await lockdown.start_lockdown_service('com.apple.atc')
                async with Atc(connection) as channel:
                    await transact(afc,channel,before,identity,voice,entries,receipt,directory,progress,
                                   operation=operation,artwork_only=True)
                after=await capture(afc,directory/'after')
                verify_before_after(before,after,entries);await verify_artwork(afc,after,entries);await check_audio(afc,entries)
                receipt['phase']='completed';save_receipt(directory,receipt)
                return {'updated':len(entries),'covers':sum(bool(e.get('artwork')) for e in entries),'backup':str(directory)}
            finally:
                if locked:
                    with suppress(Exception):await afc.lock(lock,AFC_LOCK_UN)
                await afc.fclose(lock)
    except BaseException as error:
        from .reconciliation import note_failure
        note_failure(receipt,error)
        if receipt['phase']=='preflight':receipt['phase']='before-write-failed'
        save_receipt(directory,receipt)
        raise
