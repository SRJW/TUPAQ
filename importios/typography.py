"""Native system typography on every platform; no custom font selection/loading."""
import sys
from PySide6.QtGui import QFont,QFontDatabase,QFontInfo

SF_FAMILIES=('SF Pro Text','SF Pro','SF Pro Display','SF UI Text','SF UI Display')


def css_family(family):
    return family.replace('\\','\\\\').replace('"','\\"').replace('\n',' ').replace('\r',' ')


def configure(app,path=None,family=None):
    # Ignore legacy file/family preferences, including installed Mori fonts.
    old=getattr(app,'typography_font_id',None)
    if old is not None:QFontDatabase.removeApplicationFont(old)
    app.typography_font_id=None;app.typography_font_path=None
    font=QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    # Points follow OS display scaling; never compress glyphs to fit a control.
    if sys.platform!='darwin':font.setPointSizeF(max(10.,font.pointSizeF()))
    font.setWeight(QFont.Weight.Normal);font.setStretch(QFont.Stretch.Unstretched)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing,100);font.setKerning(True)
    app.setFont(font)
    actual=QFontInfo(app.font()).family()
    apple=sys.platform=='darwin' and (actual in SF_FAMILIES or actual.startswith(('.SF','SF Pro','.AppleSystemUIFont')))
    status=('San Francisco' if apple else actual)+' · fuente del sistema'
    app.typography_family=actual;app.typography_status=status;app.typography_is_apple=apple
    app.typography_is_mori=False # Read-only compatibility with older preference/test clients.
    return status
