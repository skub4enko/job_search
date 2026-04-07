@echo off
setlocal
cd /d %~dp0\..

if not exist JobSearchUA_parser.py (
  echo Entry not found: JobSearchUA_parser.py
  exit /b 1
)

if not exist assets\icon.ico (
  echo Icon not found: assets\icon.ico
  exit /b 1
)

pyinstaller --noconfirm --clean --onefile --runtime-tmpdir ".\_pyi_tmp" --console --name JobSearchUA_Parser --icon assets\icon.ico ^
  --add-data "assets\beep.mp3;assets" ^
  JobSearchUA_parser.py

if exist dist\JobSearchUA_Parser.exe (
  echo OK: %cd%\dist\JobSearchUA_Parser.exe
  exit /b 0
)

echo Build finished, but EXE not found.
exit /b 1
