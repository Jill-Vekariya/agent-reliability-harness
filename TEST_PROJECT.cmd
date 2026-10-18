@echo off
cd /d "%~dp0"
docker compose build
if errorlevel 1 exit /b 1
set "ARH_TEST_IMAGE="
for /f "delims=" %%I in ('docker compose config --images') do set "ARH_TEST_IMAGE=%%I"
if not defined ARH_TEST_IMAGE exit /b 2
echo Running tests in %ARH_TEST_IMAGE%
docker run --rm --network none --read-only --tmpfs /tmp:size=64m --tmpfs /reports:uid=10001,gid=10001,mode=1777 --memory 768m --cpus 2 --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges "%ARH_TEST_IMAGE%" python -m pytest -q -p no:cacheprovider
if errorlevel 1 exit /b 1
docker run --rm --network none --read-only --tmpfs /tmp:size=64m --tmpfs /reports:uid=10001,gid=10001,mode=1777 --memory 768m --cpus 2 --pids-limit 64 --cap-drop ALL --security-opt no-new-privileges -e ARH_ARTIFACT_DIR=/reports "%ARH_TEST_IMAGE%" arh eval
if errorlevel 1 exit /b 1
pause
exit /b 0
