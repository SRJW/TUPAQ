"""Lightweight native audio preview player (macOS afplay, Windows MediaPlayer, Linux ffplay/paplay)."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

from .transcode import find_ffmpeg


class AudioPreviewPlayer:
    """Manage a single non-blocking local audio preview subprocess cleanly."""
    def __init__(self):
        self._process = None
        self._current_path = None

    @property
    def is_playing(self):
        return self._process is not None and self._process.poll() is None

    @property
    def current_path(self):
        return self._current_path if self.is_playing else None

    @staticmethod
    def _build_command(path):
        target = str(Path(path).resolve())
        if sys.platform == 'darwin':
            if Path('/usr/bin/afplay').is_file():
                return ['/usr/bin/afplay', target]
        elif os.name == 'nt':
            # Use Windows built-in PresentationCore MediaPlayer (supports MP3, M4A/AAC/ALAC, WAV).
            escaped = target.replace("'", "''")
            script = (
                "Add-Type -AssemblyName presentationCore; "
                "$p = New-Object System.Windows.Media.MediaPlayer; "
                f"$p.Open([Uri]'{escaped}'); "
                "$p.Play(); "
                "Start-Sleep -Milliseconds 400; "
                "$deadline = (Get-Date).AddMinutes(15); "
                "while ((Get-Date) -lt $deadline) { "
                "if ($p.NaturalDuration.HasTimeSpan -and $p.Position -ge $p.NaturalDuration.TimeSpan) { break }; "
                "Start-Sleep -Milliseconds 250 }; "
                "$p.Close()"
            )
            return ['powershell', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden', '-Command', script]
        else:
            ffplay = shutil.which('ffplay')
            if not ffplay:
                ffmpeg = find_ffmpeg()
                if ffmpeg:
                    candidate = Path(ffmpeg).with_name('ffplay')
                    if candidate.is_file():
                        ffplay = str(candidate)
            if ffplay:
                return [ffplay, '-nodisp', '-autoexit', '-loglevel', 'quiet', target]
            paplay = shutil.which('paplay')
            if paplay and Path(target).suffix.lower() in ('.wav', '.aif', '.aiff', '.ogg', '.flac'):
                return [paplay, target]
        return None

    def play(self, path):
        self.stop()
        target = Path(path)
        if not target.is_file():
            raise ValueError('No se encontró el archivo de audio para reproducir.')
        command = self._build_command(target)
        if not command:
            raise ValueError('No hay reproductor de audio disponible en este sistema.')
        creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
        self._process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        self._current_path = str(target)

    def stop(self):
        proc = self._process
        self._process = None
        self._current_path = None
        if proc is not None and proc.poll() is None:
            try:
                proc.terminate()
                proc.wait(timeout=1.5)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
