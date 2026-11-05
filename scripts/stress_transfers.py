"""Developer-only synthetic stress harness. Requires development dependencies and tests fixtures."""
import sys,time,tempfile,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import argparse
parser=argparse.ArgumentParser(description='Synthetic TUPAQ stress test; no real iPhone connection.')
parser.add_argument('--tracks',type=int,default=1000)
parser.add_argument('--report',type=Path,required=True)
args=parser.parse_args()
if not 1<=args.tracks<=50000:parser.error('--tracks must be between 1 and 50000')
from unittest.mock import patch
from mutagen.id3 import ID3,TIT2,TPE1,TALB
from importios.transfers import run_transfer,PREF
from importios.library import read_catalogue
import test_transfers as support
from test_deletion import Phone

count=args.tracks
started=time.perf_counter();report={'tracks':count,'simulation':True}
with tempfile.TemporaryDirectory(prefix='tupaq-stress-') as tmp:
 root=Path(tmp);sources=root/'sources';sources.mkdir();backups=root/'backups';p=Phone();original=p.files['/iTunes_Control/Music/F00/AAAA.mp3'];tracks=[]
 for n in range(count):
  target=sources/f'{n:05}.mp3';target.write_bytes((support.FIXTURES/'sample.mp3').read_bytes());tags=ID3(target);tags.add(TIT2(encoding=3,text=f'Stress {n:05}'));tags.add(TPE1(encoding=3,text='Synthetic'));tags.add(TALB(encoding=3,text='Stress'));tags.save(target,padding=lambda _:0)
  tracks.append({'path':str(target),'id':hashlib.sha256(target.read_bytes()).hexdigest()})
 print('Prepared',count,flush=True)
 def progress(v,total,label,*args):
  if label.endswith('canciones comprobadas'):print(v//100,'/',total//100,flush=True)
 with patch('importios.transfers.device',p.device),patch('importios.transfers.Atc',lambda peer:peer):
  before=time.perf_counter();result=run_transfer('import',tracks,backups,progress);report['import_seconds']=round(time.perf_counter()-before,3)
  print('Import',json.dumps({k:v for k,v in result.items() if k not in ('source_ids','item_ids')}),flush=True)
  assert result['imported']==count and not result.get('bulk_stopped')
  database=root/'current.sqlite';database.write_bytes(p.files[PREF+'MediaLibrary.sqlitedb']);selected=read_catalogue(database)
  for t in selected:t['_device_token']=p._tupaq_device_token
  selected=[t for t in selected if t['id']!='1']
  assert len(selected)==count
  before=time.perf_counter();result=run_transfer('delete',selected,backups,progress);report['delete_seconds']=round(time.perf_counter()-before,3)
  print('Delete',json.dumps({k:v for k,v in result.items() if k not in ('source_ids','item_ids')}),flush=True)
  assert result['deleted']==count and not result.get('bulk_stopped')
  database.write_bytes(p.files[PREF+'MediaLibrary.sqlitedb']);survivors=read_catalogue(database)
  assert len(survivors)==1 and survivors[0]['id']=='1';assert p.files['/iTunes_Control/Music/F00/AAAA.mp3']==original;assert not p.handles
  report.update(imported=count,deleted=count,survivors=1,original_audio_unchanged=True,backup_bytes=sum(x.stat().st_size for x in backups.rglob('*') if x.is_file()),seconds=round(time.perf_counter()-started,3))
  args.report.write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
