#!/usr/bin/env bash
#!/usr/bin/env bash
# Installer script for game-session-guard

set -euo pipefail

APP_DIR="/opt/game-session-guard"
BIN_DIR="/usr/local/bin"
CONFIG_DIR="/etc/game-session-guard"
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

if [[ "$EUID" -ne 0 ]]; then
  echo "[!] Run the installer with sudo: sudo ./install.sh" >&2
  exit 1
fi

command -v python3 >/dev/null || { echo "[!] python3 is required." >&2; exit 1; }
echo "[*] Creating isolated Python environment..."
install -d -m 0755 "$APP_DIR" "$CONFIG_DIR"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install --quiet psutil

echo "[*] Installing application files..."
install -m 0644 "$SCRIPT_DIR/gameguard.py" "$APP_DIR/gameguard.py"
if [[ ! -f "$CONFIG_DIR/config.json" ]]; then
  install -m 0644 "$SCRIPT_DIR/config.json" "$CONFIG_DIR/config.json"
fi
printf '%s\n' '#!/usr/bin/env bash' \
  "exec \"$APP_DIR/venv/bin/python\" \"$APP_DIR/gameguard.py\" \"\$@\"" \
  > "$BIN_DIR/gameguard"
chmod 0755 "$BIN_DIR/gameguard"

echo "[+] Installation completed."
echo "Open the settings window with: gameguard --gui"
echo "Start monitoring from a terminal with: gameguard --start"
echo "Tkinter may need to be installed separately (for example, python3-tk on Debian/Ubuntu)."
