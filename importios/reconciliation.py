"""Read-only reconciliation of interrupted receipts against the current phone.

A current byte-verified owned audio is an observation, not a claim about the
original session's atomic success. Never resends, deletes or clears unknown work.
"""
from pathlib import Path
import json
import re

from .sync.protocol import ProtocolError,require
from .sync.catalogue import verify_owned_entries
from .recovery import TERMINAL,saved_identity


def safe_code(error):
    from .library import LibraryError
    value=str(error) if isinstance(error,ProtocolError) else error.diagnostic if isinstance(error,LibraryError) else type(error).__name__
    return value if re.fullmatch(r'[A-Za-z0-9_:-]{1,100}',value) else type(error).__name__


def note_failure(receipt,error):
    receipt['last_error_code']=safe_code(error)


async def reconcile(root,afc,current,identity,progress=lambda *args:None,exclude=None):
    from .transfers import read_remote,missing,save_receipt,check_empty_staging
    from .sync.artwork import verify as verify_artwork
    result={'verified':0,'retired':0,'removed':0,'metadata_unverified':0,'reconciled':0,'source_ids':[],'unresolved':[],'foreign':0}
    for journal in sorted(Path(root).glob('*/journal.json')):
        if exclude is not None and journal.parent==exclude:continue
        record=json.loads(journal.read_text(encoding='utf-8'));phase=record.get('phase')
        if phase in TERMINAL:continue
        if phase=='preflight':
            # The durable staging phase is written before the first remote write.
            record.update(phase='before-write-failed',reconciliation='interrupted-preflight')
            save_receipt(journal.parent,record);result['reconciled']+=1;continue
        if record.get('database') is not None and record['database']!=current['database']:
            result['foreign']+=1;continue
        cause=record.get('last_error_code','unknown')
        if not isinstance(cause,str) or not re.fullmatch(r'[A-Za-z0-9_:-]{1,100}',cause):cause='unknown'
        observation={'phase':phase if isinstance(phase,str) and re.fullmatch('[a-z-]{1,64}',phase) else 'unknown','cause':cause}
        try:
            require((record.get('database'),record.get('primary'))==(current['database'],current['primary']),'pending-library-binding')
            require(saved_identity(journal.parent)==identity,'pending-library-identity')
            if phase=='staging' and not record.get('operation'):
                from .sync.catalogue import snapshot
                baseline=snapshot(journal.parent/'before'/'1'/'MediaLibrary.sqlitedb')
                if current==baseline:
                    await check_empty_staging(afc)
                    require(bool(record.get('entries')),'pending-no-entries')
                    for entry in record['entries']:
                        for path in (entry['destination'],f"/Airlock/Media/{entry['track_id']}",f"/Airlock/Media/{entry['track_id']}{entry['source']['extension']}",f"/Airlock/Media/Artwork/{entry['track_id']}"):
                            require(await missing(afc,path),'pending-staging-files-remain')
                    record.update(phase='before-write-failed',reconciliation='unannounced-empty-staging-and-unchanged-catalogue')
                    save_receipt(journal.parent,record);result['reconciled']+=1;continue
            require(phase in ('staging','metadata-announced','resuming-audio','verifying'),'pending-stage-uncertain')
            if record.get('operation')=='delete':
                from .deletion import verify_deleted
                from .sync.catalogue import snapshot
                before=snapshot(journal.parent/'before'/'1'/'MediaLibrary.sqlitedb')
                verify_deleted(before,current,record['entries'],later=True)
                result['removed']+=len(record['entries'])
                record.update(phase='completed',reconciliation='native-removal-verified-now')
                save_receipt(journal.parent,record);result['reconciled']+=1
                continue
            entries=record.get('entries',[])
            require(1<=len(entries)<=49 and type(record.get('anchor')) is int and current['anchor']>=record['anchor']+1,'pending-receipt-state')
            wires=[str(e['track_id']) for e in entries]
            require(len(set(wires))==len(wires),'pending-duplicate-entry')
            from .phone_paths import media_path
            for entry in entries:
                base,_,leaf=entry['destination'].rpartition('/')
                require(media_path(base,leaf)==entry['destination'] and type(entry['track_id']) is int
                        and 0<entry['track_id']<2**63 and entry['source']['extension'] in ('.mp3','.m4a','.wav','.aif','.aiff'),
                        'pending-entry-scope')
            present=[current['tracks'].get(current['wire_to_item'].get(wire)) for wire in wires]
            if all(track is None for track in present) and not any(wire in current['wire_to_item'] for wire in wires):
                await check_empty_staging(afc)
                for entry in entries:
                    paths=(entry['destination'],f"/Airlock/Media/{entry['track_id']}",
                           f"/Airlock/Media/{entry['track_id']}{entry['source']['extension']}",f"/Airlock/Media/Artwork/{entry['track_id']}")
                    require(all([await missing(afc,path) for path in paths]),'pending-removed-files-remain')
                record.update(phase='resolved-items-removed',reconciliation='owned-items-and-files-absent')
                save_receipt(journal.parent,record);result['retired']+=len(entries);result['reconciled']+=1;continue
            require(all(track is not None for track in present),'pending-partial-items')
            for entry,track in zip(entries,present):
                require(track.get('afc_path')==entry['destination'],'pending-audio-location')
                _,digest,size=await read_remote(afc,entry['destination'])
                require((digest,size)==(entry['source']['id'],entry['source']['size']),'pending-audio-hash')
            metadata=True
            try:
                verify_owned_entries(current,entries)
                await verify_artwork(afc,current,entries)
            except Exception:metadata=False
            record.update(phase='observed-present',reconciliation='owned-audio-verified-now',
                          observed_anchor=current['anchor'],metadata_verified=metadata)
            save_receipt(journal.parent,record)
            result['reconciled']+=1;result['verified']+=len(entries)
            result['metadata_unverified']+=0 if metadata else len(entries)
            result['source_ids'].extend(e['source']['id'] for e in entries)
            progress(result['verified'],max(1,result['verified']),'Comprobando el audio de operaciones anteriores…')
        except Exception as error:
            observation['check']=safe_code(error);result['unresolved'].append(observation)
    return result


def ensure_resolved(result):
    if result['unresolved']:
        first=result['unresolved'][0]
        raise ProtocolError('previous-import-unverified',{'pending_count':len(result['unresolved']),
            'pending_phase':first['phase'],'previous_cause':first['cause'],'current_check':first['check']})
