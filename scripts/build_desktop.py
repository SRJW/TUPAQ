"""Build on the target OS; PyInstaller does not cross-compile."""

from pathlib import Path
import platform
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def checked_run(command, **options):
    options.pop('check', None)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, **options)
    print(result.stdout, end='', flush=True)
    if result.returncode:
        if os.environ.get('GITHUB_ACTIONS') == 'true':
            message = result.stdout[-3500:].replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
            print('::error title=Error al empaquetar::'+message, flush=True)
        raise subprocess.CalledProcessError(result.returncode, command)


def main():
    system = platform.system()
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--name', 'TUPAQ', '--windowed',
               '--add-data', 'third_party:third_party',
               '--add-data', 'importios/assets/tupaq.png:importios/assets',
               '--collect-submodules', 'mutagen', '--exclude-module', 'tkinter']
    from PySide6.QtCore import QLibraryInfo
    translations=Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath))
    spanish=translations/'qtbase_es.qm'
    if not spanish.is_file():raise RuntimeError('Spanish Qt translations are missing')
    from PyInstaller.utils.hooks.qt import pyside6_library_info
    destination=Path(pyside6_library_info.qt_rel_dir)/'translations'
    command += ['--add-data', str(spanish)+':'+str(destination)]
    if system == 'Windows':
        command += ['--onefile','--icon',str(ROOT/'importios'/'assets'/'tupaq.ico')]
    else:
        command += ['--onedir']
    if system == 'Darwin':
        command += ['--osx-bundle-identifier', 'io.importios.desktop',
                    '--icon',str(ROOT/'importios'/'assets'/'tupaq.icns')]
    checked_run(command + ['desktop.py'], cwd=ROOT, check=True)
    if system == 'Darwin':
        destination = ROOT/'dist'/f'TUPAQ-macOS-{platform.machine()}.dmg'
        # Stage only the app and an Applications shortcut in the disk image.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='importios-dmg-') as temporary:
            stage = Path(temporary)
            checked_run(['ditto', str(ROOT/'dist'/'TUPAQ.app'), str(stage/'TUPAQ.app')], check=True)
            (stage/'Applications').symlink_to('/Applications')
            checked_run(['hdiutil', 'create', '-volname', 'TUPAQ', '-srcfolder',
                            str(stage), '-ov', '-format', 'UDZO', str(destination)], check=True)
        checked_run(['hdiutil', 'verify', str(destination)], check=True)
        (ROOT/'dist'/'mounted-dmg').mkdir(exist_ok=True)
        checked_run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint',
                        str(ROOT/'dist'/'mounted-dmg'), str(destination)], check=True)
        try:
            checked_run([sys.executable, 'scripts/smoke_desktop.py',
                            str(ROOT/'dist'/'mounted-dmg'/'TUPAQ.app'/'Contents'/'MacOS'/'TUPAQ')],
                           cwd=ROOT, check=True)
        finally:
            checked_run(['hdiutil', 'detach', str(ROOT/'dist'/'mounted-dmg')], check=True)


if __name__ == '__main__':
    main()
