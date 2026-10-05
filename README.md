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
