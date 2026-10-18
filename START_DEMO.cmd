@echo off
cd /d "%~dp0"
echo Building and launching the offline demo. No API key is needed.
docker compose up --build -d
if errorlevel 1 (
  echo Start Docker Desktop and retry. See docs\DEMO.md.
  pause
  exit /b 1
)
start http://localhost:8501
echo Demo: http://localhost:8501
pause
