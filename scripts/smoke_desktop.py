"""Run a real frozen native UI, including its bundled Qt platform plugin."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def verify_brand_icon(executable):
    """Check native package resources, not just the icon drawn inside Qt."""
    assets=ROOT/'importios'/'assets'
    if sys.platform=='win32':
        import struct
        ico=(assets/'tupaq.ico').read_bytes()
        reserved,kind,count=struct.unpack_from('<HHH',ico)
        if (reserved,kind)!=(0,1) or not count:raise RuntimeError('Invalid Windows brand icon')
        binary=executable.read_bytes()
        for index in range(count):
            length,offset=struct.unpack_from('<II',ico,6+16*index+8)
            if not length or ico[offset:offset+length] not in binary:
                raise RuntimeError('The Windows executable is missing a brand icon frame')
    elif sys.platform=='darwin':
        import plistlib
        contents=executable.parents[1]
        info=plistlib.loads((contents/'Info.plist').read_bytes())
        name=info.get('CFBundleIconFile','')
        if not name:raise RuntimeError('The Mac bundle has no icon reference')
        if not name.endswith('.icns'):name+='.icns'
        if (contents/'Resources'/name).read_bytes()!=(assets/'tupaq.icns').read_bytes():
            raise RuntimeError('The Mac bundle does not contain the approved brand icon')


def main():
    executable = Path(sys.argv[1]).resolve()
    verify_brand_icon(executable)
    with tempfile.TemporaryDirectory(prefix='importios-smoke-') as temporary:
        report = Path(temporary)/'result.txt'
        environment = os.environ.copy()
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        subprocess.run([str(executable), '--smoke-fixtures', str(ROOT/'tests'/'fixtures'),
                        '--smoke-report', str(report)], env=environment, check=True, timeout=90)
        if not report.exists() or report.read_text(encoding='ascii') != 'native-ui-smoke-passed':
            raise RuntimeError('The frozen native UI did not complete its checks')
    print('Native package passed: Encuentro icon, Qt UI, Spanish/English switching, bundled translations, audio formats/covers, CSV, iOS 27 catalogue, transfer worker, local lock, progress and controls (simulated USB).')


if __name__ == '__main__':
    main()
