@echo off
REM ======== CONFIG VAKI SUSHI POS ========
REM Cambia estas rutas por las tuyas

REM Ruta del proyecto
cd /d C:\vaki_sushi_pos

REM Activar entorno virtual (si usas venv)
call venv\Scripts\activate.bat

REM Levantar el servidor uvicorn
uvicorn main:app --reload --host 0.0.0.0 --port 8000

REM Para que la ventana no se cierre sola si hay error
pause
