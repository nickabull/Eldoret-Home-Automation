#!/bin/bash
set -eu

ROOT="/opt/eldoret"
ENV_FILE="/etc/eldoret.env"
SERVICE="/etc/systemd/system/eldoret.service"
BASE="https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main"

if [ "$(id -u)" -ne 0 ]; then
  echo "Run this installer with sudo."
  exit 1
fi

mkdir -p "$ROOT"

echo "Eldoret Raspberry Pi installer"
echo
read -r -p "House Hue key: " HUE_KEY
read -r -p "Utility Hue key: " UTILITY_HUE_KEY
read -r -p "Sky Q IP [10.0.0.18]: " SKY_Q_HOST
SKY_Q_HOST="${SKY_Q_HOST:-10.0.0.18}"

umask 077
cat > "$ENV_FILE" <<EOF
HUE_KEY=$HUE_KEY
UTILITY_HUE_KEY=$UTILITY_HUE_KEY
SKY_Q_HOST=$SKY_Q_HOST
EOF
chmod 600 "$ENV_FILE"

curl -fsSL -o "$ROOT/manager.py" "$BASE/manager.py"
curl -fsSL -o "$ROOT/connector.py" "$BASE/connector.py"

cat > "$SERVICE" <<EOF
[Unit]
Description=Eldoret Home Automation
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
WorkingDirectory=$ROOT
ExecStart=/usr/bin/python3 $ROOT/manager.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable eldoret.service
systemctl restart eldoret.service

echo
echo "Eldoret is installed and enabled at boot."
echo "The connector will self-update from GitHub."
echo "Use: systemctl status eldoret"
