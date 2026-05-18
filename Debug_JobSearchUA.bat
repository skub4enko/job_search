@echo off
chcp 65001 > nul
title JobSearchUA Debug Mode
echo ========================================
echo    JobSearchUA Debug Mode
echo ========================================
echo.
echo Запуск в консольном режиме для отладки...
echo Если увидите ошибку — сделайте скриншот и пришлите.
echo ========================================
echo.

cd /d "%~dp0"

if exist "dist\\JobSearchUA.exe" (
  "dist\\JobSearchUA.exe"
) else if exist "JobSearchUA_standalone.exe" (
  "JobSearchUA_standalone.exe"
) else (
  echo EXE не найден.
  echo Соберите его одной из команд:
  echo   powershell -NoProfile -ExecutionPolicy Bypass -File tools\\build_exe.ps1
  echo   python compile_to_exe.py
)

echo.
echo ========================================
echo Программа завершила работу
echo ========================================
pause
