@echo off
cd /d "%~dp0"
docker compose build
if errorlevel 1 exit /b 1
docker run --rm --network none --read-only --tmpfs /tmp:size=64m --tmpfs /reports:uid=10001,gid=10001,mode=1777 --memory 768m --cpus 2 --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges agent-reliability-harness:0.1.0 python -m pytest -q -p no:cacheprovider
if errorlevel 1 exit /b 1
docker run --rm --network none --read-only --tmpfs /tmp:size=64m --tmpfs /reports:uid=10001,gid=10001,mode=1777 --memory 768m --cpus 2 --cap-drop ALL --security-opt no-new-privileges -e ARH_ARTIFACT_DIR=/reports agent-reliability-harness:0.1.0 arh eval
pause
