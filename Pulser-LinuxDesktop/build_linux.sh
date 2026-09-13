#!/usr/bin/env bash
set -euo pipefail

APP_NAME="HealthTracker"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"
INSTALL_DIR="$HOME/.local/share/healthtracker"
DESKTOP_DIR="$HOME/.local/share/applications"

cd "$SCRIPT_DIR"

echo "== Checking for tkinter =="
if ! python3 -c "import tkinter" 2>/dev/null; then
    echo "tkinter not found - installing python3-tkinter (you'll be asked for your password)..."
    sudo dnf install -y python3-tkinter
fi

echo "== Creating a virtual environment (.venv) =="
python3 -m venv .venv
. .venv/bin/activate

echo "== Installing build dependencies =="
pip install --upgrade pip
pip install -r requirements.txt

echo "== Building the app =="
pyinstaller --noconfirm --onefile --name "$APP_NAME" --collect-all customtkinter app.py

echo "== Installing to $INSTALL_DIR =="
mkdir -p "$INSTALL_DIR"
cp "dist/$APP_NAME" "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/$APP_NAME"
cp "healthtracker.svg" "$INSTALL_DIR/"

echo "== Adding a GNOME menu entry =="
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/healthtracker.desktop" <<DESKTOP
[Desktop Entry]
Type=Application
Name=Health Tracker
Comment=Log and chart your heart rate and pulse
Exec=$INSTALL_DIR/$APP_NAME
Icon=$INSTALL_DIR/healthtracker.svg
Terminal=false
Categories=Utility;
DESKTOP

update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo
echo "Done. Search \"Health Tracker\" in GNOME Activities, or run:"
echo "  $INSTALL_DIR/$APP_NAME"
