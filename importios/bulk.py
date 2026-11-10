"""Bounded multi-session work; native transaction limits remain unchanged."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import time
import uuid
from contextvars import ContextVar
from .cancellation import CURRENT,TransferCancelled,checkpoint,wait_if_paused
from .sync.protocol import require

MAX_SELECTION=50_000
IMPORT_COUNT=49
DELETE_COUNT=100
IMPORT_BYTES=2*1024**3
SOURCE_BYTES=256*1024**2
MIN_FREE=512*1024**2
BINDING=ContextVar('tupaq_bulk_binding',default=None)


def validate_binding(lockdown,catalogue):
    state=BINDING.get()
    if state is None:return
    token=getattr(lockdown,'_tupaq_device_token',None)
    require(isinstance(token,str) and len(token)==64,'bulk-device-binding')
    identity=(token,catalogue['database'],catalogue['primary'])
    if 'identity' not in state:state['identity']=identity
    require(state['identity']==identity,'bulk-device-changed')


def plan(mode,selected):
    require(mode in ('import','delete') and 1<=len(selected)<=MAX_SELECTION,'bulk-selection-limit')
    ids=set();chunks=[];chunk=[];size=0
    for track in selected:
        checkpoint();identifier=track.get('id')
        require(isinstance(identifier,str) and identifier and identifier not in ids,'bulk-duplicate-selection');ids.add(identifier)
        length=0
        if mode=='import':
            path=Path(track['path']);require(path.is_file(),'source-size');length=path.stat().st_size
            require(0<length<=SOURCE_BYTES,'source-size')
        limit=IMPORT_COUNT if mode=='import' else DELETE_COUNT
        if chunk and (len(chunk)==limit or size+length>IMPORT_BYTES):chunks.append(chunk);chunk=[];size=0
        chunk.append(track);size+=length
    if chunk:chunks.append(chunk)
    return chunks


def save(path,record):
    temporary=path.with_suffix('.tmp')
    with temporary.open('w',encoding='utf-8') as stream:
        json.dump(record,stream,ensure_ascii=True,sort_keys=True);stream.flush()
        import os
        os.fsync(stream.fileno())
    temporary.chmod(0o600)
    temporary.replace(path)


async def execute(mode,selected,root,progress):
    from .transfers import import_with_recovery,transfer_error
    from .deletion import delete_selected
    chunks=plan(mode,selected);root=Path(root);root.mkdir(parents=True,exist_ok=True)
    folder=root/'bulk-jobs';folder.mkdir(mode=0o700,exist_ok=True)
    journal=folder/(uuid.uuid4().hex+'.json')
    fingerprint=hashlib.sha256(json.dumps([t['id'] for t in selected],ensure_ascii=True).encode()).hexdigest()
    record={'operation':mode,'selection_count':len(selected),'selection_fingerprint':fingerprint,
            'phase':'running','completed_batches':[],'batch_count':len(chunks)}
    save(journal,record)
    result={'bulk':True,'requested':len(selected),'processed':0,'batches_completed':0,
            'bulk_journal':str(journal),'source_ids':[],'item_ids':[]}
    result.update({'imported':0,'already_imported':0,'lyrics_registered':0} if mode=='import' else {'deleted':0})
    control=CURRENT.get();reserve=MIN_FREE;binding_token=BINDING.set({})
    try:
        for number,chunk in enumerate(chunks):
            await wait_if_paused(lambda _value,_total,label:progress(result['processed']*100,len(selected)*100,label))
            checkpoint()
            require(shutil.disk_usage(root).free>=reserve,'bulk-local-space')
            base=result['processed'];last_emit=0.;last_value=base*100
            def report(value,total,label,identifier=''):
                nonlocal last_emit,last_value
                now=time.monotonic()
                if now-last_emit<.08 and value<total:return
                last_emit=now
                scaled=max(last_value,base*100+round(len(chunk)*100*max(0,min(.95,value/max(1,total)))))
                last_value=scaled
                progress(scaled,len(selected)*100,f'Lote {number+1}/{len(chunks)} · {label}',identifier)
            # A fresh timeout per bounded transaction, never 30 min for the whole selection.
            work=import_with_recovery(chunk,root,report) if mode=='import' else delete_selected(chunk,root,report)
            part=await asyncio.wait_for(work,timeout=1800)
            require(not part.get('cancelled') and not part.get('metadata_unverified'),'bulk-batch-unverified')
            result['processed']+=len(chunk);result['batches_completed']+=1
            for key in ('imported','already_imported','deleted','lyrics_registered'):
                if key in result:result[key]+=part.get(key,0)
            result['source_ids'].extend(part.get('source_ids',[]));result['item_ids'].extend(part.get('item_ids',[]))
            result['backup']=part.get('backup','')
            record['completed_batches'].append({'offset':base,'count':len(chunk),'backup':part.get('backup','')})
            save(journal,record)
            # Reset cancellation only after the native batch was completely verified and saved.
            if control is not None:
                with control.lock:control.committed=False
            progress(result['processed']*100,len(selected)*100,f'{result["processed"]} de {len(selected)} canciones comprobadas','')
            if part.get('backup'):
                directory=Path(part['backup'])
                if directory.is_dir():reserve=max(MIN_FREE,3*sum(p.stat().st_size for p in directory.rglob('*') if p.is_file()))
        record['phase']='completed'
    except TransferCancelled:
        record['phase']='cancelled';result['cancelled']=True
    except Exception as error:
        from .reconciliation import safe_code
        record.update(phase='stopped',error_code=safe_code(error))
        result.update(bulk_stopped=True,diagnostic=transfer_error(error,mode).diagnostic)
    finally:
        BINDING.reset(binding_token)
        record['processed']=result['processed']
        try:save(journal,record)
        except OSError:result.update(bulk_stopped=True,diagnostic='bulk:journal-write')
    return result
