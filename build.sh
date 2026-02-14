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
echo "Bundling scripts and configs into .app..."
RESOURCES="dist/scrcpy Launcher.app/Contents/Resources"
cp custom_args.txt env.sh "$RESOURCES/"
cp mirror.sh record_video.sh tcpip.sh "$RESOURCES/"

echo
echo "Creating distribution zip..."
cd dist
zip -r scrcpy-launcher-mac.zip "scrcpy Launcher.app"
cd ..

echo
echo "Build complete!"
echo "  App:  dist/scrcpy Launcher.app"
echo "  Zip:  dist/scrcpy-launcher-mac.zip"
