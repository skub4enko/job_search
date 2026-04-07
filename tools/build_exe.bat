@echo off
setlocal
cd /d %~dp0\..

if not exist JobSearchUA.pyw (
  echo Entry not found: JobSearchUA.pyw
  exit /b 1
)

if not exist assets\icon.ico (
  echo Icon not found: assets\icon.ico
  exit /b 1
)

REM Preflight Tkinter (required for GUI build)
for %%I in (pyinstaller.exe) do set "PYINSTALLER=%%~fI"
if "%PYINSTALLER%"=="" (
  echo ERROR: pyinstaller.exe not found in PATH.
  exit /b 1
)
for %%I in ("%PYINSTALLER%") do set "PYROOT=%%~dpI.."
set "PYEXE=%PYROOT%\python.exe"
"%PYEXE%" -c "import tkinter, _tkinter; print('TK_IMPORT_OK')" >nul 2>nul
if errorlevel 1 (
  echo ERROR: Tkinter/Tcl/Tk is not working in this Python installation.
  echo Python: %PYEXE%
  echo Fix: reinstall/repair Python 3.12 with "tcl/tk and IDLE" enabled, then re-run this build.
  exit /b 1
)

pyinstaller --noconfirm --clean --additional-hooks-dir "tools\pyinstaller_hooks" --onefile --runtime-tmpdir ".\_pyi_tmp" --windowed --name JobSearchUA --icon assets\icon.ico ^
  --add-data "assets\icon.ico;assets" ^
  --add-data "assets\icon.png;assets" ^
  --add-data "assets\beep.mp3;assets" ^
  --add-data "tools\tcl8.6.13\library;_tcl_data" ^
  --add-data "%PYROOT%\tcl\tcl8.6;_tcl_data" ^
  --add-data "%PYROOT%\tcl\tk8.6;_tk_data" ^
  --add-data "%PYROOT%\Lib\tkinter;tkinter" ^
  --hidden-import tkinter --hidden-import _tkinter ^
  JobSearchUA.pyw

if exist dist\JobSearchUA.exe (
  echo OK: %cd%\dist\JobSearchUA.exe
  exit /b 0
)

echo Build finished, but EXE not found.
exit /b 1
