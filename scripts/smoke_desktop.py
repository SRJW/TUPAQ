"""Run a real frozen native UI, including its bundled Qt platform plugin."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    executable = Path(sys.argv[1]).resolve()
    with tempfile.TemporaryDirectory(prefix='importios-smoke-') as temporary:
        report = Path(temporary)/'result.txt'
        environment = os.environ.copy()
        environment['QT_QPA_PLATFORM'] = 'offscreen'
        subprocess.run([str(executable), '--smoke-fixtures', str(ROOT/'tests'/'fixtures'),
                        '--smoke-report', str(report)], env=environment, check=True, timeout=90)
        if not report.exists() or report.read_text(encoding='ascii') != 'native-ui-smoke-passed':
            raise RuntimeError('The frozen native UI did not complete its checks')
    print('Native package passed: Qt UI, worker, four formats, duplicates, corrupt audio, CSV, remove, clear.')


if __name__ == '__main__':
    main()
