"""Developer-only synthetic stress harness. Requires development dependencies and tests fixtures."""
import sys,time,tempfile,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'tests')]
import argparse
parser=argparse.ArgumentParser(description='Synthetic TUPAQ stress test; no real iPhone connection.')
parser.add_argument('--tracks',type=int,default=10000)
parser.add_argument('--report',type=Path,required=True)
args=parser.parse_args()
if not 1<=args.tracks<=50000:parser.error('--tracks must be between 1 and 50000')
from PySide6.QtCore import QTimer,qVersion
from PySide6.QtWidgets import QApplication
from mutagen.id3 import ID3,TIT2
from mutagen.mp4 import MP4
from importios.native import Window
import test_transfers as support
n=args.tracks
app=QApplication([]);app.setApplicationName('TUPAQ-stress');w=Window(auto_connect=False);w.show();app.processEvents()
with tempfile.TemporaryDirectory() as root:
 paths=[]
 for i in range(n):
  if i<150:
   path=Path(root)/f'{i}.m4a';path.write_bytes((support.FIXTURES/'covered-aac.m4a').read_bytes());tags=MP4(path);tags['\xa9nam']=[f'Song {i:06}'];tags.save()
  else:
   path=Path(root)/f'{i}.mp3';path.write_bytes((support.FIXTURES/'sample.mp3').read_bytes());tags=ID3(path);tags.add(TIT2(encoding=3,text=f'Song {i:06}'));tags.save(path,padding=lambda _:0)
  paths.append(path)
 started=time.perf_counter();last=started;gaps=[]
 def beat():
  global last
  now=time.perf_counter();gaps.append(now-last);last=now
 timer=QTimer();timer.setInterval(10);timer.timeout.connect(beat);timer.start();w.add_paths(paths)
 while w.worker is not None or w.thumbnail_worker is not None:
  app.processEvents();time.sleep(.001)
 elapsed=time.perf_counter()-started;timer.stop();gaps.append(time.perf_counter()-last)
 assert len(w.tracks)==n and w.table.rowCount()==n and not w.errors.count()
 report={'tracks':n,'prepared':len(w.tracks),'seconds':round(elapsed,3),'max_gui_gap_seconds':round(max(gaps),3),'heartbeats':len(gaps),'qt':qVersion(),'thumbnail_count':sum(bool(t.get('thumbnail')) for t in w.tracks.values()),'simulation':True,'peak_rss_kib':next((int(line.split()[1]) for line in Path('/proc/self/status').read_text().splitlines() if line.startswith('VmHWM:')),None) if Path('/proc/self/status').exists() else None}
 args.report.write_text(json.dumps(report,indent=2));print(report,flush=True)
 w.tracks.clear();w.close()
