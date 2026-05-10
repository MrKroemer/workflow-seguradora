@echo off
for %%I in ("%~dp0..") do set "ROOT_DIR=%%~fI"
cd /d "%ROOT_DIR%"
set "PYTHONPATH=%ROOT_DIR%\src"

if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" -m rpa_corretora.agent
) else (
    where pythonw >nul 2>nul
    if %ERRORLEVEL%==0 (
        start "" pythonw -m rpa_corretora.agent
    ) else (
        start "" py -3 -m rpa_corretora.agent
    )
)
