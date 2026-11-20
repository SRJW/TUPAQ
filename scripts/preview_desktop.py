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
 ext={'MP3':'.mp3','WAV':'.wav','AIFF':'.aif'}.get(fmt,'.m4a')
 rows.append({'id':str(n),'title':title,'artist':artist,'album':album,'format_label':fmt,'duration':180+n*17,'size':(n+8)*1024**2,'is_local':True,'usb_exists':True,'afc_path':f'iTunes_Control/Music/F00/{n:04}{ext}','has_artwork':True})
w.connection_token='synthetic-preview';w.show_library(rows);w.device_name.setText('iPhone de prueba');w.device_details={'model':'iPhone14,2','version':'27.0','total_bytes':256*10**9,'free_bytes':137*10**9,'battery':{'health_percent':94.0,'cycle_count':180,'charge_percent':78,'max_capacity_mah':3070,'design_capacity_mah':3274,'temperature_c':28.5,'voltage_v':3.98,'is_charging':True}};w.update_diagnostics()
from importios.visuals import table_cover
for n in range(len(rows)):
 picture=QPixmap(96,96);p=QPainter(picture);g=QLinearGradient(0,0,96,96);g.setColorAt(0,QColor.fromHsv((n*37)%360,150,180));g.setColorAt(1,QColor.fromHsv((n*37+55)%360,180,70));p.fillRect(picture.rect(),g);p.setPen(QColor('#ffffff'));p.drawEllipse(18+n%3*3,17,58,58);p.drawLine(8,75,85,38);p.end()
 w.library_model.set_icon(str(n),table_cover(picture,28))
w.library_model.checked.add('0');w.checks_changed()
for n,fixture in enumerate(('sample.mp3','covered-aac.m4a','sample.wav')):
 path=ROOT/'tests'/'fixtures'/fixture;track=inspect_audio(path,fixture);track['path']=str(path);from importios.artwork import thumbnail
 track['thumbnail']=thumbnail(__import__('importios.audio',fromlist=['read_artwork']).read_artwork(path))
 track['title']=('Órbita','Luz de madrugada','Todo vuelve')[n];w.accept_track(track)
from datetime import datetime
w.app_list=[{'bundle_id':'org.videolan.vlc-ios','name':'VLC','version':'3.5.0'},{'bundle_id':'com.example.reader','name':'Lector PDF','version':'2.1'}]
w.app_list_token='synthetic-preview'
w.app_selector.blockSignals(True);w.app_selector.addItem('VLC (org.videolan.vlc-ios)','org.videolan.vlc-ios');w.app_selector.addItem('Lector PDF (com.example.reader)','com.example.reader');w.app_selector.blockSignals(False)
w.app_current_bundle='org.videolan.vlc-ios';w.app_current_path=''
w.app_entries=[{'name':'Películas','relative':'Películas','kind':'dir','size':None,'modified':datetime(2026,5,1,12,30)},{'name':'Concierto.mp4','relative':'Concierto.mp4','kind':'file','size':42*1024**2,'modified':datetime(2026,5,2,18,15)},{'name':'Notas.pdf','relative':'Notas.pdf','kind':'file','size':380*1024,'modified':datetime(2026,5,3,9,5)}]
w.populate_app_table();w.app_status.setText('3 elementos en la carpeta.')
w.read_finished();w.update_buttons();w.show();app.processEvents()
for mode,index in [('oscuro',2),('claro',1)]:
 w.theme_choice.setCurrentIndex(index);app.processEvents()
 for name,page in [('biblioteca',0),('preferencias',1),('importar',2),('diagnostico',3),('apps',4)]:
  w.navigate(page);app.processEvents();w.grab().save(str(args.output/f'{name}-{mode}.png'))
(args.output/'render-info.json').write_text(json.dumps({'data':'synthetic','platform':sys.platform,'system_font':QFontInfo(app.font()).family(),'device_pixel_ratio':w.devicePixelRatioF()},indent=2))
w.tracks.clear();w.close()
