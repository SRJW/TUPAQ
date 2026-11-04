"""Use macOS's native San Francisco; never bundle Apple's font files.

On other systems an already-installed or separately authorized user font may be
selected. The actual resolved family is exposed, so a fallback is never called SF.
"""
from pathlib import Path
import sys

from PySide6.QtGui import QFont,QFontDatabase,QFontInfo

SF_FAMILIES=('SF Pro Text','SF Pro','SF Pro Display','SF UI Text','SF UI Display')


def configure(app,path=None):
    previous=getattr(app,'typography_font_id',None)
    if previous is not None:
        QFontDatabase.removeApplicationFont(previous);app.typography_font_id=None
    families=set(QFontDatabase.families());loaded=[]
    if path:
        file=Path(path)
        if file.is_file() and file.suffix.lower() in ('.ttf','.otf','.ttc') and file.stat().st_size<=32*1024**2:
            identifier=QFontDatabase.addApplicationFont(str(file))
            if identifier>=0:
                app.typography_font_id=identifier
                loaded=QFontDatabase.applicationFontFamilies(identifier);families.update(loaded)
            else:raise ValueError('font-file')
        else:raise ValueError('font-file')
    if loaded:
        font=QFont(loaded[0]);apple=font.family() in SF_FAMILIES
    elif sys.platform=='darwin':
        font=QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    else:
        chosen=next((family for family in SF_FAMILIES if family in families),None)
        apple=chosen is not None
        chosen=chosen or next((family for family in ('Segoe UI Variable Text','Segoe UI','Arial','DejaVu Sans') if family in families),None)
        font=QFont(chosen) if chosen else QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    font.setPixelSize(13);font.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    app.setFont(font)
    actual=QFontInfo(app.font()).family()
    apple=actual in SF_FAMILIES or actual.startswith(('.SF','SF Pro','.AppleSystemUIFont'))
    status='San Francisco · fuente nativa de macOS' if sys.platform=='darwin' and apple and not loaded else f'San Francisco · {actual}' if apple else f'{actual} · San Francisco no está disponible'
    app.typography_status=status;app.typography_is_apple=apple
    return status
