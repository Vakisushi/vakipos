@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\pythonw.exe" "%~dp0desktop_main.py"
if errorlevel 1 (
    echo No se pudo iniciar Vaki Sushi POS.
    echo Ejecuta primero:
    echo   venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
)
