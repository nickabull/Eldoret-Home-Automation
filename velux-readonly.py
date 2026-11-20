#!/usr/bin/env python3
"""Read-only VELUX HAP status for Eldoret. Secrets never appear in JSON."""
import asyncio
import json
import os
import pathlib
from datetime import datetime, timezone
from argparse import Namespace
from aiohomekit.__main__ import get_controller

FILE = pathlib.Path.home() / ".config/eldoret-homekit/pairings.json"

async def main():
    if not FILE.exists():
        print(json.dumps({"connected": False, "error": "HomeKit pairing credentials are not installed on this host", "windows": [], "mode": "read-only"}))
        return
    async with get_controller(Namespace(file=str(FILE))) as controller:
        pairing = controller.aliases.get("velux")
        if not pairing:
            raise RuntimeError("VELUX alias unavailable; pairing credentials were not loaded")
        await pairing.async_populate_accessories()
        accessories = pairing.accessories
        if accessories is None:
            raise RuntimeError("No HAP accessories returned")
        result = {"connected": True, "source": "VELUX HomeKit local", "mode": "read-only",
                  "checked_at": datetime.now(timezone.utc).isoformat(), "windows": [], "climate": None}
        # The first verified installation has AID 2 climate, AID 3/4 windows.
        # Explicitly refuse unknown/missing values rather than defaulting to zero.
        for aid, characteristic_map in ((2, {"temperature": 10, "humidity": 13, "co2_ppm": 17}),
                                        (3, {"current_position": 10, "target_position": 11, "position_state": 12}),
                                        (4, {"current_position": 10, "target_position": 11, "position_state": 12})):
            values = {}
            for key, iid in characteristic_map.items():
                ch = accessories.aid(aid).characteristics.iid(iid)
                values[key] = ch.value
            if aid == 2:
                result["climate"] = values
            else:
                result["windows"].append({"aid": aid, **values})
        print(json.dumps(result))

if __name__ == "__main__":
    os.umask(0o077)
    try:
        asyncio.run(main())
    except Exception as exc:
        print(json.dumps({"connected": False, "error": type(exc).__name__ + ": " + str(exc),
                          "windows": [], "mode": "read-only", "checked_at": datetime.now(timezone.utc).isoformat()}))
