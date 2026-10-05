# Eldoret Chromebook runtime

The Chromebook runtime can be installed as a per-user systemd service.

- `manager.py` checks GitHub for a newer `connector.py` every 30 seconds.
- When `connector.py` changes, the manager restarts the connector automatically.
- Hue credentials remain only in `~/.config/eldoret.env` on the Chromebook (mode 600).
- The service restarts automatically if the connector crashes.

The public repository contains no Hue credentials.
