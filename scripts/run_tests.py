"""Keep complete unittest failures visible in public Actions annotations."""
import os
import sys

from build_desktop import checked_run


if __name__ == '__main__':
    environment = os.environ.copy()
    environment['PYTHONIOENCODING'] = 'utf-8'
    checked_run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v'],
                encoding='utf-8', env=environment)
