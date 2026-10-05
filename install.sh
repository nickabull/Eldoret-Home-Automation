#!/bin/bash
set -eu

ROOT="$HOME/eldoret-connector"
ENV_DIR="$HOME/.config"
ENV_FILE="$ENV_DIR/eldoret.env"
USER_SYSTEMD="$HOME/.config/systemd/user"
SERVICE="$USER_SYSTEMD/eldoret.service"

mkdir -p "$ROOT" "$ENV_DIR" "$USER_SYSTEMD"

if [ -z "${HUE_KEY:-}" ] || [ -z "${UTILITY_HUE_KEY:-}" ]; then
  echo "Hue keys are not available in this Terminal session."
  echo "Export HUE_KEY and UTILITY_HUE_KEY first, then run this installer again."
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<EOF
HUE_KEY=$HUE_KEY
UTILITY_HUE_KEY=$UTILITY_HUE_KEY
SKY_Q_HOST=10.0.0.18
EOF
chmod 600 "$ENV_FILE"

curl -fsSL -o "$ROOT/manager.py" "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/manager.py"
curl -fsSL -o "$ROOT/connector.py" "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/connector.py"

cat > "$SERVICE" <<EOF
[Unit]
Description=Eldoret Home Automation
After=network-online.target

[Service]
Type=simple
EnvironmentFile=$ENV_FILE
ExecStart=/usr/bin/python3 $ROOT/manager.py
Restart=always
RestartSec=3

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable eldoret.service
systemctl --user restart eldoret.service

echo
echo "Eldoret is installed as a user service."
echo "It will check GitHub for connector updates every 30 seconds."
echo "Open http://localhost:8765 or the Chromebook LAN address on port 8765."
