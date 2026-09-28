#!/usr/bin/env bash
# Installer script for game-session-guard

set -e

INSTALL_DIR="/usr/local/bin"
SCRIPT_NAME="gameguard"

if [ "$EUID" -ne 0 ]; then
  echo "[!] Please run installer as root (sudo ./install.sh)"
  exit 1
fi

echo "[*] Installing Python dependencies (psutil)..."
python3 -m pip install psutil --quiet || true

echo "[*] Installing gameguard to $INSTALL_DIR/$SCRIPT_NAME..."
cp gameguard.py "$INSTALL_DIR/$SCRIPT_NAME"
cp config.json "$INSTALL_DIR/gameguard_config.json"
chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "[✓] Installation completed successfully!"
echo "Run 'sudo gameguard' for maximum process priority boosting & RAM clearing."
