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

Install the Python dependency once:

```bash
python3 -m pip install -r requirements.txt
```

Then run the connector with the existing Hue environment variables. Sky Q defaults to `10.0.0.18`; override it with `SKY_Q_HOST` if the box address changes.

The dashboard now includes a **Now Watching · Sky Q** panel. It reads the current channel from the Sky Q box and, when live TV is playing, resolves the programme title and synopsis through `pyskyqremote`.
