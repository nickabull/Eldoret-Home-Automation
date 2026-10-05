#!/usr/bin/env python3
import hashlib
import os
import signal
import subprocess
import sys
import time
import urllib.request

BASE="https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/"
ROOT=os.path.expanduser("~/eldoret-connector")
CONNECTOR=os.path.join(ROOT,"connector.py")
CHECK_SECONDS=30

def fetch():
    req=urllib.request.Request(BASE+"connector.py",headers={"User-Agent":"Eldoret-Updater/1.0"})
    with urllib.request.urlopen(req,timeout=15) as r:
        return r.read()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def write_if_changed(data):
    old=None
    try:
        with open(CONNECTOR,"rb") as f:
            old=f.read()
    except FileNotFoundError:
        pass
    if old is not None and sha(old)==sha(data):
        return False
    tmp=CONNECTOR+".new"
    with open(tmp,"wb") as f:
        f.write(data)
    os.replace(tmp,CONNECTOR)
    return True

def start_child():
    return subprocess.Popen([sys.executable,CONNECTOR],cwd=ROOT,env=os.environ.copy())

def stop_child(child):
    if not child or child.poll() is not None:
        return
    child.terminate()
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        child.kill()
        child.wait(timeout=5)

def main():
    os.makedirs(ROOT,exist_ok=True)
    try:
        write_if_changed(fetch())
    except Exception as e:
        print("Initial update check failed:",e,flush=True)
    child=start_child()
    print("Eldoret manager running; checking GitHub every 30 seconds.",flush=True)
    try:
        while True:
            time.sleep(CHECK_SECONDS)
            try:
                changed=write_if_changed(fetch())
                if changed:
                    print("Eldoret update found; restarting connector.",flush=True)
                    stop_child(child)
                    child=start_child()
                elif child.poll() is not None:
                    print("Connector stopped; restarting.",flush=True)
                    child=start_child()
            except Exception as e:
                print("Update check failed:",e,flush=True)
    except KeyboardInterrupt:
        pass
    finally:
        stop_child(child)

if __name__=="__main__":
    main()
