@echo off
setlocal
title Importios
cd /d "%~dp0.."
if exist ".venv\Scripts\python.exe" goto run
echo Preparando Importios por primera vez...
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" >nul 2>&1
if errorlevel 1 goto python_missing
py -3 -m venv .venv
if errorlevel 1 goto failed
:run
".venv\Scripts\python.exe" -c "import mutagen, PySide6, Cryptodome; assert mutagen.version_string == '1.47.0' and PySide6.__version__ == '6.10.2' and Cryptodome.__version__ == '3.24.1'" >nul 2>&1
if not errorlevel 1 goto start
".venv\Scripts\python.exe" -m pip install -r requirements-desktop.txt
if errorlevel 1 goto failed
:start
".venv\Scripts\python.exe" -m importios.native
if errorlevel 1 goto failed
exit /b 0
:python_missing
echo Necesitas Python 3.11 o posterior para esta version de desarrollo.
echo Instala Python desde https://www.python.org/downloads/windows/
echo Incluye el lanzador py en la instalacion y vuelve a abrir este archivo.
pause
exit /b 1
:failed
echo No se pudo abrir Importios. Comparte el mensaje que aparece arriba.
pause
exit /b 1
