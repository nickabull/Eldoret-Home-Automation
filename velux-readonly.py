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
        accessories = await pairing.list_accessories_and_characteristics()
        result = {"connected": True, "source": "VELUX HomeKit local", "mode": "read-only",
                  "checked_at": datetime.now(timezone.utc).isoformat(), "windows": [], "climate": None}
        by_aid = {a["aid"]: a for a in accessories}
        def read(aid, iid):
            for service in by_aid.get(aid, {}).get("services", []):
                for characteristic in service.get("characteristics", []):
                    if characteristic.get("iid") == iid:
                        return characteristic.get("value")
            return None
        if 2 in by_aid:
            result["climate"] = {"temperature": read(2, 10), "humidity": read(2, 13),
                                  "co2_ppm": read(2, 17)}
        for aid in (3, 4):
            if aid in by_aid:
                result["windows"].append({"aid": aid, "current_position": read(aid, 10),
                    "target_position": read(aid, 11), "position_state": read(aid, 12)})
        print(json.dumps(result))

if __name__ == "__main__":
    os.umask(0o077)
    try:
        asyncio.run(main())
    except Exception as exc:
        print(json.dumps({"connected": False, "error": type(exc).__name__ + ": " + str(exc),
                          "windows": [], "mode": "read-only", "checked_at": datetime.now(timezone.utc).isoformat()}))
