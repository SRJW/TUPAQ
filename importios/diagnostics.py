"""Explicit read-only checks: fresh catalogue, paths and complete streamed audio reads."""
import asyncio
import json
import re
from pathlib import Path
import tempfile
from .sync.protocol import require
from .cancellation import checkpoint,TransferCancelled,wait_if_paused


async def check(selected,progress,root=None):
    from .transfers import device,read_remote
    from .library import copy_catalogue
    from .library_fields import local_tracks
    from pymobiledevice3.services.afc import AfcFileNotFoundError
    async with device() as (_,afc):
        with tempfile.TemporaryDirectory(prefix='tupaq-check-') as temporary:
            tracks=await copy_catalogue(afc,Path(temporary),(FileNotFoundError,AfcFileNotFoundError))
            fresh={track['id']:track for track in local_tracks(tracks)}
            targets=selected if selected else list(fresh.values())
            require(len(targets)<=50000,'bulk-selection-limit')
            for chosen in targets:
                current=fresh.get(chosen.get('id'))
                require(current is not None and chosen.get('afc_path')==current.get('afc_path'),'export-stale-selection')
            expected={}
            if root is not None:
                for journal in sorted(Path(root).glob('*/journal.json'))[-5000:]:
                    try:
                        if journal.stat().st_size>8*1024*1024:continue
                        receipt=json.loads(journal.read_text(encoding='utf-8'))
                        if receipt.get('phase') not in ('completed','observed-present') or receipt.get('operation')=='delete':continue
                        for entry in receipt.get('entries',[]):
                            digest=entry['source']['id']
                            if isinstance(digest,str) and re.fullmatch('[0-9a-f]{64}',digest):expected[(receipt.get('database'),receipt.get('primary'),entry['track_id'],entry['destination'])]=digest
                    except (OSError,ValueError,KeyError,TypeError):continue
            checked=0;failed=0;total_bytes=0;hash_verified=0;mismatches=0
            for index,chosen in enumerate(targets):
                await wait_if_paused(progress);checkpoint()
                def report(done,total):progress(index*100+round(done*90/max(1,total)),max(1,len(targets))*100,'Comprobando lectura de audios…')
                try:
                    _,digest,size=await asyncio.wait_for(read_remote(afc,chosen['afc_path'],progress=report),timeout=1800)
                    require(size>0,'export-empty-audio');total_bytes+=size
                    track=fresh[chosen['id']]
                    known=expected.get((track.get('library_database'),track.get('library_primary'),track.get('library_wire'),track['afc_path'].lstrip('/')))
                    if known and digest!=known:failed+=1;mismatches+=1
                    else:
                        checked+=1
                        if known:hash_verified+=1
                except (FileNotFoundError,AfcFileNotFoundError):failed+=1
                progress((index+1)*100,max(1,len(targets))*100,'Comprobando lectura de audios…')
            return {'diagnosed':checked,'files_failed':failed,'bytes_checked':total_bytes,'catalogue_checked':True,'hash_verified':hash_verified,'hash_mismatches':mismatches,'requested':len(targets)}
