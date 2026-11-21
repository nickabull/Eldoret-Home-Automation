#!/usr/bin/env python3
"""One-time, interactive myenergi setup on Bulldog. No credentials sent to ChatGPT."""
import getpass
import json
import os
import pathlib
import re
import stat
import tempfile

def main():
    print("\nEldoret · myenergi Zappi secure setup")
    print("This runs locally on Bulldog. The API key is not echoed or stored in GitHub.")
    target=pathlib.Path.home()/".config"/"eldoret"/"myenergi.json"
    if target.exists():
        print("\nA Zappi key file already exists. Nothing will be overwritten automatically.")
        answer=input("Replace it? (type REPLACE): ").strip()
        if answer!="REPLACE":
            print("Keeping current configuration.")
            return
    serial=input("myenergi GATEWAY/HUB serial number (digits only): ").strip()
    if not re.fullmatch(r"[0-9]{5,20}",serial):
        raise SystemExit("Invalid gateway serial. No changes made.")
    key=getpass.getpass("myenergi API key (hidden): ").strip()
    if not 8<=len(key)<=256:
        raise SystemExit("API key length unexpected. No changes made.")
    directory=target.parent
    directory.mkdir(parents=True,exist_ok=True,mode=0o700)
    os.chmod(directory,0o700)
    descriptor,tmp=tempfile.mkstemp(prefix=".myenergi-",suffix=".new",dir=directory)
    try:
        os.fchmod(descriptor,stat.S_IRUSR|stat.S_IWUSR)
        with os.fdopen(descriptor,"w",encoding="utf-8") as out:
            json.dump({"gateway_serial":serial,"api_key":key},out)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp,target)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    print("\nSaved privately at ~/.config/eldoret/myenergi.json (mode 600).")
    print("Go to Eldoret Car Charging and press 'Refresh both statuses'.")
    print("No charger commands or schedules are changed.")

if __name__=="__main__":
    main()
