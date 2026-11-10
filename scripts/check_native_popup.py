"""Inspect our actual Win32 popup frame, keyboard behavior and capture both themes."""
import argparse,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from importios.native import Window


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    app=QApplication([]);app.setApplicationName('TUPAQ-popup-check')
    if sys.platform!='win32' or app.platformName()!='windows':
        raise RuntimeError('This check requires the native Windows Qt platform')
    import ctypes
    get_style=ctypes.windll.user32.GetWindowLongW
    get_style.argtypes=[ctypes.c_void_p,ctypes.c_int];get_style.restype=ctypes.c_long
    window=Window(auto_connect=False);window.resize(1280,800);window.show();QTest.qWait(150)
    results=[]
    try:
        for name,theme in [('light',1),('dark',2)]:
            window.theme_choice.setCurrentIndex(theme);app.processEvents()
            combo=window.format_filter;combo.setCurrentIndex(0);combo.showPopup();QTest.qWait(120)
            popup=combo.view().window();style=get_style(int(popup.winId()),-16)
            # Win32's old square caption/border/resizing frame must be absent.
            assert not style & (0x00C00000|0x00040000),hex(style)
            assert not popup.mask().contains(popup.rect().topLeft())
            assert popup.mask().contains(popup.rect().center())
            pixmap=popup.screen().grabWindow(int(popup.winId()))
            assert not pixmap.isNull()
            assert pixmap.save(str(args.output/f'popup-{name}.png'))
            QTest.keyClick(combo.view(),Qt.Key.Key_Down);QTest.keyClick(combo.view(),Qt.Key.Key_Return);app.processEvents()
            assert combo.currentIndex()==1 and not popup.isVisible()
            combo.showPopup();app.processEvents();QTest.keyClick(combo.view(),Qt.Key.Key_Escape);app.processEvents()
            assert not popup.isVisible() and combo.currentIndex()==1
            results.append({'theme':name,'native_square_frame':False,'rounded_mask':True,'keyboard':True})
        (args.output/'native-popup-check.json').write_text(json.dumps({'platform':app.platformName(),'results':results},indent=2))
    finally:window.close();app.processEvents()


if __name__=='__main__':
    try:main()
    except Exception:
        import os,traceback
        if os.environ.get('GITHUB_ACTIONS')=='true':
            message=traceback.format_exc()[-3500:].replace('%','%25').replace('\r','%0D').replace('\n','%0A')
            print('::error title=Native popup check::'+message,flush=True)
        raise
