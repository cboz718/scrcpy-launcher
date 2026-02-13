@echo off
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set timestamp=%%i
if not exist "%~dp0Recordings" mkdir "%~dp0Recordings"

scrcpy.exe --audio-codec=aac --record=Recordings\screen_recording_%timestamp%.mp4 --no-audio-playback --video-buffer=50 --audio-buffer=50 --show-touches --stay-awake --pause-on-exit=if-error %*
