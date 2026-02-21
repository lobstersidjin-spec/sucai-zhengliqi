@echo off
REM Launch 点点素材管理大师 GUI (no console)
cd /d "%~dp0\.."
if exist "start_gui.pyw" (
    start "" pythonw.exe "start_gui.pyw"
) else if exist "main.py" (
    start "" pythonw.exe "main.py"
) else (
    start "" pythonw.exe "organizer_gui.py"
)
