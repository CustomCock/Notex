@echo off
rem Baut die App unter Windows (Name aus notex/__init__.py). Voraussetzung: Python 3.12 im PATH.
cd /d "%~dp0"
if not exist venv (
    python -m venv venv
)
call venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
python build.py
echo.
echo Ergebnis liegt in dist\ (Ordner = App-Name)
pause
