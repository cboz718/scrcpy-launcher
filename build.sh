#!/usr/bin/env bash
set -e

echo "=== scrcpy Launcher Build (macOS) ==="
echo

# Check dependencies
missing=()
python3 -c "import PIL" 2>/dev/null || missing+=("pillow")
python3 -c "import PyInstaller" 2>/dev/null || missing+=("pyinstaller")
if [ ${#missing[@]} -gt 0 ]; then
    echo "Missing build dependencies: ${missing[*]}"
    echo "Install them with: pip3 install ${missing[*]}"
    exit 1
fi

echo "Generating icon..."
python3 build_icon.py

echo
echo "Building application with PyInstaller..."
pyinstaller --onefile --noconsole \
    --name "scrcpy Launcher" \
    --icon=launcher.icns \
    --add-data "azure-theme:azure-theme" \
    --add-data "launcher.icns:." \
    launcher.pyw

echo
echo "Creating distribution zip..."
cd dist
zip -j scrcpy-launcher-mac.zip "scrcpy Launcher" \
    ../custom_args.txt \
    ../mirror.bat ../mirror.sh \
    ../record_video.bat ../record_video.sh \
    ../tcpip.bat ../tcpip.sh
cd ..

echo
echo "Build complete!"
echo "  Executable: dist/scrcpy Launcher"
echo "  Zip:        dist/scrcpy-launcher-mac.zip"
