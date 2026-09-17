@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (echo Python launcher not found. Install Python 3.12+ and try again.&pause&exit /b 1)
if not exist .venv py -3 -m venv .venv
call .venv\Scripts\python.exe -m pip install --upgrade pip
call .venv\Scripts\python.exe -m pip install -r requirements.txt
if not exist data mkdir data
if not exist projects mkdir projects
if not exist output mkdir output
if not exist assets mkdir assets
if not exist logs mkdir logs
echo Setup complete.
pause
endlocal
