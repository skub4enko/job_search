@echo off
setlocal
cd /d %~dp0

if exist "venv\Scripts\pythonw.exe" (
    start "" "venv\Scripts\pythonw.exe" "JobSearchUA.pyw"
) else if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "JobSearchUA.pyw"
) else (
    start "" pythonw "JobSearchUA.pyw"
)

exit