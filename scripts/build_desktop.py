"""Build on the target OS; PyInstaller does not cross-compile."""

from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    system = platform.system()
    command = [sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
               '--name', 'Importios', '--windowed',
               '--add-data', 'third_party:third_party',
               '--collect-submodules', 'mutagen']
    if system == 'Windows':
        command += ['--onefile']
    else:
        command += ['--onedir']
    if system == 'Darwin':
        command += ['--osx-bundle-identifier', 'io.importios.desktop']
    subprocess.run(command + ['desktop.py'], cwd=ROOT, check=True)
    if system == 'Darwin':
        destination = ROOT/'dist'/f'Importios-macOS-{platform.machine()}.dmg'
        # Stage only the app and an Applications shortcut in the disk image.
        import tempfile
        with tempfile.TemporaryDirectory(prefix='importios-dmg-') as temporary:
            stage = Path(temporary)
            subprocess.run(['ditto', str(ROOT/'dist'/'Importios.app'), str(stage/'Importios.app')], check=True)
            (stage/'Applications').symlink_to('/Applications')
            subprocess.run(['hdiutil', 'create', '-volname', 'Importios', '-srcfolder',
                            str(stage), '-ov', '-format', 'UDZO', str(destination)], check=True)
        subprocess.run(['hdiutil', 'verify', str(destination)], check=True)
        (ROOT/'dist'/'mounted-dmg').mkdir(exist_ok=True)
        subprocess.run(['hdiutil', 'attach', '-readonly', '-nobrowse', '-mountpoint',
                        str(ROOT/'dist'/'mounted-dmg'), str(destination)], check=True)
        try:
            subprocess.run([sys.executable, 'scripts/smoke_desktop.py',
                            str(ROOT/'dist'/'mounted-dmg'/'Importios.app'/'Contents'/'MacOS'/'Importios')],
                           cwd=ROOT, check=True)
        finally:
            subprocess.run(['hdiutil', 'detach', str(ROOT/'dist'/'mounted-dmg')], check=True)


if __name__ == '__main__':
    main()
