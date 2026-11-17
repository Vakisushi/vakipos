@echo off
setlocal
cd /d "%~dp0"

"%~dp0venv\Scripts\python.exe" -m PyInstaller ^
  --noconfirm ^
  --clean ^
  --windowed ^
  --name "Vaki Sushi POS" ^
  --collect-all sqlmodel ^
  --add-data "desktop_app\assets;desktop_app\assets" ^
  "%~dp0desktop_main.py"

if errorlevel 1 (
    echo Error al construir el ejecutable.
    pause
    exit /b 1
)

if not exist "%~dp0dist\Vaki Sushi POS\sushi_pos.db" (
    copy "%~dp0sushi_pos.db" "%~dp0dist\Vaki Sushi POS\sushi_pos.db" >nul
)

set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ISCC%" (
    "%ISCC%" "%~dp0instalador_vaki_sushi.iss"
)

echo.
echo Aplicacion creada en:
echo   dist\Vaki Sushi POS\Vaki Sushi POS.exe
if exist "%~dp0installer\Instalar Vaki Sushi POS.exe" (
    echo Instalador creado en:
    echo   installer\Instalar Vaki Sushi POS.exe
)
pause
