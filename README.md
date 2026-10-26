# Eldoret Home Automation

Touch-first dashboard for the Eldoret Philips Hue installation.

## Design principles
- Touch targets sized for a dedicated 10–13 inch panel
- No hover-dependent controls
- Responsive on tablet, phone and desktop
- House and Utility Hue bridges represented separately
- Public repository contains **no Hue API keys or local bridge credentials**

This first version is a sanitised inventory/status dashboard. Direct Hue control will be added separately so credentials remain on the local network.


## Local connector

The Chromebook connector serves the dashboard at `http://localhost:8765` and keeps all Hue credentials on the local network.

No extra Python packages are required. The Sky Q integration now uses only Python's built-in networking libraries.

Run the connector with the existing Hue environment variables. Sky Q defaults to `10.0.0.18`; override it with `SKY_Q_HOST` if the box address changes.

The dashboard now includes a **Now Watching · Sky Q** panel. It talks directly to the Sky Q box over the local network, with no pip-installed dependency.

## UniFi access-point readings

The connector supports the classic API on a self-hosted UniFi Network Server (including Network 8.1). Use a separate local **View Only** account with Remote Access and device adoption disabled.

After the connector updates, run locally:

```sh
python3 ~/eldoret-connector/connector.py --configure-unifi
```

Enter the controller's HTTPS origin, including port 8443, the local username and site (usually `default`). Confirm trust in that controller's displayed certificate fingerprint and enter the password at the hidden prompt. Setup verifies device access before saving. Settings, password and certificate fingerprint remain in `~/eldoret-connector/unifi/config.json` (mode 600, private directory); do not upload this file. No extra packages are required. Rerun setup if the host or certificate changes, or when moving the controller to another machine.

The Network page reads `/api/unifi/status` for AP connection state, reported client count, CPU/memory, firmware and uptime. Only selected fields are returned; raw controller configuration, login cookies and credentials are never included. Polling is cached for 30 seconds (10 seconds after failure). Missing metrics remain unknown. If the controller sleeps or cannot be reached, the last successful AP statistics stay visible with their original last-seen timestamp and historical labels. They return to live readings when the controller responds. This history is held in connector memory; restarting the connector clears it. Existing device service checks remain separate.

