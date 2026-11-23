#!/usr/bin/env python3
"""Install a SmartThings read-only token privately for Eldoret Bulldog.
Run locally on Bulldog. Never print or commit tokens.
"""
import getpass
import json
import os
import pathlib
import tempfile
import urllib.request
import urllib.error

DEST = pathlib.Path.home() / ".config/eldoret/smartthings.json"
def main():
    token = getpass.getpass("SmartThings read-only token (hidden): ").strip()
    if not token or any(ch.isspace() for ch in token):
        raise SystemExit("No valid token entered; existing settings untouched.")
    request = urllib.request.Request("https://api.smartthings.com/v1/devices",
        headers={"Authorization":"Bearer "+token,"Accept":"application/json",
                 "User-Agent":"Eldoret-Bulldog/1.0"})
    try:
        with urllib.request.urlopen(request,timeout=12) as response:
            data=json.load(response)
    except urllib.error.HTTPError as e:
        raise SystemExit("Validation failed: SmartThings HTTP "+str(e.code)+". Existing settings untouched.")
    except (OSError,ValueError) as e:
        raise SystemExit("Validation failed: "+type(e).__name__+". Existing settings untouched.")
    devices=data.get("items",[])
    if not isinstance(devices,list) or not any(
        "refrigerator" in str(d.get("label","")+" "+d.get("name","")).lower()
        for d in devices if isinstance(d,dict)):
        raise SystemExit("Refrigerator not in authorized device list. Existing settings untouched.")
    folder=DEST.parent
    folder.mkdir(parents=True,exist_ok=True,mode=0o700)
    folder.chmod(0o700)
    fd,tmp=tempfile.mkstemp(prefix=".smartthings-",dir=str(folder))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"token":token},f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,DEST)
        DEST.chmod(0o600)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print("SmartThings read-only token validated and saved privately (0600).")
    print("Refrigerator discovered. Token not printed.")
if __name__=="__main__":
    main()
