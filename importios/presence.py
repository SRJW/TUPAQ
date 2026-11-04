"""Read directory names once per validated music folder; never delete files."""
from collections import defaultdict
from .phone_paths import media_path


async def probe_files(afc,tracks,diagnostics=None):
    from pymobiledevice3.services.afc import AfcFileNotFoundError
    groups=defaultdict(list)
    for track in tracks:
        path=track.get('afc_path')
        if not path:continue
        base,_,leaf=path.rpartition('/')
        if media_path(base,leaf)==path:groups[base].append((leaf,track))
    checked=missing=unavailable=0
    for folder,rows in groups.items():
        if checked+unavailable>=512:break
        try:
            names=await afc.listdir(folder)
            if not isinstance(names,list) or len(names)>200000 or any(not isinstance(name,str) for name in names):
                unavailable+=1;continue
            names=set(names);checked+=1
        except (FileNotFoundError,AfcFileNotFoundError):
            names=set();checked+=1
        except Exception:
            unavailable+=1;continue
        for leaf,track in rows:
            track['usb_exists']=leaf in names
            missing+=leaf not in names
    if diagnostics is not None:
        from .library_fields import local_tracks
        diagnostics['local_tracks']=len(local_tracks(tracks))
        diagnostics.update(usb_folders_checked=checked,usb_folders_unavailable=unavailable,usb_missing_references=missing)
    return tracks
