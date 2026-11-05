"""Render the actual native widgets with synthetic data, no USB or user files."""
import argparse,json,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap,QPainter,QColor,QLinearGradient,QFontInfo,QFontDatabase
from PySide6.QtWidgets import QApplication
from importios.native import Window
from importios.audio import inspect_audio,read_artwork
from importios.artwork import thumbnail
parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
app=QApplication([]);app.setApplicationName('TUPAQ-preview')
# Windows' offscreen plugin may not enumerate its OS font collection. Register
# existing system files for this renderer only; never copy/distribute fonts.
if sys.platform=='win32' and len(QFontDatabase.families())<2:
 for name in ('segoeui.ttf','seguisb.ttf','segoeuib.ttf'):
  path=Path(os.environ.get('WINDIR','C:/Windows'))/'Fonts'/name
  if path.is_file():QFontDatabase.addApplicationFont(str(path))
w=Window(auto_connect=False);w.resize(1280,800);w.motion.set_enabled(False)
rows=[]
for n,(title,artist,album,fmt) in enumerate([('Órbita','Lina del Sol','Horizontes','M4A · ALAC'),('7 días','Norte','Tiempo','MP3'),('Luz de madrugada','Isla','Reflejos','M4A · AAC'),('A través del agua','Marea','Azul','WAV'),('Todo vuelve','Prisma','Colores','AIFF'),('Lejos de aquí','Atlas','Caminos','M4A · ALAC'),('El último verano','Bruma','Recuerdos','MP3'),('Silencio','Luna','Noche','M4A · AAC'),('Bajo el cielo','Lina del Sol','Horizontes','M4A · ALAC'),('Viento del sur','Norte','Tiempo','MP3')]):
 rows.append({'id':str(n),'title':title,'artist':artist,'album':album,'format_label':fmt,'duration':180+n*17,'size':(n+8)*1024**2,'is_local':True,'usb_exists':True,'afc_path':f'iTunes_Control/Music/F00/{n:04}.m4a','has_artwork':True})
w.connection_token='synthetic-preview';w.show_library(rows);w.device_name.setText('iPhone de prueba');w.device_details={'model':'iPhone14,2','version':'27.0','total_bytes':256*10**9,'free_bytes':137*10**9};w.update_diagnostics()
for n in range(len(rows)):
 picture=QPixmap(96,96);p=QPainter(picture);g=QLinearGradient(0,0,96,96);g.setColorAt(0,QColor.fromHsv((n*37)%360,150,180));g.setColorAt(1,QColor.fromHsv((n*37+55)%360,180,70));p.fillRect(picture.rect(),g);p.setPen(QColor('#ffffff'));p.drawEllipse(18+n%3*3,17,58,58);p.drawLine(8,75,85,38);p.end()
 from PySide6.QtGui import QIcon
 w.library_model.set_icon(str(n),QIcon(picture))
w.library_model.checked.add('0');w.checks_changed()
for n,fixture in enumerate(('sample.mp3','covered-aac.m4a','sample.wav')):
 path=ROOT/'tests'/'fixtures'/fixture;track=inspect_audio(path,fixture);track['path']=str(path);from importios.artwork import thumbnail
 track['thumbnail']=thumbnail(__import__('importios.audio',fromlist=['read_artwork']).read_artwork(path))
 track['title']=('Órbita','Luz de madrugada','Todo vuelve')[n];w.accept_track(track)
w.read_finished();w.update_buttons();w.show();app.processEvents()
for mode,index in [('oscuro',2),('claro',1)]:
 w.theme_choice.setCurrentIndex(index);app.processEvents()
 for name,page in [('biblioteca',0),('preferencias',1),('importar',2),('diagnostico',3)]:
  w.navigate(page);app.processEvents();w.grab().save(str(args.output/f'{name}-{mode}.png'))
(args.output/'render-info.json').write_text(json.dumps({'data':'synthetic','platform':sys.platform,'system_font':QFontInfo(app.font()).family(),'device_pixel_ratio':w.devicePixelRatioF()},indent=2))
w.tracks.clear();w.close()
