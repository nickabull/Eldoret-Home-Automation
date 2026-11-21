#!/usr/bin/env python3
"""Private, read-only PlayStation Network presence bridge for Eldoret."""
import getpass
import json
import os
import stat
import sys
from datetime import datetime, timezone
from urllib.parse import urlparse

CONFIG=os.path.expanduser("~/.config/eldoret/psn.json")

def configured():
    try:
        st=os.stat(CONFIG)
        return st.st_uid==os.getuid() and stat.S_IMODE(st.st_mode)==0o600
    except OSError:
        return False

def setup():
    directory=os.path.dirname(CONFIG)
    os.makedirs(directory,mode=0o700,exist_ok=True)
    os.chmod(directory,0o700)
    print("PlayStation Network setup (private Bulldog terminal only)")
    token=getpass.getpass("NPSSO token (hidden): ").strip()
    online_id=input("PSN online ID to monitor [Jesse_Dub_Dub]: ").strip() or "Jesse_Dub_Dub"
    if len(token)<20 or not online_id or len(online_id)>32:
        raise ValueError("Incomplete token or online ID")
    path=CONFIG+".new"
    fd=os.open(path,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"npsso":token,"online_id":online_id},f)
            f.flush();os.fsync(f.fileno())
        os.replace(path,CONFIG)
        os.chmod(CONFIG,0o600)
    finally:
        if os.path.exists(path): os.unlink(path)
    print("Saved private PSN token (0600). No token displayed.")

def safe_image(url):
    if not isinstance(url,str) or len(url)>2000: return None
    p=urlparse(url)
    if p.scheme!="https" or not p.hostname or p.username or p.password: return None
    h=p.hostname.lower()
    if h.endswith(".playstation.net") or h.endswith(".sony.com") or h.endswith(".sonyentertainmentnetwork.com"):
        return url
    return None

def fetch():
    result={"configured":configured(),"connected":False,"online_id":None,
            "online_status":None,"platform":None,"game":None,
            "game_title_id":None,"game_artwork":None,"game_status":None,
            "checked_at":datetime.now(timezone.utc).isoformat(),"source":"PSN presence"}
    if not result["configured"]:
        result["detail"]="Private PSN account token not configured."
        return result
    from psnawp_api import PSNAWP
    with open(CONFIG,encoding="utf-8") as f: conf=json.load(f)
    api=PSNAWP(conf["npsso"])
    user=api.user(online_id=conf["online_id"])
    raw=user.get_presence()
    presence=raw.get("basicPresence",raw)
    platform=presence.get("primaryPlatformInfo") or {}
    games=presence.get("gameTitleInfoList") or []
    game=next((x for x in games if isinstance(x,dict) and x.get("titleName")),None)
    result.update(connected=True,online_id=conf["online_id"],
                  online_status=platform.get("onlineStatus") or presence.get("availability"),
                  platform=platform.get("platform"),
                  game=game.get("titleName") if game else None,
                  game_title_id=game.get("npTitleId") if game else None,
                  game_artwork=safe_image(game.get("npTitleIconUrl")) if game else None,
                  game_status=game.get("gameStatus") if game else None,
                  detail="PSN presence received. Game visibility depends on PlayStation privacy settings.")
    return result

if __name__=="__main__":
    try:
        if len(sys.argv)!=2 or sys.argv[1] not in ("--setup","status"):
            raise ValueError("Unknown command")
        if sys.argv[1]=="--setup": setup()
        else: print(json.dumps(fetch(),separators=(",",":")))
    except Exception as exc:
        # Never print raw API exceptions: these may contain identifying information.
        print(json.dumps({"configured":configured(),"connected":False,
                          "error":type(exc).__name__,
                          "detail":"PSN authentication, privacy or network request failed."}))
        sys.exit(1)
