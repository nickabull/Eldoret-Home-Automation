#!/usr/bin/env python3
"""Manual supervised VELUX target-position write through the existing local HomeKit pairing.

Usage: velux-window-command.py <aid:3|4> <target:0|10|100>
Never reads or prints pairing credentials. No automatic control or retries.
"""
import asyncio
import json
import os
import pathlib
import sys
from argparse import Namespace
from aiohomekit.__main__ import get_controller

PAIRINGS = pathlib.Path.home() / ".config/eldoret-homekit/pairings.json"

async def run(aid, target):
    if not PAIRINGS.exists():
        return {"ok": False, "detail": "VELUX HomeKit pairing unavailable"}
    async with get_controller(Namespace(file=str(PAIRINGS))) as controller:
        pairing = controller.aliases.get("velux")
        if pairing is None:
            return {"ok": False, "detail": "VELUX HomeKit pairing alias unavailable"}
        accessories = await pairing.list_accessories_and_characteristics()
        entry = next((x for x in accessories if x.get("aid") == aid), None)
        if entry is None:
            return {"ok": False, "detail": "Window accessory not found"}
        # Verify that IID 11 is a writable Target Position characteristic on this
        # exact accessory, not just any property at IID 11.
        char = next((ch for service in entry.get("services", [])
                     for ch in service.get("characteristics", [])
                     if ch.get("iid") == 11), None)
        target_type = str(char.get("type", "")).upper() if char else ""
        if not char or "pw" not in (char.get("perms") or []) or not (target_type.startswith("0000007C") or target_type == "7C"):
            return {"ok": False, "detail": "Window target position is not verified writable"}
        if char.get("format") not in ("uint8", "int", "uint16", "uint32"):
            return {"ok": False, "detail": "Unexpected target characteristic type"}
        try:
            result = await pairing.put_characteristics([(aid, 11, target)])
        except Exception:
            return {"ok": False, "detail": "VELUX rejected the movement request"}
        failure = result.get((aid, 11))
        if failure and failure.get("status", 0) != 0:
            return {"ok": False, "detail": "VELUX rejected target position"}
        # A successful HomeKit write means requested, not physically completed.
        return {"ok": True, "aid": aid, "requested_position": target,
                "detail": "Target accepted. Check the physical window; rain safety remains managed by VELUX."}

def main():
    if len(sys.argv) != 3:
        raise ValueError("Arguments required")
    aid, target = int(sys.argv[1]), int(sys.argv[2])
    if aid not in (3, 4) or target not in (0, 10, 100):
        raise ValueError("Unsupported window or position")
    return asyncio.run(run(aid, target))

if __name__ == "__main__":
    os.umask(0o077)
    try:
        print(json.dumps(main()))
    except Exception:
        print(json.dumps({"ok": False, "detail": "VELUX command could not be completed"}))
