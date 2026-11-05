"""Private, aggregate operation history; never stores song names or device IDs."""
from datetime import datetime,timezone
import json
from pathlib import Path
import uuid
from .bulk import save


def record(root,mode,requested,result=None,diagnostic=''):
    result=result or {};folder=Path(root)/'history';folder.mkdir(mode=0o700,parents=True,exist_ok=True)
    confirmed=sum(result.get(k,0) for k in ('imported','already_imported','deleted','exported','diagnosed','updated','verified'))
    status='stopped' if diagnostic or result.get('bulk_stopped') or result.get('metadata_unverified') or result.get('files_failed') else 'cancelled' if result.get('cancelled') else 'completed'
    item={'time':datetime.now(timezone.utc).isoformat(),'operation':mode,'requested':result.get('requested',requested) or confirmed,'confirmed':confirmed,'status':status}
    save(folder/(uuid.uuid4().hex+'.json'),item)
    # History is aggregate UI data, separate from recovery/catalogue receipts.
    files=sorted(folder.glob('*.json'),key=lambda path:path.stat().st_mtime,reverse=True)
    for path in files[500:]:path.unlink(missing_ok=True)
    return item


def recent(root):
    result=[];folder=Path(root)/'history'
    if not folder.exists():return result
    for path in sorted(folder.glob('*.json'),key=lambda path:path.stat().st_mtime,reverse=True)[:200]:
        try:
            item=json.loads(path.read_text(encoding='utf-8'))
            if isinstance(item,dict) and item.get('operation') in ('import','export','delete','verify','resume','repair','diagnose'):result.append(item)
        except (OSError,ValueError):continue
    return result
