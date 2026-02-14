@echo off
echo === scrcpy Launcher Build ===
echo.

echo Generating icon...
python build_icon.py
if errorlevel 1 (
    echo Icon generation failed.
    pause
    exit /b 1
)

echo.
echo Building executable with PyInstaller...
pyinstaller --onefile --noconsole --name "scrcpy Launcher" --icon=launcher.ico --add-data "azure-theme;azure-theme" --add-data "launcher.ico;." launcher.pyw
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Creating distribution zip...
powershell -NoProfile -Command "if (Test-Path 'dist\scrcpy-launcher-windows.zip') { Remove-Item 'dist\scrcpy-launcher-windows.zip' }; $files = @('dist\scrcpy Launcher.exe', 'custom_args.txt', 'mirror.bat', 'mirror.sh', 'record_video.bat', 'record_video.sh', 'tcpip.bat', 'tcpip.sh'); Compress-Archive -Path $files -DestinationPath 'dist\scrcpy-launcher-windows.zip'"
if errorlevel 1 (
    echo Zip creation failed.
    pause
    exit /b 1
)

echo.
echo Build complete!
echo   Executable: dist\scrcpy Launcher.exe
echo   Zip:        dist\scrcpy-launcher-windows.zip
pause
