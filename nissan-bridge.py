#!/usr/bin/env python3
"""Local NissanConnect adapter for Eldoret. No secrets in GitHub, HTTP or logs."""
import getpass
import json
import os
import stat
import sys
from datetime import datetime, timezone

CONFIG=os.path.expanduser("~/.config/eldoret/nissan.json")
LIB=os.path.expanduser("~/nissan-test/nissanconnect/custom_components/nissan_connect")
sys.path.insert(0, LIB)

def configured():
    try:
        info=os.stat(CONFIG)
        return stat.S_IMODE(info.st_mode)==0o600 and info.st_uid==os.getuid()
    except OSError:
        return False

def read_config():
    if not configured():
        raise RuntimeError("Nissan private configuration missing or permissions incorrect")
    with open(CONFIG,encoding="utf-8") as f:
        c=json.load(f)
    if not isinstance(c,dict) or not c.get("email") or not c.get("password"):
        raise RuntimeError("Nissan configuration incomplete")
    return c

def setup():
    os.makedirs(os.path.dirname(CONFIG),mode=0o700,exist_ok=True)
    os.chmod(os.path.dirname(CONFIG),0o700)
    print("Private NissanConnect setup on Bulldog (never enter these in ChatGPT)")
    email=input("Nissan email: ").strip()
    password=getpass.getpass("Nissan password (hidden): ")
    if not email or not password: raise ValueError("Both fields required")
    tmp=CONFIG+".new"
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    try:
        with os.fdopen(fd,"w",encoding="utf-8") as f:
            json.dump({"email":email,"password":password},f)
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp,CONFIG); os.chmod(CONFIG,0o600)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    print("Nissan credentials saved privately (0600). No credentials printed.")

def timestamp(value):
    return value.isoformat() if hasattr(value,"isoformat") else None

def connect():
    from kamereon import NCISession
    c=read_config()
    s=NCISession(region="EU")
    s.login(c["email"],c["password"])
    cars=[v for v in s.fetch_vehicles() if (v.model_name or "").casefold()=="ariya"]
    if len(cars)!=1: raise RuntimeError("Expected exactly one Ariya")
    return cars[0]

def status():
    from kamereon import Feature
    out={"model":"Nissan Ariya","provider":"NissanConnect EU",
         "configured":configured(),"connected":False,"battery_percent":None,
         "range_km":None,"range_miles":None,"plugged_in":None,"charging":None,
         "cabin_temperature_c":None,"climate_active":None,"target_temperature_c":None,
         "climate_command_enabled":False,"location_available":False,
         "last_location_update":None,"last_vehicle_update":None,
         "checked_at":datetime.now(timezone.utc).isoformat()}
    if not out["configured"]:
        out["detail"]="Private Nissan credentials not configured on Bulldog."
        return out
    car=connect()
    out["connected"]=True
    faults=[]
    for label,fun in (("battery",car.fetch_battery_status),("climate",car.fetch_hvac_status),
                      ("location",car.fetch_location)):
        try: fun()
        except Exception: faults.append(label)
    out["battery_percent"]=car.battery_level if isinstance(car.battery_level,(float,int)) else None
    out["range_km"]=car.range_hvac_on if isinstance(car.range_hvac_on,(float,int)) else None
    if isinstance(out["range_km"],(float,int)):
        out["range_miles"]=round(out["range_km"]*0.621371,1)
    out["plugged_in"]=getattr(car.plugged_in,"name",None)=="PLUGGED"
    out["charging"]=getattr(car.charging,"name",None)=="CHARGING"
    out["cabin_temperature_c"]=car.internal_temperature
    out["climate_active"]=car.hvac_status
    out["target_temperature_c"]=car.next_target_temperature
    out["climate_command_enabled"]=Feature.CLIMATE_ON_OFF in car.features
    out["last_vehicle_update"]=timestamp(car.battery_status_last_updated)
    out["location_available"]=car.location is not None
    out["last_location_update"]=timestamp(car.location_last_updated)
    # GPS coordinates deliberately excluded from general status; separate explicit user request.
    out["detail"]="Read-only Nissan data retrieved." if not faults else "Some Nissan readings unavailable: "+", ".join(faults)
    return out

def command(action,temp):
    from kamereon import Feature, HVACAction
    if action not in ("start","stop") or type(temp) is not int or not 16<=temp<=26:
        raise ValueError("Invalid climate control request")
    car=connect()
    if Feature.CLIMATE_ON_OFF not in car.features:
        raise RuntimeError("Car does not advertise climate control")
    car.set_hvac_status(HVACAction.START if action=="start" else HVACAction.STOP,target_temperature=temp)
    return {"ok":True,"submitted":True,"action":action,"target_temperature_c":temp,
            "detail":"Nissan accepted the request; verify the physical vehicle state."}

if __name__=="__main__":
    try:
        if len(sys.argv)==2 and sys.argv[1]=="--setup":
            setup()
        elif len(sys.argv)==2 and sys.argv[1]=="status":
            print(json.dumps(status(),default=str))
        elif len(sys.argv)==2 and sys.argv[1]=="control":
            req=json.load(sys.stdin)
            if not isinstance(req,dict) or set(req)!={"action","temperature_c"}:
                raise ValueError("Unexpected control payload")
            print(json.dumps(command(req["action"],req["temperature_c"])))
        else:
            raise ValueError("Unknown invocation")
    except Exception as ex:
        # Keep identities, tokens, URLs, location and API bodies out of diagnostics.
        print(json.dumps({"ok":False,"error":type(ex).__name__,
                          "detail":"Nissan request could not be completed; check private setup and connection."}))
        sys.exit(1)
