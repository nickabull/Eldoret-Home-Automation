# Raspberry Pi migration

Eldoret is intentionally portable. The dashboard lives in GitHub and the local runtime is plain Python using the standard library.

On a Raspberry Pi running Raspberry Pi OS:

1. Give the Pi a DHCP reservation on the home network.
2. Download `install-pi.sh`.
3. Run it once with `sudo bash install-pi.sh`.
4. Enter the two Hue keys locally when prompted.
5. The installer creates a system service that starts at boot and restarts automatically.

Secrets are stored only in `/etc/eldoret.env` with restrictive permissions and are never committed to GitHub.

The same `manager.py` keeps checking GitHub for new connector code, so future Eldoret changes continue to deploy automatically.
