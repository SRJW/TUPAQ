"""Explicit native Music removals; never unlinks audio or edits remote SQLite."""
from contextlib import suppress
from datetime import datetime,timezone
from pathlib import Path
import plistlib
import uuid

from .sync.protocol import require


def verify_deleted(before,after,entries,later=False):
    targets={e['item_id'] for e in entries}
    require(1<=len(entries)<=100 and len(targets)==len(entries) and targets<=before['originals'] and
        all(before['wire_to_item'].get(str(e['track_id']))==e['item_id'] for e in entries),'delete-receipt-binding')
    require((before['database'],before['primary'])==(after['database'],after['primary']),'delete-library-changed')
    require(after['anchor']>=before['anchor']+1 if later else after['anchor']==before['anchor']+1,'delete-anchor')
    require(after['originals']==before['originals']-targets,'delete-item-set')
    require(all(str(e['track_id']) not in after['wire_to_item'] for e in entries),'delete-wire-remains')
    for identifier,old in before['tracks'].items():
        if identifier in targets:continue
        current=after['tracks'].get(identifier)
        require(current is not None and all(old.get(k)==current.get(k) for k in ('title','artist','album','duration','afc_path')),'delete-survivor-changed')
        if before['dates_known'] and after['dates_known']:
            require(before['dates'].get(identifier)==after['dates'].get(identifier),'delete-survivor-date')
    require(all(after['wire_to_item'].get(wire)==item for wire,item in before['wire_to_item'].items() if item not in targets),'delete-survivor-wire')


async def delete_selected(selected,root,progress):
    from .transfers import device,capture,preferences,save_receipt,transact,Atc
    from .reconciliation import reconcile,ensure_resolved,note_failure
    from pymobiledevice3.services.afc import AFC_LOCK_EX,AFC_LOCK_UN
    require(1<=len(selected)<=100 and len({t['id'] for t in selected})==len(selected),'delete-selection-limit')
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    directory=root/(datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]);directory.mkdir(mode=0o700)
    receipt={'phase':'preflight','operation':'delete','entries':[]};save_receipt(directory,receipt)
    try:
        async with device() as (lockdown,afc):
            token=getattr(lockdown,'_tupaq_device_token',None)
            require(isinstance(token,str) and len(token)==64 and all(t.get('_device_token')==token for t in selected),'delete-stale-selection')
            lock=await afc.fopen('/com.apple.itunes.lock_sync','a+');locked=False
            try:
                await afc.lock(lock,AFC_LOCK_EX);locked=True
                before=await capture(afc,directory/'before')
                from .bulk import validate_binding
                validate_binding(lockdown,before)
                identity,voice=await preferences(afc,directory,before)
                ensure_resolved(await reconcile(root,afc,before,identity,progress,exclude=directory))
                inverse={item:wire for wire,item in before['wire_to_item'].items()};entries=[]
                for chosen in selected:
                    current=before['tracks'].get(chosen['id'])
                    require((chosen.get('library_database'),chosen.get('library_primary'))==(before['database'],before['primary'])
                        and current is not None and all(chosen.get(k)==current.get(k) for k in ('title','artist','album','afc_path')),
                        'delete-stale-selection')
                    wire=inverse.get(chosen['id'])
                    require(wire is not None and int(wire)!=0 and type(chosen.get('library_wire')) is int and chosen['library_wire']==int(wire),'delete-stale-selection')
                    entries.append({'item_id':chosen['id'],'track_id':int(wire),'wire_pid':int(wire)&((1<<64)-1)})
                receipt.update(entries=entries,anchor=before['anchor'],database=before['database'],primary=before['primary']);save_receipt(directory,receipt)
                operations=[{'operation':'update_db_info','pid':before['database'],'db_info':{'primary_container_pid':before['primary']}}]
                operations.extend({'operation':'delete_track','pid':e['wire_pid']} for e in entries)
                operation=plistlib.dumps({'revision':before['anchor']+1,'timestamp':datetime.now(timezone.utc).replace(tzinfo=None),
                    'operations':operations},fmt=plistlib.FMT_BINARY,sort_keys=False)
                progress(0,100,'Eliminando las canciones marcadas…')
                connection=await lockdown.start_lockdown_service('com.apple.atc')
                async with Atc(connection) as channel:
                    await transact(afc,channel,before,identity,voice,entries,receipt,directory,progress,operation=operation,deleting=True)
                after=await capture(afc,directory/'after');verify_deleted(before,after,entries)
                receipt['phase']='completed';save_receipt(directory,receipt)
                return {'deleted':len(entries),'item_ids':[e['item_id'] for e in entries],'backup':str(directory)}
            finally:
                if locked:
                    with suppress(Exception):await afc.lock(lock,AFC_LOCK_UN)
                await afc.fclose(lock)
    except BaseException as error:
        note_failure(receipt,error)
        if receipt['phase']=='preflight':receipt['phase']='before-write-failed'
        save_receipt(directory,receipt);raise
