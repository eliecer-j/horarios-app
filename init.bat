@echo off
cd /d "C:\horarios app"

start "" /B .venv\Scripts\waitress-serve.exe --listen=0.0.0.0:8000 horarios_project.wsgi:application

exit