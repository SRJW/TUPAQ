"""Fixed Mori on Windows when installed; system typography on macOS.

Personal font files are never bundled, installed, uploaded or downloaded by TUPAQ.
"""
import sys
from PySide6.QtGui import QFont,QFontDatabase,QFontInfo

SF_FAMILIES=('SF Pro Text','SF Pro','SF Pro Display','SF UI Text','SF UI Display')
MORI_FAMILY='PP Mori'


def css_family(family):
    return family.replace('\\','\\\\').replace('"','\\"').replace('\n',' ').replace('\r',' ')


def configure(app,path=None,family=None):
    # Legacy file/family preferences are intentionally ignored on every platform.
    old=getattr(app,'typography_font_id',None)
    if old is not None:QFontDatabase.removeApplicationFont(old)
    app.typography_font_id=None;app.typography_font_path=None
    available=QFontDatabase.families() if sys.platform=='win32' else []
    requested=sys.platform=='win32' and MORI_FAMILY in available
    font=QFont(MORI_FAMILY) if requested else QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPixelSize(14 if requested else 13);font.setWeight(QFont.Weight.Normal)
    font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias);app.setFont(font)
    actual=QFontInfo(app.font()).family()
    mori=requested and actual==MORI_FAMILY
    apple=sys.platform=='darwin' and (actual in SF_FAMILIES or actual.startswith(('.SF','SF Pro','.AppleSystemUIFont')))
    if mori:status='Mori · tipografía de Windows'
    elif sys.platform=='win32':status='Mori no está instalada · '+actual+' · fuente del sistema'
    else:status=('San Francisco' if apple else actual)+' · fuente del sistema'
    app.typography_family=actual;app.typography_status=status;app.typography_is_apple=apple;app.typography_is_mori=mori
    return status
