"""System typography on macOS; staged installed/file fonts elsewhere."""
from pathlib import Path
import sys
from PySide6.QtGui import QFont,QFontDatabase,QFontInfo

SF_FAMILIES=('SF Pro Text','SF Pro','SF Pro Display','SF UI Text','SF UI Display')


def css_family(family):
    return family.replace('\\','\\\\').replace('"','\\"').replace('\n',' ').replace('\r',' ')


def configure(app,path=None,family=None):
    old=getattr(app,'typography_font_id',None);identifier=None;loaded=[]
    if sys.platform=='darwin':path=family=None
    if path:
        file=Path(path)
        if not file.is_file() or file.suffix.lower() not in ('.ttf','.otf','.ttc','.otc') or file.stat().st_size>128*1024**2:
            raise ValueError('font-file')
        identifier=QFontDatabase.addApplicationFont(str(file))
        if identifier<0:raise ValueError('font-file')
        loaded=QFontDatabase.applicationFontFamilies(identifier)
        if not loaded:
            QFontDatabase.removeApplicationFont(identifier);raise ValueError('font-file')
        chosen=family if family in loaded else loaded[0]
        font=QFont(chosen)
    elif family:
        if family not in QFontDatabase.families():raise ValueError('font-family')
        font=QFont(family)
    else:font=QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    if old is not None and old!=identifier:QFontDatabase.removeApplicationFont(old)
    app.typography_font_id=identifier;app.typography_font_path=str(path) if path else None
    font.setPixelSize(13);font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias);app.setFont(font)
    actual=QFontInfo(app.font()).family();apple=actual in SF_FAMILIES or actual.startswith(('.SF','SF Pro','.AppleSystemUIFont'))
    status=('San Francisco' if sys.platform=='darwin' and apple else actual)+' · '+('fuente seleccionada' if family or path else 'fuente del sistema')
    app.typography_family=actual;app.typography_status=status;app.typography_is_apple=apple
    return status
