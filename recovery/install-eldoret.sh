#!/usr/bin/env bash
# Bulldog Recovery v1. Run on a freshly flashed Raspberry Pi OS Desktop as your usual user.
set -Eeuo pipefail
HERE="$(cd -- "$(dirname -- "$0")" && pwd)"
ROOT="$HOME/eldoret-connector"
ENVFILE="$HOME/.config/eldoret.env"
REPO="https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main"
LOG="$HOME/bulldog-recovery-install.log"
exec > >(tee -a "$LOG") 2>&1
echo "BULLDOG RECOVERY v1 | $(date)"
if [ "$(id -u)" -eq 0 ]; then echo "Please run as normal Pi user, not root."; exit 1; fi
if [ "$(uname -s)" != "Linux" ]; then echo "Pi/Linux installation only."; exit 1; fi
if [ ! -f "$HERE/backup-restore.py" ]; then echo "Missing backup-restore.py"; exit 1; fi
if systemctl is-active --quiet eldoret.service; then
 echo "Eldoret already running. Refusing to replace it."; exit 1
fi
if [ -e "$ENVFILE" ] || [ -e "$ROOT/manager.py" ] || [ -e "$ROOT/connector.py" ]; then
 echo "Existing Eldoret files found. This tool only works on a clean install."; exit 1
fi
echo "A private backup must have been created before the old SD card failed."
read -r -p "Full path to verified private backup .tar.gz: " ARCHIVE
test -f "$ARCHIVE" || { echo "Archive not found"; exit 1; }
python3 "$HERE/backup-restore.py" verify --archive "$ARCHIVE"
echo
echo "This will install required Linux packages, restore private settings, and start Eldoret."
read -r -p "Type INSTALL to continue: " CONFIRM
[ "$CONFIRM" = "INSTALL" ] || { echo "Cancelled."; exit 1; }
sudo apt-get update
sudo apt-get install -y python3 ca-certificates curl snmp
STAGE="$(mktemp -d)"
trap 'rm -rf -- "$STAGE"' EXIT
for FILE in manager.py connector.py; do
 if [ -s "$HERE/$FILE" ]; then
   cp -- "$HERE/$FILE" "$STAGE/$FILE"
 else
   curl -fsSL --max-time 35 "$REPO/$FILE" -o "$STAGE/$FILE"
 fi
 test -s "$STAGE/$FILE"
done
python3 -m py_compile "$STAGE/manager.py" "$STAGE/connector.py"
python3 "$HERE/backup-restore.py" restore --archive "$ARCHIVE" --home "$HOME"
install -d -m 700 "$ROOT"
install -m 600 "$STAGE/manager.py" "$ROOT/manager.py"
install -m 600 "$STAGE/connector.py" "$ROOT/connector.py"
USER_NAME="$(id -un)"
case "$HOME" in *$'\n'*|*' '*|*'%'*) echo "Unsupported home path"; exit 1;; esac
case "$USER_NAME" in *[!a-zA-Z0-9_-]*|"") echo "Unsupported user name"; exit 1;; esac
cat > "$STAGE/eldoret.service" <<EOF
[Unit]
Description=Eldoret Home Automation (Bulldog)
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
Environment=HOME=$HOME
EnvironmentFile=$ENVFILE
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $ROOT/manager.py
Restart=always
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF
sudo install -m 644 "$STAGE/eldoret.service" /etc/systemd/system/eldoret.service
sudo systemctl daemon-reload
sudo systemctl enable --now eldoret.service
sleep 5
if systemctl is-active --quiet eldoret.service; then
 echo "PASS: Eldoret service active."
else
 echo "WARNING: Eldoret service not active; check sudo journalctl -u eldoret -n 50"
 exit 1
fi
if curl -fsS --max-time 8 http://127.0.0.1:8765/api/lg/discovery >/dev/null; then
 echo "PASS: local connector HTTP server responding."
else
 echo "WARNING: local HTTP health not yet confirmed."
fi
echo "DONE. Open http://$(hostname -I | awk '{print $1}'):8765/"
echo "Still verify Hue, Sky, router, UniFi, Home Connect, physical screen and kiosk."
echo "Installation log: $LOG"
