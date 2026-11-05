"""Bounded local folder expansion, used only from the preparation worker."""
import os
from pathlib import Path
from .audio import EXTENSIONS
from .bulk import MAX_SELECTION


def expand(paths,interrupted=lambda:False,limit=MAX_SELECTION):
    result=[];seen=set();folders=0
    for item in paths:
        if interrupted():return []
        item=Path(item)
        if not item.is_dir():result.append(item)
        else:
            pending=[item]
            while pending:
                if interrupted():return []
                current=pending.pop();folders+=1
                if folders>100000:raise ValueError('La carpeta contiene demasiadas subcarpetas.')
                with os.scandir(current) as entries:
                    for entry in entries:
                        if interrupted():return []
                        if entry.is_dir(follow_symlinks=False):pending.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False) and Path(entry.name).suffix.casefold() in EXTENSIONS:
                            key=str(Path(entry.path).resolve())
                            if key not in seen:seen.add(key);result.append(Path(entry.path))
                        if len(result)>limit:raise ValueError('La carpeta supera el límite de 50.000 canciones.')
                        if len(pending)>100000:raise ValueError('La carpeta contiene demasiadas subcarpetas.')
        if len(result)>limit:raise ValueError('La carpeta supera el límite de 50.000 canciones.')
    return result
