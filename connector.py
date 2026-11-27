import json
import math
import os
import socket
import ssl
import time
import threading
import hashlib
import base64
import secrets
import platform
import subprocess
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

BRIDGES = {
    "house": {"ip": "10.0.0.2", "key": os.environ.get("HUE_KEY")},
    "utility": {"ip": "10.0.0.4", "key": os.environ.get("UTILITY_HUE_KEY")},
}
GITHUB_BASE = "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/"
STATIC_CACHE = {}
STATIC_CACHE_TTL = 300
AGENT_TASK_URL = "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/agent-task.json"
AGENT_RELAY_URL = "https://ntfy.sh/eldoret-relay-7e6b9d2c4f8a31b5a0c9e247d6f31c8e"
REMOTE_STATE_URL = "https://ntfy.sh/eldoret-live-4f1c7a92d8e63b5a0f4d2c9b71e8a605"
AGENT_RESULTS_FILE = os.path.join(os.path.expanduser("~/eldoret-connector"), "agent-results.json")
AGENT_STATE_FILE = os.path.join(os.path.expanduser("~/eldoret-connector"), "agent-state.json")
DEVICE_REGISTRY_FILE = os.path.join(os.path.expanduser("~/eldoret-connector"), "device-registry.json")
REMOTE_TUNNEL_FILE = os.path.join(os.path.expanduser("~/eldoret-connector"), "remote-tunnel.json")
REMOTE_TUNNEL_PROCESS = None
REMOTE_SESSIONS = set()
REMOTE_LOGIN_SALT = "61PKtUm5Xl8+7jP1w7GC8Q=="
REMOTE_LOGIN_HASH = "ApNkYRNpbpuUh7efM3oHprHfLOi1MRO79RGQh4YUehE="
AGENT_RESULT = {"status":"waiting","task":None,"task_id":None,"result":None,"error":None,"finished_at":None}
SKY_Q_HOST = os.environ.get("SKY_Q_HOST", "10.0.0.18")

# Studio telemetry: argument-free OSC reads only; shared bounded cache.
STUDIO_LOCK = threading.Lock()
STUDIO_CACHE = {"data":None,"next":0}
def studio_status():
    import struct
    if not STUDIO_LOCK.acquire(blocking=False):
        return STUDIO_CACHE["data"] or {"available":False,"sampling":True,"channels":[]}
    try:
        if time.monotonic()<STUDIO_CACHE["next"]:
            return STUDIO_CACHE["data"] or {"available":False,"sampling":True,"channels":[]}
        STUDIO_CACHE["next"]=time.monotonic()+120
        host=_registry_ip("x32","10.0.0.42")
        previous=STUDIO_CACHE["data"]
        result={"available":False,"channels":[],"buses":[],"dcas":[],"main":{},"checked_at":datetime.now(timezone.utc).isoformat(),"xtouch":{"ip":_registry_ip("xtouch","10.0.0.26"),"protocol":"unverified"}}
        def osc_string(value):
            b=value.encode()+b"\0"
            return b+b"\0"*((-len(b))%4)
        def get_string(data,offset):
            end=data.index(b"\0",offset)
            return data[offset:end].decode(errors="replace"),(end+4)&~3
        with socket.socket(socket.AF_INET,socket.SOCK_DGRAM) as sock:
            sock.connect((host,10023))
            sock.settimeout(.35)
            deadline=time.monotonic()+8
            failures=0
            def query(path):
                nonlocal failures
                if failures>=3 or time.monotonic()>deadline:return None
                # No arguments or write-capable OSC commands.
                sock.send(osc_string(path)+osc_string(","))
                try:
                    data=sock.recv(4096)
                    address,pos=get_string(data,0)
                    if address!=path:return None
                    tags,pos=get_string(data,pos)
                    values=[]
                    for tag in tags[1:]:
                        if tag=="s":
                            value,pos=get_string(data,pos)
                        elif tag in ("i","f"):
                            value=struct.unpack_from(">i" if tag=="i" else ">f",data,pos)[0]
                            pos+=4
                        else:return None
                        values.append(value)
                    failures=0
                    return values[0] if len(values)==1 else values
                except (OSError,ValueError,struct.error):
                    failures+=1
                    return None
                finally:
                    time.sleep(.025)
            identity=query("/xinfo")
            if isinstance(identity,list) and len(identity)>=4:
                result.update(available=True,model=identity[2],firmware=identity[3],name=identity[1],ip=host)
                for kind,count,collection in (("ch",32,"channels"),("bus",16,"buses"),("dca",8,"dcas")):
                    for i in range(1,count+1):
                        base="/"+kind+"/"+(str(i) if kind=="dca" else f"{i:02d}")
                        item={"number":i,"name":query(base+"/config/name"),"fader":query(base+"/mix/fader"),"on":query(base+"/mix/on")}
                        result[collection].append(item)
                result["main"]={"fader":query("/main/st/mix/fader"),"on":query("/main/st/mix/on")}
        if not result["available"] and previous and previous.get("available"):
            result={**previous,"available":False,"stale":True,"attempted_at":result["checked_at"]}
        try:
            p=subprocess.run(["ping","-c","1","-W","1",result["xtouch"]["ip"]],capture_output=True,timeout=2)
            result["xtouch"]["reachable"]=p.returncode==0
        except (OSError,subprocess.TimeoutExpired):
            result["xtouch"]["reachable"]=None
        STUDIO_CACHE["data"]=result
        return result
    finally:
        STUDIO_LOCK.release()

def sky_q_host():
    return _registry_ip("sky_q", SKY_Q_HOST)
SKY_Q_JSON_PORT = int(os.environ.get("SKY_Q_JSON_PORT", "9006"))
SKY_Q_REMOTE_PORT = int(os.environ.get("SKY_Q_REMOTE_PORT", "49160"))
# Temporary diagnostic: prevent ALL passive Sky Q GET requests from reaching the box.
# Manual Sky Q POST remote/channel commands remain enabled.
SKY_PASSIVE_ISOLATION = True
SKY_PASSIVE_BLOCKED = {}
SKY_PASSIVE_LOCK = threading.Lock()
# Shared original media readback: one sample per five minutes across all clients.
# Keep legacy discovery, guides and other passive routes isolated.
SKY_GENTLE_LOCK = threading.Lock()
SKY_GENTLE_CACHE = {"available":False,"live":False,"gentle":True,"detail":"Awaiting first playback sample"}
SKY_GENTLE_NEXT = 0
def sky_gentle_now():
    global SKY_GENTLE_NEXT, SKY_GENTLE_CACHE
    if not SKY_GENTLE_LOCK.acquire(blocking=False):
        return dict(SKY_GENTLE_CACHE)
    try:
        now=time.monotonic()
        if now < SKY_GENTLE_NEXT:
            return dict(SKY_GENTLE_CACHE)
        SKY_GENTLE_NEXT=now+300
        try:
            result=sky_now_playing_v2()
            if not result.get("available") and result.get("uri") != "":
                raise RuntimeError("Sky media readback unavailable")
            SKY_GENTLE_CACHE={**result,"gentle":True,"checked_at":time.time(),"stale":False}
        except Exception:
            SKY_GENTLE_NEXT=time.monotonic()+1800
            SKY_GENTLE_CACHE={**SKY_GENTLE_CACHE,"available":False,"live":False,"stale":True,"detail":"Readback unavailable; retry paused for 30 minutes"}
        return dict(SKY_GENTLE_CACHE)
    finally:
        SKY_GENTLE_LOCK.release()

NETWORK_PROBES = [
 {"ip":"10.0.0.1","name":"Main Router","ports":[80,443]},
 {"ip":"10.0.0.2","name":"House Hue Bridge","ports":[80]},
 {"ip":"10.0.0.3","name":"Epson printer","ports":[80,443,9100,631]},
 {"ip":"10.0.0.4","name":"Utility Hue Bridge","ports":[80]},
 {"ip":"10.0.0.5","name":"Old Raspberry Pi","ports":[22,80,443]},
 {"ip":"10.0.0.6","name":"UniFi Office/Kitchen","ports":[22,443,8080]},
 {"ip":"10.0.0.7","name":"UniFi Utility","ports":[22,443,8080]},
 {"ip":"10.0.0.8","name":"UniFi Garden","ports":[22,443,8080]},
 {"ip":"10.0.0.9","name":"UniFi Landing","ports":[22,443,8080]},
 {"ip":"10.0.0.18","name":"Sky Q","ports":[49160,49153]},
 {"ip":"10.0.0.22","name":"VELUX Gateway","ports":[80,443]},
 {"ip":"10.0.0.27","name":"Eldoret Chromebook","ports":[8765]},
 {"ip":"10.0.0.51","name":"LG webOS TV","ports":[3000,3001,80]},
 {"ip":"10.0.0.43","name":"LG device","ports":[3000,3001,80]},
 {"ip":"10.0.0.47","name":"LG device","ports":[3000,3001,80]},
 {"ip":"10.0.0.48","name":"PlayStation","ports":[80,443,9295,9304]}
]
GUIDE_GROUPS = {
    "movies": ["Sky Cinema Premiere","Sky Cinema Select","Sky Cinema Hits","Sky Cinema Greats","Sky Cinema Animation","Sky Cinema Family","Sky Cinema Action","Sky Cinema Comedy","Sky Cinema Thriller","Sky Cinema Drama","Sky Cinema Sci-Fi Horror","Film4","Talking Pictures"],
    "news": ["Sky News","BBC News","CNN","GB News","Bloomberg","BBC Parliament","CNBC"],
    "documentaries": ["Sky Documentaries","Sky Nature","Sky History","National Geographic","Discovery","Animal Planet","Crime + Investigation","PBS America","Yesterday"],
    "hd": ["BBC One HD","BBC Two HD","ITV1 HD","Channel 4 HD","Channel 5 HD","Sky Atlantic HD","Sky Max HD","Sky Witness HD","Sky Arts HD","Gold HD","Discovery HD","National Geographic HD","Sky News HD","TNT Sports 1 HD"],
    "plus1": ["Channel 4 +1","Channel 5 +1","ITV1 +1","Sky Witness +1","Comedy Central +1","Gold +1","Dave ja vu"],
    "music": ["MTV Music","MTV Hits","MTV 80s","MTV 90s","Clubland TV","NOW 80s","NOW 90s","Trace Hits","4Music"]
}
GUIDE_CHANNEL_NUMBERS = {"movies":["301","302","303","304","305","306","307","308","309","310","311","312","313","315"],"news":["501","502","503","504","505","506","507","508","509","510","511","512","513","515"],"documentaries":["114","121","123","124","125","129","139","162","163","165","166"],"hd":["101","102","103","104","105","106","107","108","109","110","111","112","113","114"],"plus1":["203","204","205","209","210","211","212","218","219","220","225","228","232","233"],"music":["354","355","356","357","358"]}
SPORT_CHANNEL_NUMBERS = ["401","402","403","404","405","406","407","408","409","410","411","412","413","414","419"]
SKY_KEY_MAP = {
    "power":0,"select":1,"backup":2,"channelup":6,"channeldown":7,
    "help":9,"search":10,"home":11,"up":16,"down":17,"left":18,"right":19,"red":32,
    "0":48,"1":49,"2":50,"3":51,"4":52,"5":53,"6":54,"7":55,"8":56,"9":57,
    "play":64,"pause":65,"stop":66,"record":67,"fastforward":69,"rewind":71
}

def _registry_load():
    try:
        with open(DEVICE_REGISTRY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def _registry_save(registry):
    try:
        os.makedirs(os.path.dirname(DEVICE_REGISTRY_FILE), exist_ok=True)
        tmp=DEVICE_REGISTRY_FILE+".new"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(registry, f, ensure_ascii=False, indent=2)
        os.replace(tmp, DEVICE_REGISTRY_FILE)
    except Exception:
        pass

def _registry_set(device_id, ip, evidence):
    registry=_registry_load()
    registry[device_id]={"ip":ip,"evidence":evidence,"updated_at":datetime.now(timezone.utc).isoformat()}
    _registry_save(registry)
    return ip

def _registry_ip(device_id, fallback):
    entry=_registry_load().get(device_id) or {}
    return entry.get("ip") or fallback

def _scan_port(port, timeout=0.07):
    found=[]
    def one(last):
        ip="10.0.0."+str(last)
        return ip if _tcp_open(ip, port, timeout=timeout) else None
    with ThreadPoolExecutor(max_workers=48) as pool:
        for ip in pool.map(one, range(1,255)):
            if ip:
                found.append(ip)
    return found

def discover_known_devices():
    found={}
    # Sky Q has distinctive local service ports.
    sky_candidates=_scan_port(SKY_Q_REMOTE_PORT,0.06)
    if not sky_candidates:
        sky_candidates=_scan_port(49153,0.06)
    if sky_candidates:
        found["sky_q"]=_registry_set("sky_q",sky_candidates[0],"Sky Q local control service")

    # Epson ET-3850: printing services plus Epson web identity when available.
    printer_candidates=list(dict.fromkeys(_scan_port(631,0.06)+_scan_port(9100,0.06)))
    ctx=ssl._create_unverified_context()
    for ip in printer_candidates:
        is_epson=False
        for scheme in ("http","https"):
            try:
                req=urllib.request.Request(scheme+"://"+ip+"/",headers={"User-Agent":"Eldoret/1.0"})
                with urllib.request.urlopen(req,timeout=0.8,context=ctx if scheme=="https" else None) as r:
                    body=r.read(25000).decode("utf-8",errors="replace").lower()
                if "epson" in body or "et-3850" in body:
                    is_epson=True; break
            except Exception:
                pass
        if is_epson or len(printer_candidates)==1:
            found["epson_et3850"]=_registry_set("epson_et3850",ip,"IPP/raw-print + Epson identity")
            break

    # LG webOS televisions.
    lg_candidates=list(dict.fromkeys(_scan_port(3000,0.05)+_scan_port(3001,0.05)))
    for idx,ip in enumerate(sorted(lg_candidates)):
        _registry_set("lg_tv_"+str(idx+1),ip,"LG webOS service")
    found["lg_tvs"]=sorted(lg_candidates)

    # VELUX ACTIVE / App Control gateway.
    velux_candidates=_scan_port(25050,0.06)
    if velux_candidates:
        found["velux_gateway"]=_registry_set("velux_gateway",velux_candidates[0],"VELUX local pairing/service port 25050")

    # PlayStation discovery protocol: broadcast and collect replies.
    ps_ip=None
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        sock.settimeout(0.35)
        payload=b"SRCH * HTTP/1.1\nD-Protocol-Version:00030010\n"
        sock.sendto(payload,("10.0.0.255",9302))
        end=time.time()+1.2
        while time.time()<end:
            try:
                data,addr=sock.recvfrom(4096)
                text=data.decode("utf-8",errors="ignore").lower()
                if "host-type" in text or "ps5" in text or "ps4" in text:
                    ps_ip=addr[0]; break
            except socket.timeout:
                continue
    except Exception:
        pass
    finally:
        sock.close()
    if ps_ip:
        found["playstation"]=_registry_set("playstation",ps_ip,"PlayStation UDP discovery")

    return {"found":found,"registry":_registry_load(),"checked_at":datetime.now(timezone.utc).isoformat()}

def device_registry_loop():
    while True:
        try:
            discover_known_devices()
        except Exception:
            pass
        time.sleep(600)

def _tcp_open(ip, port, timeout=0.25):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def lg_pair_page():
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pair LG TV</title>
<style>body{font-family:system-ui;background:#09111d;color:#eef5ff;padding:32px}button{font-size:20px;padding:16px 24px;border:0;border-radius:14px}pre{white-space:pre-wrap;background:#111d2c;padding:18px;border-radius:14px}</style></head>
<body><h1>Pair Eldoret with LG TV</h1><p>TV: 10.0.0.51. Press Pair, then accept the prompt on the television.</p><button id="go">Pair TV</button><pre id="out">Ready.</pre>
<script>
const out=document.querySelector("#out");
document.querySelector("#go").onclick=()=>{
 const ws=new WebSocket("ws://10.0.0.51:3000/");
 ws.onopen=()=>{out.textContent="Connected. Sending pairing request…";
  ws.send(JSON.stringify({type:"register",id:"eldoret-register",payload:{forcePairing:false,pairingType:"PROMPT",manifest:{manifestVersion:1,permissions:["CONTROL_AUDIO","CONTROL_INPUT_TV","CONTROL_POWER","READ_APP_STATUS","READ_CURRENT_CHANNEL","READ_INPUT_DEVICE_LIST","READ_RUNNING_APPS","READ_POWER_STATE","READ_INSTALLED_APPS"]}}}));
 };
 ws.onmessage=(e)=>{let m;try{m=JSON.parse(e.data)}catch(_){m={raw:e.data}}
  if(m.type==="registered"&&m.payload&&m.payload["client-key"]){
   out.textContent="PAIRED OK.\n\nClient key (keep private):\n"+m.payload["client-key"]+"\n\nNext: save this key locally on the Chromebook; do not send it in chat.";
   ws.close();
  }else out.textContent="TV reply:\n"+JSON.stringify(m,null,2);
 };
 ws.onerror=()=>out.textContent="WebSocket connection failed. Leave the TV on and try again.";
};
</script></body></html>"""

def velux_status(ip=None):
    ip=ip or _registry_ip("velux_gateway","10.0.0.22")
    # Read-only reachability check for the VELUX gateway. KLF 200 local API uses TLS 51200.
    ports=[p for p in (80,443,51200) if _tcp_open(ip,p,timeout=0.6)]
    return {
        "ip":ip,
        "online":bool(ports),
        "ports":ports,
        "klf200_api":51200 in ports,
        "http":80 in ports,
        "https":443 in ports,
        "detail":("VELUX KLF 200 local API detected on TLS port 51200." if 51200 in ports
                  else ("VELUX gateway reachable; KLF 200 API port did not answer." if ports else "VELUX gateway did not answer."))
    }


def lg_discovery_status():
    """Read-only LG webOS LAN presence inventory; never pairs, wakes or controls TVs."""
    found = sorted(set(_scan_port(3000, 0.06) + _scan_port(3001, 0.06)),
                   key=lambda ip: tuple(int(v) for v in ip.split(".")))
    # A reachable webOS service is a candidate, not proof of which room/TV it is.
    targets = []
    for ip in found:
        plain = _tcp_open(ip, 3000, timeout=0.35)
        tls = _tcp_open(ip, 3001, timeout=0.35)
        targets.append({"ip":ip,"webos_plain":plain,"webos_tls":tls,
                        "identity":"unverified","room":"unassigned"})
    return {"source":"LAN webOS port discovery","checked_at":datetime.now(timezone.utc).isoformat(),
            "candidate_count":len(targets),"candidates":targets,
            "note":"Only powered/reachable TVs may appear. No room identity or pairing inferred."}



# Lounge webOS pilot: one fixed IP, explicit user-triggered control, private key only on Bulldog.
LG_LOUNGE_IP = "10.0.0.52"
LG_LOUNGE_KEY_FILE = os.path.expanduser("~/eldoret-connector/lg/lounge.json")
LG_LOUNGE_LOCK = threading.Lock()
LG_LOUNGE_JOB = {"state":"idle","detail":"Ready to request pairing.","at":None}
LG_LOUNGE_BUSY = False

class _LGWebSocket:
    """Small RFC6455 client over local webOS TLS; no third-party packages."""
    def __init__(self, ip):
        import struct
        self.struct = struct
        self.ip = ip
        self.sock = None
        self.fingerprint = None

    def connect(self):
        raw = socket.create_connection((self.ip,3001),timeout=5)
        try:
            # LG TVs often use self-signed certificates. Encrypted but not public-CA authenticated.
            self.sock = ssl._create_unverified_context().wrap_socket(raw,server_hostname=self.ip)
            self.sock.settimeout(6)
            self.fingerprint = hashlib.sha256(self.sock.getpeercert(binary_form=True)).hexdigest()
            nonce=base64.b64encode(secrets.token_bytes(16)).decode()
            request=("GET / HTTP/1.1\r\nHost: "+self.ip+":3001\r\n"
                     "Upgrade: websocket\r\nConnection: Upgrade\r\n"
                     "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Key: "+nonce+"\r\n\r\n")
            self.sock.sendall(request.encode("ascii"))
            header=bytearray()
            while not header.endswith(b"\r\n\r\n"):
                if len(header)>8192: raise RuntimeError("Unexpected large webOS handshake")
                char=self.sock.recv(1)
                if not char: raise RuntimeError("TV closed during TLS WebSocket handshake")
                header.extend(char)
            header_text=header.decode("iso-8859-1")
            if not header_text.startswith("HTTP/1.1 101 ") and not header_text.startswith("HTTP/1.0 101 "):
                raise RuntimeError("webOS rejected WebSocket upgrade")
            expected=base64.b64encode(hashlib.sha1((nonce+"258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
            if ("sec-websocket-accept: "+expected).lower() not in header_text.lower():
                raise RuntimeError("TV returned incorrect WebSocket acceptance")
        except Exception:
            self.close()
            raise

    def _exact(self, n):
        data=bytearray()
        while len(data)<n:
            part=self.sock.recv(n-len(data))
            if not part: raise RuntimeError("TV closed the connection")
            data.extend(part)
        return bytes(data)

    def send(self, payload, opcode=1):
        frame=payload if isinstance(payload,bytes) else payload.encode("utf-8")
        if len(frame)>65536: raise RuntimeError("Oversized command")
        key=secrets.token_bytes(4)
        length=len(frame)
        hdr=bytes([0x80|opcode,0x80|min(length,126)])
        if length>=126: hdr=bytes([0x80|opcode,0x80|126])+self.struct.pack("!H",length)
        masked=bytes(b^key[i%4] for i,b in enumerate(frame))
        self.sock.sendall(hdr+key+masked)

    def recv_json(self):
        import struct
        while True:
            a,b=self._exact(2)
            opcode=a&0x0f
            if not (a&0x80): raise RuntimeError("Fragmented webOS message unsupported")
            length=b&0x7f
            if length==126: length=struct.unpack("!H",self._exact(2))[0]
            if length==127: length=struct.unpack("!Q",self._exact(8))[0]
            if length>65536: raise RuntimeError("Oversized TV message")
            mask=self._exact(4) if b&0x80 else None
            data=self._exact(length)
            if mask: data=bytes(v^mask[i%4] for i,v in enumerate(data))
            if opcode==8: raise RuntimeError("TV closed the webOS session")
            if opcode==9: self.send(data,opcode=10); continue
            if opcode!=1: continue
            return json.loads(data.decode("utf-8"))

    def close(self):
        if self.sock:
            try: self.sock.close()
            except Exception: pass
        self.sock=None

def _lg_saved():
    import stat
    try:
        st=os.stat(LG_LOUNGE_KEY_FILE)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077:
            raise RuntimeError("Private TV pairing file permissions are unsafe")
        with open(LG_LOUNGE_KEY_FILE,encoding="utf-8") as f: return json.load(f)
    except FileNotFoundError:
        return None

def _lg_write(data):
    folder=os.path.dirname(LG_LOUNGE_KEY_FILE)
    os.makedirs(folder,mode=0o700,exist_ok=True)
    os.chmod(folder,0o700)
    import tempfile
    fd,tmp=tempfile.mkstemp(prefix=".lgtv-",dir=folder)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f: json.dump(data,f)
        os.replace(tmp,LG_LOUNGE_KEY_FILE)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def _lg_register_message(key=None):
    manifest={"manifestVersion":1,"appVersion":"1.0","signed":{"created":"20261120",
              "appId":"com.eldoret.remote","vendorId":"com.eldoret","localizedAppNames":{"":"Eldoret"},
              "localizedVendorNames":{"":"Eldoret"},"permissions":LG_LIVE_PERMISSIONS},
              "permissions":LG_LIVE_PERMISSIONS}
    payload={"forcePairing":False,"pairingType":"PROMPT","manifest":manifest}
    if key: payload["client-key"]=key
    return {"type":"register","id":"eldoret-register","payload":payload}

def _lg_set(state,detail):
    with LG_LOUNGE_LOCK:
        LG_LOUNGE_JOB.update(state=state,detail=detail,at=datetime.now(timezone.utc).isoformat())

def lg_bulldog_status():
    with LG_LOUNGE_LOCK: result=dict(LG_LOUNGE_JOB)
    try: result["paired"]=bool((_lg_saved() or {}).get("client_key"))
    except RuntimeError: result["paired"]=False;result["detail"]="Pairing storage permissions need checking."
    result["ip"]=LG_LOUNGE_IP
    return result

def _lg_pair_task():
    global LG_LOUNGE_BUSY
    ws=_LGWebSocket(LG_LOUNGE_IP)
    try:
        _lg_set("connecting","Connecting via encrypted webOS port 3001...")
        saved=_lg_saved()
        ws.connect()
        if saved and saved.get("fingerprint") != ws.fingerprint:
            raise RuntimeError("LG certificate changed. Pairing stopped for safety.")
        _lg_set("waiting","Encrypted TV connection established. Watch the lounge television for a pairing prompt.")
        ws.send(json.dumps(_lg_register_message((saved or {}).get("client_key"))))
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            ws.sock.settimeout(min(6,max(1,deadline-time.monotonic())))
            try: message=ws.recv_json()
            except socket.timeout: continue
            if message.get("type")=="registered":
                payload=message.get("payload") or {}
                key=payload.get("client-key") or (saved or {}).get("client_key")
                if not isinstance(key,str) or len(key)<10:
                    raise RuntimeError("TV replied but did not grant a pairing key")
                _lg_write({"ip":LG_LOUNGE_IP,"client_key":key,"fingerprint":ws.fingerprint,
                           "paired_at":datetime.now(timezone.utc).isoformat()})
                _lg_set("paired","Success! Lounge TV paired with Bulldog. Ready to open Tivvy TV.")
                return
            if message.get("type")=="error":
                raise RuntimeError("LG refused the registration request; check TV permissions.")
        raise RuntimeError("Timed out waiting for approval on the TV (65 seconds).")
    except Exception as exc:
        _lg_set("error",str(exc)[:180])
    finally:
        ws.close()
        with LG_LOUNGE_LOCK: LG_LOUNGE_BUSY=False

def lg_bulldog_pair_start():
    global LG_LOUNGE_BUSY
    with LG_LOUNGE_LOCK:
        if LG_LOUNGE_BUSY: return False
        LG_LOUNGE_BUSY=True
    threading.Thread(target=_lg_pair_task,daemon=True).start()
    return True

def lg_bulldog_launch():
    saved=_lg_saved()
    if not saved or not saved.get("client_key"):
        raise RuntimeError("Pair the lounge LG before launching its browser")
    ws=_LGWebSocket(LG_LOUNGE_IP)
    try:
        ws.connect()
        if saved.get("fingerprint")!=ws.fingerprint:
            raise RuntimeError("LG certificate differs from paired television. Stopped.")
        ws.send(json.dumps(_lg_register_message(saved["client_key"])))
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            ws.sock.settimeout(3)
            try:msg=ws.recv_json()
            except socket.timeout:continue
            if msg.get("type")=="error": raise RuntimeError("LG rejected stored pairing key")
            if msg.get("type")=="registered":break
        else:raise RuntimeError("LG did not register the existing pairing")
        ws.send(json.dumps({"type":"request","id":"eldoret-browser",
                           "uri":"ssap://system.launcher/launch",
                           "payload":{"id":"com.webos.app.browser",
                                      "params":{"target":"https://is.gd/TivvyTV26"}}}))
        ws.sock.settimeout(6)
        try:
            while True:
                msg=ws.recv_json()
                if msg.get("id")=="eldoret-browser":
                    if msg.get("type")=="error":raise RuntimeError("LG rejected browser launch")
                    return {"ok":True,"detail":"LG accepted browser launch. Check TV for the Tivvy page."}
        except socket.timeout:
            return {"ok":True,"detail":"Browser launch sent; TV did not confirm within six seconds."}
    finally:
        ws.close()




# Independent kitchen LG trial. Credentials stay on Bulldog, never in GitHub or browser.
LG_KITCHEN_IP="10.0.0.51"
LG_KITCHEN_KEY_FILE=os.path.expanduser("~/eldoret-connector/lg/kitchen.json")
LG_KITCHEN_LOCK=threading.Lock()
LG_KITCHEN_JOB={"state":"idle","detail":"No live connection tested yet.","at":None}
LG_KITCHEN_BUSY=False

def _lg_kitchen_saved():
    import stat
    try:
        st=os.stat(LG_KITCHEN_KEY_FILE)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077:
            raise RuntimeError("Kitchen TV pairing permissions unsafe")
        with open(LG_KITCHEN_KEY_FILE,encoding="utf-8") as f:record=json.load(f)
        # 20 Nov 2026: same physical kitchen LG moved from DHCP .33 to reserved .51.
        # This is an in-memory compatibility mapping, not a credential rewrite.
        if record.get("ip")=="10.0.0.33" and record.get("client_key") and record.get("fingerprint"):
            record["ip"]=LG_KITCHEN_IP
        return record
    except FileNotFoundError:
        return None

def _lg_kitchen_write(data):
    import tempfile
    folder=os.path.dirname(LG_KITCHEN_KEY_FILE)
    os.makedirs(folder,mode=0o700,exist_ok=True)
    os.chmod(folder,0o700)
    fd,tmp=tempfile.mkstemp(prefix=".lg-kitchen-",dir=folder)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(data,f)
        os.replace(tmp,LG_KITCHEN_KEY_FILE)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def _lg_kitchen_set(state,detail):
    with LG_KITCHEN_LOCK:
        LG_KITCHEN_JOB.update(state=state,detail=detail,at=datetime.now(timezone.utc).isoformat())

def lg_kitchen_status():
    with LG_KITCHEN_LOCK:result=dict(LG_KITCHEN_JOB)
    try:result["paired"]=bool((_lg_kitchen_saved() or {}).get("client_key"))
    except RuntimeError:
        result["paired"]=False
        result["detail"]="Kitchen TV credential storage permissions need checking."
    result["ip"]=LG_KITCHEN_IP
    return result

def lg_kitchen_reachability():
    """Explicit read-only live test; saved pairing alone does not prove TV is reachable."""
    checked=datetime.now(timezone.utc).isoformat()
    saved=_lg_kitchen_saved()
    if not saved or not saved.get("client_key") or saved.get("ip")!=LG_KITCHEN_IP:
        return {"paired":False,"reachable":False,"checked_at":checked,
                "detail":"Kitchen LG is not paired; pair it while powered on."}
    ws=_LGWebSocket(LG_KITCHEN_IP)
    try:
        ws.connect()
        if ws.fingerprint!=saved.get("fingerprint"):
            return {"paired":True,"reachable":False,"checked_at":checked,
                    "detail":"Kitchen LG identity did not match saved pairing."}
        ws.send(json.dumps(_lg_register_message(saved["client_key"])))
        deadline=time.monotonic()+8
        while time.monotonic()<deadline:
            ws.sock.settimeout(min(2,max(.2,deadline-time.monotonic())))
            try:msg=ws.recv_json()
            except socket.timeout:continue
            if msg.get("type")=="registered":
                _,ok=_lg_ssap_request(ws,"eldoret-kitchen-refresh",
                          "ssap://com.webos.applicationManager/getForegroundAppInfo")
                return {"paired":True,"reachable":bool(ok),"checked_at":checked,
                        "detail":"Kitchen TV responded to an authenticated live check." if ok else "Kitchen TV connected but did not answer live status."}
            if msg.get("type")=="error":
                return {"paired":True,"reachable":False,"checked_at":checked,
                        "detail":"Kitchen TV rejected stored pairing credentials."}
        return {"paired":True,"reachable":False,"checked_at":checked,
                "detail":"Kitchen TV did not confirm the connection before timeout."}
    except (OSError,RuntimeError,ValueError) as exc:
        # Do not leak details from credentials or underlying socket addresses.
        import errno
        if isinstance(exc,OSError) and exc.errno in (errno.EHOSTUNREACH,errno.ENETUNREACH):
            message="Kitchen TV is unreachable on the network (possibly in standby)."
        elif isinstance(exc,(TimeoutError,socket.timeout)):
            message="Kitchen TV did not respond before timeout."
        else:
            message="Kitchen TV connection failed; check it is switched on and on the home network."
        return {"paired":True,"reachable":False,"checked_at":checked,"detail":message}
    finally:ws.close()

def _lg_kitchen_pair_task():
    global LG_KITCHEN_BUSY
    ws=_LGWebSocket(LG_KITCHEN_IP)
    try:
        _lg_kitchen_set("connecting","Connecting securely to kitchen LG 10.0.0.51...")
        saved=_lg_kitchen_saved()
        ws.connect()
        if saved and saved.get("fingerprint")!=ws.fingerprint:
            raise RuntimeError("Kitchen LG identity changed. Pairing stopped.")
        _lg_kitchen_set("waiting","Connection established. Accept the Eldoret pairing request on the KITCHEN TV.")
        ws.send(json.dumps(_lg_register_message((saved or {}).get("client_key"))))
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            ws.sock.settimeout(min(6,max(1,deadline-time.monotonic())))
            try:message=ws.recv_json()
            except socket.timeout:continue
            if message.get("type")=="registered":
                payload=message.get("payload") or {}
                key=payload.get("client-key") or (saved or {}).get("client_key")
                if not isinstance(key,str) or len(key)<10:
                    raise RuntimeError("Kitchen LG did not grant a pairing key")
                _lg_kitchen_write({"ip":LG_KITCHEN_IP,"client_key":key,"fingerprint":ws.fingerprint,
                                  "paired_at":datetime.now(timezone.utc).isoformat()})
                _lg_kitchen_set("paired","Kitchen TV paired successfully. Ready to open Tivvy TV.")
                return
            if message.get("type")=="error":
                raise RuntimeError("Kitchen LG rejected the pairing request.")
        raise RuntimeError("Timed out waiting for kitchen TV pairing approval (65 seconds).")
    except Exception as exc:
        _lg_kitchen_set("error",str(exc)[:180])
    finally:
        ws.close()
        with LG_KITCHEN_LOCK:LG_KITCHEN_BUSY=False

def lg_kitchen_pair_start():
    global LG_KITCHEN_BUSY
    with LG_KITCHEN_LOCK:
        if LG_KITCHEN_BUSY:return False
        LG_KITCHEN_BUSY=True
    threading.Thread(target=_lg_kitchen_pair_task,daemon=True).start()
    return True

def lg_kitchen_launch():
    saved=_lg_kitchen_saved()
    if not saved or not saved.get("client_key"):
        raise RuntimeError("Pair the kitchen LG before launching Tivvy TV")
    if saved.get("ip")!=LG_KITCHEN_IP:
        raise RuntimeError("Kitchen LG IP does not match stored identity")
    ws=_LGWebSocket(LG_KITCHEN_IP)
    try:
        ws.connect()
        if saved.get("fingerprint")!=ws.fingerprint:
            raise RuntimeError("Kitchen TV identity changed. Refusing to connect.")
        ws.send(json.dumps(_lg_register_message(saved["client_key"])))
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            ws.sock.settimeout(3)
            try:message=ws.recv_json()
            except socket.timeout:continue
            if message.get("type")=="registered":break
            if message.get("type")=="error":
                raise RuntimeError("Kitchen LG rejected its pairing key")
        else:raise RuntimeError("Kitchen LG did not confirm its pairing")
        ws.send(json.dumps({"type":"request","id":"eldoret-kitchen-browser",
                           "uri":"ssap://system.launcher/launch",
                           "payload":{"id":"com.webos.app.browser",
                                      "params":{"target":"https://is.gd/TivvyTV26"}}}))
        deadline=time.monotonic()+6
        while time.monotonic()<deadline:
            ws.sock.settimeout(max(.3,deadline-time.monotonic()))
            try:message=ws.recv_json()
            except socket.timeout:break
            if message.get("id")!="eldoret-kitchen-browser":continue
            if message.get("type")=="error" or (message.get("payload") or {}).get("returnValue") is False:
                raise RuntimeError("Kitchen LG rejected browser launch")
            return {"ok":True,"detail":"Kitchen LG accepted Tivvy TV browser launch. Check picture."}
        return {"ok":True,"detail":"Kitchen LG browser launch sent; no confirmation received. Check picture."}
    finally:
        ws.close()


# Kitchen wake-on-LAN: never reuse lounge MAC, identity or verification state.
LG_KITCHEN_WOL_FILE=os.path.expanduser("~/eldoret-connector/lg/kitchen-wol.json")
LG_KITCHEN_WOL_LOCK=threading.Lock()
LG_KITCHEN_WOL_VERIFY={"state":"idle","detail":"No kitchen wake test has run.","checked_at":None}

def lg_kitchen_wol_status():
    import stat
    saved=None
    try:
        st=os.stat(LG_KITCHEN_WOL_FILE)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077:
            raise RuntimeError("Kitchen wake file has unsafe permissions")
        with open(LG_KITCHEN_WOL_FILE,encoding="utf-8") as f:saved=json.load(f)
    except FileNotFoundError:pass
    paired=_lg_kitchen_saved()
    ready=bool(saved and paired and saved.get("ip")==LG_KITCHEN_IP and
               saved.get("mac") and saved.get("fingerprint")==paired.get("fingerprint"))
    with LG_KITCHEN_WOL_LOCK:verification=dict(LG_KITCHEN_WOL_VERIFY)
    return {"ready":ready,"ip":LG_KITCHEN_IP,
            "verification":verification,
            "detail":"Kitchen MAC verified and saved from paired LG" if ready else
                     "Kitchen TV wake is not ready. Learn its MAC while TV is on."}

def lg_kitchen_learn_mac():
    ws=_LGWebSocket(LG_KITCHEN_IP)
    try:
        saved=_lg_kitchen_saved()
        if not saved or not saved.get("client_key") or saved.get("ip")!=LG_KITCHEN_IP:
            raise RuntimeError("Pair kitchen LG before learning its MAC")
        ws.connect()
        if ws.fingerprint!=saved.get("fingerprint"):
            raise RuntimeError("Kitchen TV identity changed. Refusing MAC learning.")
        ws.send(json.dumps(_lg_register_message(saved["client_key"])))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            ws.sock.settimeout(2)
            try:reply=ws.recv_json()
            except socket.timeout:continue
            if reply.get("type")=="registered":break
            if reply.get("type")=="error":raise RuntimeError("Kitchen LG rejected pairing")
        else:raise RuntimeError("Kitchen LG did not confirm pairing")
        result,ok=_lg_ssap_request(ws,"eldoret-kitchen-wol-identify",
                              "ssap://com.webos.applicationManager/getForegroundAppInfo")
        if not ok:raise RuntimeError("Kitchen TV did not authenticate MAC learning request")
        mac=_lg_mac_from_arp(LG_KITCHEN_IP)
        if not mac:raise RuntimeError("Kitchen TV LAN MAC not found; keep TV on and retry")
        import tempfile
        folder=os.path.dirname(LG_KITCHEN_WOL_FILE)
        os.makedirs(folder,mode=0o700,exist_ok=True);os.chmod(folder,0o700)
        fd,tmp=tempfile.mkstemp(prefix=".kitchen-wol-",dir=folder)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                json.dump({"ip":LG_KITCHEN_IP,"mac":mac,"fingerprint":saved["fingerprint"],
                           "learned_at":datetime.now(timezone.utc).isoformat()},f)
            os.replace(tmp,LG_KITCHEN_WOL_FILE)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return {"ok":True,"detail":"Kitchen TV MAC securely remembered. Ready to test wake from standby."}
    finally:
        ws.close()

def _lg_kitchen_wol_monitor():
    deadline=time.monotonic()+42
    while time.monotonic()<deadline:
        ws=None
        try:
            saved=_lg_kitchen_saved()
            ws=_LGWebSocket(LG_KITCHEN_IP)
            ws.connect()
            if not saved or ws.fingerprint!=saved.get("fingerprint"):
                raise RuntimeError("Kitchen LG certificate mismatch")
            ws.send(json.dumps(_lg_register_message(saved["client_key"])))
            register_deadline=time.monotonic()+8
            registered=False
            while time.monotonic()<register_deadline:
                ws.sock.settimeout(2)
                try:reply=ws.recv_json()
                except socket.timeout:continue
                if reply.get("type")=="registered":registered=True;break
                if reply.get("type")=="error":break
            if registered:
                _,ok=_lg_ssap_request(ws,"eldoret-kitchen-wol-verify",
                    "ssap://com.webos.applicationManager/getForegroundAppInfo")
                if ok:
                    with LG_KITCHEN_WOL_LOCK:
                        LG_KITCHEN_WOL_VERIFY.update(state="responding",detail="Kitchen LG authenticated after wake. Check picture.",
                            checked_at=datetime.now(timezone.utc).isoformat())
                    return
        except Exception:pass
        finally:
            if ws:ws.close()
        time.sleep(3)
    with LG_KITCHEN_WOL_LOCK:
        LG_KITCHEN_WOL_VERIFY.update(state="timeout",detail="Kitchen LG did not respond within 42 seconds.",
                checked_at=datetime.now(timezone.utc).isoformat())

def lg_kitchen_wake():
    import re
    state=lg_kitchen_wol_status()
    if not state["ready"]:raise RuntimeError("Remember kitchen LG MAC while TV is on before waking it")
    with open(LG_KITCHEN_WOL_FILE,encoding="utf-8") as f:wol=json.load(f)
    mac=wol["mac"]
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}",str(mac)):
        raise RuntimeError("Kitchen MAC format invalid")
    packet=bytes([255])*6+bytes.fromhex(mac.replace(":",""))*16
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        sock.settimeout(2)
        sock.sendto(packet,("10.0.0.255",9))
    finally:sock.close()
    with LG_KITCHEN_WOL_LOCK:
        LG_KITCHEN_WOL_VERIFY.update(state="checking",detail="Kitchen wake packet sent; checking for authenticated TV response.",
            checked_at=datetime.now(timezone.utc).isoformat())
    threading.Thread(target=_lg_kitchen_wol_monitor,daemon=True).start()
    return {"ok":True,"detail":"Kitchen wake packet sent. Checking response for up to 42 seconds."}


# Five additional independently paired LG TVs (fixed trusted addresses only).
# Kids' rooms deliberately expose pairing + volume/mute/channel controls only.
LG_EXTRA_ROOMS={
    "pit":{"ip":"10.0.0.47","media":True},
    "bedroom":{"ip":"10.0.0.45","media":True},
    "jesse":{"ip":"10.0.0.49","media":False},
    "ella":{"ip":"10.0.0.40","media":False},
    "thea":{"ip":"10.0.0.43","media":False},
}
LG_EXTRA_LOCK=threading.Lock()
LG_EXTRA_JOBS={room:{"state":"idle","detail":"Ready for individual pairing.","at":None,"busy":False} for room in LG_EXTRA_ROOMS}
LG_EXTRA_WOL={room:{"state":"idle","detail":"Not yet wake-tested.","checked_at":None} for room in ("pit","bedroom")}
LG_EXTRA_WOL_LOCK=threading.Lock()

def _lg_extra_config(room):
    if room not in LG_EXTRA_ROOMS:raise ValueError("Unknown TV room")
    return LG_EXTRA_ROOMS[room]

def _lg_extra_file(room,kind="pair"):
    _lg_extra_config(room)
    name=room+".json" if kind=="pair" else room+"-wol.json"
    return os.path.expanduser("~/eldoret-connector/lg/"+name)

def _lg_extra_read(room,kind="pair"):
    import stat
    path=_lg_extra_file(room,kind)
    try:
        st=os.stat(path)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077:
            raise RuntimeError("TV "+room+" storage permissions unsafe")
        with open(path,encoding="utf-8") as f:return json.load(f)
    except FileNotFoundError:return None

def _lg_extra_write(room,kind,record):
    import tempfile
    path=_lg_extra_file(room,kind)
    folder=os.path.dirname(path)
    os.makedirs(folder,mode=0o700,exist_ok=True)
    os.chmod(folder,0o700)
    fd,temp=tempfile.mkstemp(prefix="."+room+"-",dir=folder)
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as f:json.dump(record,f)
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def _lg_extra_status(room):
    cfg=_lg_extra_config(room)
    with LG_EXTRA_LOCK:job=dict(LG_EXTRA_JOBS[room])
    job.pop("busy",None)
    try:saved=_lg_extra_read(room)
    except RuntimeError as exc:
        saved=None
        job.update(state="error",detail=str(exc))
    job.update(ip=cfg["ip"],paired=bool(saved and saved.get("client_key") and
                                        saved.get("ip")==cfg["ip"]),
               media=cfg["media"])
    return job

def _lg_extra_set(room,state,detail):
    with LG_EXTRA_LOCK:
        LG_EXTRA_JOBS[room].update(state=state,detail=detail,at=datetime.now(timezone.utc).isoformat())

def _lg_extra_pair_worker(room):
    cfg=_lg_extra_config(room)
    ws=None
    try:
        saved=_lg_extra_read(room)
        ws=_LGWebSocket(cfg["ip"])
        _lg_extra_set(room,"connecting","Connecting securely to "+room+" TV...")
        ws.connect()
        if saved and saved.get("fingerprint")!=ws.fingerprint:
            raise RuntimeError("TV identity changed. Pairing stopped.")
        _lg_extra_set(room,"waiting","Accept the Eldoret pairing prompt on the "+room+" TV.")
        ws.send(json.dumps(_lg_register_message((saved or {}).get("client_key"))))
        deadline=time.monotonic()+65
        while time.monotonic()<deadline:
            ws.sock.settimeout(min(6,max(1,deadline-time.monotonic())))
            try:message=ws.recv_json()
            except socket.timeout:continue
            if message.get("type")=="registered":
                key=(message.get("payload") or {}).get("client-key") or (saved or {}).get("client_key")
                if not isinstance(key,str) or len(key)<10:raise RuntimeError("TV did not grant pairing key")
                _lg_extra_write(room,"pair",{"ip":cfg["ip"],"client_key":key,
                          "fingerprint":ws.fingerprint,
                          "paired_at":datetime.now(timezone.utc).isoformat()})
                _lg_extra_set(room,"paired","Paired with Bulldog. Remote controls ready.")
                return
            if message.get("type")=="error":raise RuntimeError("TV rejected pairing")
        raise RuntimeError("Pairing timed out: no approval received.")
    except Exception as exc:
        _lg_extra_set(room,"error",str(exc)[:180])
    finally:
        if ws:ws.close()
        with LG_EXTRA_LOCK:LG_EXTRA_JOBS[room]["busy"]=False

def lg_extra_pair_start(room):
    _lg_extra_config(room)
    with LG_EXTRA_LOCK:
        if LG_EXTRA_JOBS[room]["busy"]:return False
        LG_EXTRA_JOBS[room]["busy"]=True
    threading.Thread(target=_lg_extra_pair_worker,args=(room,),daemon=True).start()
    return True

def _lg_extra_open(room):
    cfg=_lg_extra_config(room)
    saved=_lg_extra_read(room)
    if not saved or not saved.get("client_key") or saved.get("ip")!=cfg["ip"]:
        raise RuntimeError("Pair "+room+" TV first")
    ws=_LGWebSocket(cfg["ip"])
    try:
        ws.connect()
        if ws.fingerprint!=saved.get("fingerprint"):
            raise RuntimeError("TV certificate changed. Connection refused.")
        ws.send(json.dumps(_lg_register_message(saved["client_key"])))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            ws.sock.settimeout(2)
            try:reply=ws.recv_json()
            except socket.timeout:continue
            if reply.get("type")=="registered":return ws
            if reply.get("type")=="error":raise RuntimeError("TV rejected stored pairing")
        raise RuntimeError("TV did not confirm pairing")
    except Exception:
        ws.close()
        raise

def lg_extra_control(room,action):
    # Strictly limited to benign basic remote keys; no media controls on kids' rooms.
    actions={"volume_up":("ssap://audio/volumeUp",None),
             "volume_down":("ssap://audio/volumeDown",None),
             "mute":("ssap://audio/setMute",{"mute":True}),
             "unmute":("ssap://audio/setMute",{"mute":False}),
             "channel_up":("ssap://tv/channelUp",None),
             "channel_down":("ssap://tv/channelDown",None)}
    if action not in actions:raise ValueError("Unsupported TV control")
    ws=_lg_extra_open(room)
    try:
        uri,payload=actions[action]
        _,ok=_lg_ssap_request(ws,"eldoret-"+room+"-control",uri,payload)
        if not ok:raise RuntimeError("TV did not acknowledge "+action)
        return {"ok":True,"detail":room.title()+" TV acknowledged "+action.replace("_"," ")}
    finally:ws.close()

def lg_extra_media(room,action):
    if not _lg_extra_config(room)["media"]:
        raise ValueError("Media shortcuts are unavailable in this room")
    ws=_lg_extra_open(room)
    try:
        if action=="tivvy":
            _,ok=_lg_ssap_request(ws,"eldoret-"+room+"-tivvy",
                      "ssap://system.launcher/launch",
                      {"id":"com.webos.app.browser","params":{"target":"https://is.gd/TivvyTV26"}})
            if not ok:raise RuntimeError("TV did not acknowledge Tivvy browser launch")
            return {"ok":True,"detail":"TV accepted Tivvy TV launch; check the picture."}
        if action=="hdmi1":
            import re
            data,ok=_lg_ssap_request(ws,"eldoret-"+room+"-inputs",
                                         "ssap://tv/getExternalInputList")
            if not ok or not isinstance(data,dict):
                raise RuntimeError("Could not read TV inputs")
            ids=[x.get("id") for x in (data.get("devices") or [])
                 if isinstance(x,dict) and isinstance(x.get("id"),str)
                 and re.search(r"(?i)(?:^|[^a-z0-9])hdmi[ _-]*1(?:$|[^0-9])",x["id"])]
            if len(ids)!=1:raise RuntimeError("HDMI 1 was not identified unambiguously")
            _,ok=_lg_ssap_request(ws,"eldoret-"+room+"-switch",
                                     "ssap://tv/switchInput",{"inputId":ids[0]})
            if not ok:raise RuntimeError("TV did not acknowledge HDMI 1")
            return {"ok":True,"detail":"TV acknowledged HDMI 1 (Sky Q); check picture."}
        raise ValueError("Unknown media action")
    finally:ws.close()

def lg_extra_wol_status(room):
    cfg=_lg_extra_config(room)
    if not cfg["media"]:raise ValueError("Wake functions not available in this room")
    saved=_lg_extra_read(room)
    wake=_lg_extra_read(room,"wol")
    ready=bool(saved and wake and wake.get("mac") and
               saved.get("ip")==cfg["ip"] and wake.get("ip")==cfg["ip"]
               and saved.get("fingerprint")==wake.get("fingerprint"))
    with LG_EXTRA_WOL_LOCK:verify=dict(LG_EXTRA_WOL[room])
    return {"ready":ready,"ip":cfg["ip"],"verification":verify,
            "detail":"Wake MAC securely stored" if ready else "Learn MAC while TV is on"}

def lg_extra_learn_mac(room):
    if not _lg_extra_config(room)["media"]:
        raise ValueError("Wake function not available")
    ws=_lg_extra_open(room)
    try:
        _,ok=_lg_ssap_request(ws,"eldoret-"+room+"-identify",
                  "ssap://com.webos.applicationManager/getForegroundAppInfo")
        if not ok:raise RuntimeError("TV did not authenticate MAC learning")
        mac=_lg_mac_from_arp(LG_EXTRA_ROOMS[room]["ip"])
        if not mac:raise RuntimeError("TV LAN MAC not found. Check TV on and connection.")
        saved=_lg_extra_read(room)
        _lg_extra_write(room,"wol",{"ip":LG_EXTRA_ROOMS[room]["ip"],
                          "mac":mac,"fingerprint":saved["fingerprint"],
                          "learned_at":datetime.now(timezone.utc).isoformat()})
        return {"ok":True,"detail":"MAC saved securely for "+room+" TV"}
    finally:ws.close()

def _lg_extra_wol_verify(room):
    deadline=time.monotonic()+42
    while time.monotonic()<deadline:
        ws=None
        try:
            ws=_lg_extra_open(room)
            _,ok=_lg_ssap_request(ws,"eldoret-"+room+"-wake-verify",
                  "ssap://com.webos.applicationManager/getForegroundAppInfo")
            if ok:
                with LG_EXTRA_WOL_LOCK:
                    LG_EXTRA_WOL[room].update(state="responding",
                        detail="Paired TV authenticated after wake",
                        checked_at=datetime.now(timezone.utc).isoformat())
                return
        except Exception:pass
        finally:
            if ws:ws.close()
        time.sleep(3)
    with LG_EXTRA_WOL_LOCK:
        LG_EXTRA_WOL[room].update(state="timeout",
            detail="No authenticated TV response within 42 seconds",
            checked_at=datetime.now(timezone.utc).isoformat())

def lg_extra_wake(room):
    import re
    if not lg_extra_wol_status(room)["ready"]:
        raise RuntimeError("Learn "+room+" TV MAC first")
    config=_lg_extra_read(room,"wol")
    mac=config["mac"]
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}",str(mac)):
        raise RuntimeError("Invalid stored TV MAC")
    packet=bytes([255])*6+bytes.fromhex(mac.replace(":",""))*16
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        sock.settimeout(2)
        sock.sendto(packet,("10.0.0.255",9))
    finally:sock.close()
    with LG_EXTRA_WOL_LOCK:
        LG_EXTRA_WOL[room].update(state="checking",
            detail="Wake packet sent; authenticating TV response",
            checked_at=datetime.now(timezone.utc).isoformat())
    threading.Thread(target=_lg_extra_wol_verify,args=(room,),daemon=True).start()
    return {"ok":True,"detail":"Wake sent. Waiting for authenticated TV response."}


# Experimental lounge LG telemetry. The TV is the source of truth; never infer state from our buttons.
LG_LIVE_LOCK=threading.Lock()
LG_LIVE_CACHE={"at":0,"data":None}
LG_LIVE_PERMISSIONS=["LAUNCH","READ_RUNNING_APPS","READ_APP_STATUS","READ_INPUT_DEVICE_LIST",
                     "READ_CURRENT_CHANNEL","READ_POWER_STATE","CONTROL_AUDIO","CONTROL_INPUT_TV",
                     "CONTROL_POWER"]
def _lg_open_paired():
    saved=_lg_saved()
    if not saved or not saved.get("client_key"):
        raise RuntimeError("LG is not paired")
    ws=_LGWebSocket(LG_LOUNGE_IP)
    try:
        ws.connect()
        if saved.get("fingerprint") != ws.fingerprint:
            raise RuntimeError("Paired LG certificate changed. Connection blocked.")
        ws.send(json.dumps(_lg_register_message(saved["client_key"])))
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            ws.sock.settimeout(2)
            try: msg=ws.recv_json()
            except socket.timeout: continue
            if msg.get("type")=="registered": return ws
            if msg.get("type")=="error": raise RuntimeError("LG declined existing pairing")
        raise RuntimeError("LG did not confirm pairing")
    except Exception:
        ws.close()
        raise

def _lg_ssap_request(ws, request_id, uri, payload=None):
    obj={"type":"request","id":request_id,"uri":uri}
    if payload is not None:obj["payload"]=payload
    ws.send(json.dumps(obj))
    deadline=time.monotonic()+2.5
    while time.monotonic()<deadline:
        ws.sock.settimeout(max(.2, deadline-time.monotonic()))
        try: reply=ws.recv_json()
        except socket.timeout: break
        if reply.get("id") != request_id: continue
        data=reply.get("payload") or {}
        if reply.get("type")=="error" or data.get("returnValue") is False:
            return None, False
        return data, True
    return None, False

def lg_switch_sky_hdmi1(room):
    """Select verified HDMI 1 on one paired LG; does not control/power on Sky Q."""
    import re
    if room=="lounge":
        ws=_lg_open_paired()
    elif room=="kitchen":
        saved=_lg_kitchen_saved()
        if not saved or not saved.get("client_key") or saved.get("ip")!=LG_KITCHEN_IP:
            raise RuntimeError("Kitchen LG not paired")
        ws=_LGWebSocket(LG_KITCHEN_IP)
        try:
            ws.connect()
            if saved.get("fingerprint")!=ws.fingerprint:
                raise RuntimeError("Kitchen LG identity mismatch")
            ws.send(json.dumps(_lg_register_message(saved["client_key"])))
            deadline=time.monotonic()+10
            while time.monotonic()<deadline:
                ws.sock.settimeout(2)
                try:reply=ws.recv_json()
                except socket.timeout:continue
                if reply.get("type")=="registered":break
                if reply.get("type")=="error":raise RuntimeError("Kitchen LG rejected pairing")
            else:raise RuntimeError("Kitchen LG did not confirm pairing")
        except Exception:
            ws.close()
            raise
    else:raise ValueError("Unknown TV room")
    try:
        data,ok=_lg_ssap_request(ws,"eldoret-hdmi-list",
                                "ssap://tv/getExternalInputList")
        if not ok or not isinstance(data,dict):
            raise RuntimeError("TV did not provide its current input list; HDMI 1 not selected")
        matches=[]
        for item in (data.get("devices") or []):
            if not isinstance(item,dict):continue
            input_id=item.get("id")
            if not isinstance(input_id,str) or not input_id:continue
            # Prefer the TV's actual HDMI_1 ID; some models call it HDMI 1.
            if re.search(r"(?i)(?:^|[^a-z0-9])hdmi[ _-]*1(?:$|[^0-9])",input_id):
                matches.append(input_id)
        if len(matches)!=1:
            raise RuntimeError("Could not identify one unambiguous HDMI 1 from TV input list")
        _,accepted=_lg_ssap_request(ws,"eldoret-hdmi-one",
                  "ssap://tv/switchInput",{"inputId":matches[0]})
        if not accepted:
            raise RuntimeError("TV did not acknowledge HDMI 1 input switch")
        return {"ok":True,"detail":room.capitalize()+" LG acknowledged HDMI 1 selection. Check Sky Q picture."}
    finally:ws.close()


def lg_lounge_live():
    """Read-only and bounded; measurements are from the TV, never command guesses."""
    now=time.monotonic()
    with LG_LIVE_LOCK:
        cached=LG_LIVE_CACHE["data"]
        if cached is not None and now-LG_LIVE_CACHE["at"]<20:
            return dict(cached)
        if LG_LIVE_CACHE.get("busy"):
            return dict(cached) if cached else {"online":None,"detail":"Reading lounge LG...","ip":LG_LOUNGE_IP}
        LG_LIVE_CACHE["busy"]=True
    data={"ip":LG_LOUNGE_IP,"online":False,"source":"LG webOS direct SSAP",
          "checked_at":datetime.now(timezone.utc).isoformat(),
          "app":None,"app_name":None,"app_type":None,"input":None,"inputs":[],
          "volume":None,"muted":None,"audio_output":None,
          "channel":None,"channel_number":None,"channel_id":None,"channel_type":None,
          "power":None,"model":None,"software":None,"device_name":None,
          "country":None,"service_results":{},"detail":"Waiting for LG response"}
    ws=None
    def bounded(value,length=100):
        if value is None:return None
        text=str(value).strip()
        return text[:length] if text else None
    try:
        ws=_lg_open_paired()
        data["online"]=True
        data["power"]="On (responding)"
        # Non-critical services may be missing on particular webOS generations.
        calls=[
            ("application","ssap://com.webos.applicationManager/getForegroundAppInfo"),
            ("inputs","ssap://tv/getExternalInputList"),
            ("volume","ssap://audio/getVolume"),
            ("channel","ssap://tv/getCurrentChannel"),
            ("power","ssap://com.webos.service.tvpower/power/getPowerState"),
            ("system","ssap://com.webos.service.tv.systemproperty/getSystemInfo"),
            ("audio_output","ssap://com.webos.service.apiadapter/audio/getSoundOutput"),
        ]
        for key,uri in calls:
            result,ok=_lg_ssap_request(ws,"eldoret-read-"+key,uri)
            data["service_results"][key]="responded" if ok else "not available"
            if not ok or not isinstance(result,dict):continue
            if key=="application":
                app=bounded(result.get("appId") or result.get("id"))
                data["app"]=app
                data["app_name"]=bounded(result.get("appName") or result.get("title"))
                data["app_type"]=bounded(result.get("processId") or result.get("windowType"))
                if app and (".externalinput." in app or app.startswith("com.webos.app.hdmi")):
                    data["input"]=app
            elif key=="inputs":
                devices=result.get("devices") or []
                if not isinstance(devices,list):devices=[]
                data["inputs"]=[{"id":bounded(v.get("id"),80),"label":bounded(v.get("label") or v.get("id"),80),
                    "connected":v.get("connected") if isinstance(v.get("connected"),bool) else None}
                    for v in devices[:16] if isinstance(v,dict) and v.get("id")]
            elif key=="volume":
                v=result.get("volume")
                data["volume"]=v if type(v) is int and 0<=v<=100 else None
                data["muted"]=result.get("muted") if type(result.get("muted")) is bool else None
                data["audio_output"]=bounded(result.get("soundOutput") or result.get("output"))
            elif key=="channel":
                data["channel"]=bounded(result.get("channelName"))
                data["channel_number"]=bounded(result.get("channelNumber"))
                data["channel_id"]=bounded(result.get("channelId"))
                data["channel_type"]=bounded(result.get("channelType"))
            elif key=="power":
                data["power"]=bounded(result.get("state")) or "On (responding)"
            elif key=="system":
                features=result.get("features") or {}
                if not isinstance(features,dict):features={}
                data["model"]=bounded(result.get("modelName") or result.get("model"))
                data["software"]=bounded(result.get("firmwareVersion") or result.get("softwareVersion"))
                data["device_name"]=bounded(result.get("deviceName"))
                data["country"]=bounded(result.get("country"))
            elif key=="audio_output":
                data["audio_output"]=bounded(result.get("soundOutput") or result.get("output")) or data["audio_output"]
        # External input list is authoritative for a matching foreground app.
        if data["app"]:
            for item in data["inputs"]:
                if item["id"]==data["app"]:
                    data["input"]=item["label"] or item["id"]
                    break
        count=sum(x=="responded" for x in data["service_results"].values())
        data["detail"]="TV connected · "+str(count)+" of "+str(len(calls))+" readback services responded"
    except Exception:
        data["detail"]="Lounge LG not responding or pairing needs renewal."
    finally:
        if ws:ws.close()
        with LG_LIVE_LOCK:
            LG_LIVE_CACHE.update(at=time.monotonic(),data=dict(data),busy=False)
    return data

def lg_lounge_control(action, input_id=None):
    # No raw URI or arbitrary command passthrough from the browser.
    actions={"volume_up":("ssap://audio/volumeUp",None),
             "volume_down":("ssap://audio/volumeDown",None),
             "mute":("ssap://audio/setMute",{"mute":True}),
             "unmute":("ssap://audio/setMute",{"mute":False}),
             "channel_up":("ssap://tv/channelUp",None),
             "channel_down":("ssap://tv/channelDown",None)}
    if action=="input":
        info=lg_lounge_live()
        choices=[x["id"] for x in info.get("inputs",[]) if x.get("id")]
        if not input_id or input_id not in choices or not info.get("online"):
            raise ValueError("Please select a currently reported LG input")
        uri,payload="ssap://tv/switchInput",{"inputId":input_id}
    elif action in actions:
        uri,payload=actions[action]
    else:raise ValueError("Unsupported TV control")
    ws=_lg_open_paired()
    try:
        response,ok=_lg_ssap_request(ws,"eldoret-control",uri,payload)
        if not ok:raise RuntimeError("LG did not confirm the requested control")
    finally:
        ws.close()
    with LG_LIVE_LOCK:
        LG_LIVE_CACHE["at"]=0
    return {"ok":True,"detail":"LG acknowledged "+action.replace("_"," ")+". Await fresh readback."}


# Lounge WOL pilot. MAC is learned from the LAN neighbour entry only after
# authenticating to the ALREADY PAIRED TV; no guessed MAC or broadcast scanning.
LG_WOL_FILE=os.path.expanduser("~/eldoret-connector/lg/lounge-wol.json")
LG_WOL_VERIFY_LOCK=threading.Lock()
LG_WOL_VERIFY={"state":"idle","detail":"No wake test has run.","checked_at":None}
def _lg_wol_monitor():
    # Distinguish "magic packet sent" from a TV verified through its existing pairing.
    deadline=time.monotonic()+42
    while time.monotonic()<deadline:
        ws=None
        try:
            ws=_lg_open_paired()
            reply,ok=_lg_ssap_request(ws,"eldoret-wol-verify",
                "ssap://com.webos.applicationManager/getForegroundAppInfo")
            if ok:
                with LG_WOL_VERIFY_LOCK:
                    LG_WOL_VERIFY.update(state="responding",detail=
                        "LG authenticated and responded after the wake packet. Please visually confirm the picture.",
                        checked_at=datetime.now(timezone.utc).isoformat())
                return
        except Exception:
            pass
        finally:
            if ws:ws.close()
        time.sleep(3)
    with LG_WOL_VERIFY_LOCK:
        LG_WOL_VERIFY.update(state="timeout",detail=
            "No authenticated LG response within 42 seconds. Wake not verified; check LG standby network settings.",
            checked_at=datetime.now(timezone.utc).isoformat())

def _lg_mac_from_arp(ip):
    import re
    with open("/proc/net/arp",encoding="ascii") as f:
        rows=f.readlines()[1:]
    for row in rows:
        fields=row.split()
        if len(fields)<6 or fields[0]!=ip or fields[2]!="0x2":continue
        mac=fields[3].lower()
        if re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}",mac) and mac!="00:00:00:00:00:00":
            return mac
    return None

def lg_lounge_wol_status():
    import stat
    saved=None
    try:
        info=os.stat(LG_WOL_FILE)
        if info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)&0o077:
            raise RuntimeError("Wake configuration permissions unsafe")
        with open(LG_WOL_FILE,encoding="utf-8") as f:saved=json.load(f)
    except FileNotFoundError:pass
    with LG_WOL_VERIFY_LOCK: verification=dict(LG_WOL_VERIFY)
    return {"ready":bool(saved and saved.get("mac") and saved.get("ip")==LG_LOUNGE_IP),
            "ip":LG_LOUNGE_IP,"mac":saved.get("mac") if saved else None,
            "verification":verification,
            "detail":"MAC securely recorded from paired lounge LG" if saved else "TV MAC not recorded. Learn it while television is on."}

def lg_lounge_learn_mac():
    # Validate this TV identity through its existing client key and TLS fingerprint.
    ws=_lg_open_paired()
    try:
        # Query confirms responsive authenticated SSAP, not merely an open TCP port.
        result,ok=_lg_ssap_request(ws,"eldoret-wol-identify",
                                  "ssap://com.webos.applicationManager/getForegroundAppInfo")
        if not ok:raise RuntimeError("Could not verify paired TV before learning MAC")
        # Reading neighbour table after talking to that IP ensures recent ARP.
        mac=_lg_mac_from_arp(LG_LOUNGE_IP)
        if not mac:raise RuntimeError("No verified LAN MAC entry for lounge TV. Check wired/Wi-Fi setup.")
        saved=_lg_saved()
        if not saved or not saved.get("fingerprint"):raise RuntimeError("Missing LG pairing fingerprint")
        folder=os.path.dirname(LG_WOL_FILE)
        os.makedirs(folder,mode=0o700,exist_ok=True)
        os.chmod(folder,0o700)
        import tempfile
        fd,tmp=tempfile.mkstemp(prefix=".wol-",dir=folder)
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as f:
                json.dump({"ip":LG_LOUNGE_IP,"mac":mac,"fingerprint":saved["fingerprint"],
                           "learned_at":datetime.now(timezone.utc).isoformat()},f)
            os.replace(tmp,LG_WOL_FILE)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return {"ok":True,"detail":"Learned lounge TV MAC from paired local TV. You can now try waking it from standby.","mac":mac}
    finally:ws.close()

def lg_lounge_wake():
    import re
    cfg=lg_lounge_wol_status()
    if not cfg["ready"]:raise RuntimeError("Learn and verify the lounge TV MAC before trying wake-up")
    saved=_lg_saved()
    with open(LG_WOL_FILE,encoding="utf-8") as f:wol=json.load(f)
    if not saved or saved.get("fingerprint")!=wol.get("fingerprint"):
        raise RuntimeError("Paired TV identity changed. Wake refused.")
    mac=cfg["mac"]
    if not re.fullmatch(r"(?:[0-9a-f]{2}:){5}[0-9a-f]{2}",str(mac)):
        raise RuntimeError("Saved MAC format invalid")
    binary=bytes.fromhex(mac.replace(":",""))
    packet=b"\xff"*6+binary*16
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_BROADCAST,1)
        sock.settimeout(2)
        sock.sendto(packet,("10.0.0.255",9))
    finally:sock.close()
    with LG_WOL_VERIFY_LOCK:
        LG_WOL_VERIFY.update(state="checking",detail="Wake packet sent. Waiting for authenticated LG response...",
                             checked_at=datetime.now(timezone.utc).isoformat())
    threading.Thread(target=_lg_wol_monitor,daemon=True).start()
    return {"ok":True,"detail":"Wake packet sent. Bulldog will check for a confirmed LG reply for up to 42 seconds."}

def lg_tv_status(ip=None):
    ip=ip or _registry_ip("lg_tv_1","10.0.0.51")
    ports=[p for p in (80,3000,3001) if _tcp_open(ip,p,timeout=0.5)]
    return {
        "ip":ip,
        "online":bool(ports),
        "ports":ports,
        "webos_plain":3000 in ports,
        "webos_tls":3001 in ports,
        "paired":False,
        "detail":("LG webOS service detected; ready for one-time TV pairing." if (3000 in ports or 3001 in ports)
                  else ("LG device reachable on HTTP." if 80 in ports else "No configured LG service answered."))
    }

def playstation_status(ip=None):
    ip=ip or _registry_ip("playstation","10.0.0.48")
    result = {"online": False, "ip": ip, "host_type": None, "host_name": None,
              "system_version": None, "running_app_name": None, "running_app_titleid": None,
              "status_code": None, "detail": "No PlayStation discovery reply."}
    probes = [
        (9302, b"SRCH * HTTP/1.1\nD-Protocol-Version:00030010\n"),
        (987,  b"SRCH * HTTP/1.1\nD-Protocol-Version:00020020\n"),
    ]
    for port, payload in probes:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(0.8)
        try:
            sock.sendto(payload, (ip, port))
            data, addr = sock.recvfrom(4096)
            if addr[0] != ip:
                continue
            text = data.decode("utf-8", errors="replace").replace("\r", "")
            lines = [x.strip() for x in text.split("\n") if x.strip()]
            fields = {}
            if lines:
                parts = lines[0].split()
                if len(parts) >= 2 and parts[1].isdigit():
                    result["status_code"] = int(parts[1])
            for line in lines[1:]:
                if ":" in line:
                    k, v = line.split(":", 1)
                    fields[k.strip().lower()] = v.strip()
            result.update({
                "online": True,
                "host_type": fields.get("host-type"),
                "host_name": fields.get("host-name"),
                "system_version": fields.get("system-version"),
                "running_app_name": fields.get("running-app-name"),
                "running_app_titleid": fields.get("running-app-titleid"),
                "detail": "PlayStation discovery reply received on UDP " + str(port)
            })
            return result
        except Exception:
            pass
        finally:
            sock.close()
    return result


# Private, local PS5 availability / app telemetry. Never uses PSN credentials.
PS5_ACTIVITY_FILE = os.path.expanduser("~/eldoret-connector/playstation-activity.json")
PS5_ACTIVITY_LOCK = threading.Lock()
PS5_ACTIVITY = {"last":None, "events":[], "sessions":[], "last_checked":None}
def _ps5_load():
    try:
        with open(PS5_ACTIVITY_FILE,encoding="utf-8") as stream:
            data=json.load(stream)
        if isinstance(data,dict):
            for k in ("last","events","sessions","last_checked"):
                if k in data:
                    PS5_ACTIVITY[k]=data[k]
    except (OSError,ValueError,TypeError):
        pass

def _ps5_save():
    try:
        target=PS5_ACTIVITY_FILE+".new"
        fd=os.open(target,os.O_WRONLY | os.O_CREAT | os.O_TRUNC,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(PS5_ACTIVITY,stream,separators=(",",":"))
        os.replace(target,PS5_ACTIVITY_FILE)
    except OSError:
        pass

def _ps5_record(sample):
    # Store observed transitions, not every check or inferred 'gameplay'.
    now=datetime.now(timezone.utc).isoformat()
    state={"online":bool(sample.get("online")),
           "game":sample.get("running_app_name") or None,
           "titleid":sample.get("running_app_titleid") or None}
    with PS5_ACTIVITY_LOCK:
        old=PS5_ACTIVITY.get("last")
        changed=old is None or old!=state
        if changed:
            if old is not None:
                if old.get("online")!=state["online"]:
                    PS5_ACTIVITY["events"].append({"at":now,"kind":"console",
                        "detail":"Responding" if state["online"] else "No discovery reply"})
                if old.get("game")!=state["game"] or old.get("titleid")!=state["titleid"]:
                    if old.get("game") or old.get("titleid"):
                        sessions=PS5_ACTIVITY["sessions"]
                        if sessions and not sessions[-1].get("ended_at"):
                            sessions[-1]["ended_at"]=now
                    if state["game"] or state["titleid"]:
                        PS5_ACTIVITY["sessions"].append({"started_at":now,"ended_at":None,
                            "game":str(state["game"] or "Unknown game")[:130],
                            "titleid":str(state["titleid"] or "")[:40]})
                        PS5_ACTIVITY["events"].append({"at":now,"kind":"game",
                            "detail":str(state["game"] or "Game ID reported")[:130]})
            PS5_ACTIVITY["last"]=state
            PS5_ACTIVITY["events"]=PS5_ACTIVITY["events"][-150:]
            PS5_ACTIVITY["sessions"]=PS5_ACTIVITY["sessions"][-100:]
            _ps5_save()
        PS5_ACTIVITY["last_checked"]=now

def _ps5_collector_loop():
    _ps5_load()
    while True:
        try:
            _ps5_record(playstation_status())
        except Exception:
            pass
        time.sleep(60)

# PSN profile presence complements local PS5 discovery. Read-only, bounded and cached.
# Never put the NPSSO token into HTML, GitHub, event logs or remote-state relay.
PSN_BRIDGE=os.path.expanduser("~/eldoret-connector/psn-bridge.py")
PSN_PYTHON=os.path.expanduser("~/psn-test/venv/bin/python")
PSN_CACHE={"at":0.0,"value":None}
PSN_STATUS_LOCK=threading.Lock()

def playstation_network_status():
    with PSN_STATUS_LOCK:
        now=time.monotonic()
        if PSN_CACHE["value"] is not None and now-PSN_CACHE["at"]<120:
            return dict(PSN_CACHE["value"])
        if not os.path.isfile(PSN_BRIDGE) or not os.path.isfile(PSN_PYTHON):
            return {"configured":False,"connected":False,
                    "detail":"Private PSN bridge or virtual environment not installed."}
        try:
            proc=subprocess.run([PSN_PYTHON,PSN_BRIDGE,"status"],text=True,
                                capture_output=True,timeout=35,check=False)
            if proc.returncode!=0:
                raise RuntimeError("PSN helper unavailable")
            result=json.loads(proc.stdout)
            if not isinstance(result,dict): raise ValueError("Invalid PSN status")
            PSN_CACHE.update(at=now,value=result)
            return dict(result)
        except (OSError,RuntimeError,ValueError,subprocess.TimeoutExpired):
            failure={"configured":True,"connected":False,
                     "detail":"PSN status unavailable; check token, privacy and internet."}
            PSN_CACHE.update(at=now,value=failure)
            return failure

def playstation_activity_status():
    live=playstation_status()
    with PS5_ACTIVITY_LOCK:
        events=list(PS5_ACTIVITY.get("events",[])[-60:])
        sessions=list(PS5_ACTIVITY.get("sessions",[])[-30:])
        last=PS5_ACTIVITY.get("last_checked")
    psn=playstation_network_status()
    return {"live":live,"psn":psn,"observed_at":datetime.now(timezone.utc).isoformat(),
            "history_started":last,"events":events,"sessions":sessions,
            "game_source":"PSN presence" if psn.get("connected") else "PS5 local discovery",
            "game_available":bool(psn.get("game") or live.get("running_app_name") or live.get("running_app_titleid"))}

def _ipp_attributes(raw):
    """Decode IPP scalar attributes, including repeated values (RFC 8010)."""
    import struct
    if len(raw) < 8 or int.from_bytes(raw[2:4], "big") > 0x00ff:
        raise ValueError("Printer returned an invalid or unsuccessful IPP response")
    attrs, pos, name = {}, 8, None
    while pos < len(raw):
        tag = raw[pos]; pos += 1
        if tag == 3:
            break
        if tag < 0x10:
            name = None
            continue
        if pos + 2 > len(raw): raise ValueError("Truncated IPP attribute")
        size = int.from_bytes(raw[pos:pos+2], "big"); pos += 2
        if pos + size + 2 > len(raw): raise ValueError("Truncated IPP attribute name")
        if size: name = raw[pos:pos+size].decode("utf-8", "replace")
        pos += size
        length = int.from_bytes(raw[pos:pos+2], "big"); pos += 2
        if pos + length > len(raw): raise ValueError("Truncated IPP value")
        value = raw[pos:pos+length]; pos += length
        if not name: continue
        if tag in (0x21, 0x23) and length == 4:
            value = struct.unpack(">i", value)[0]
        elif tag == 0x22 and length == 1:
            value = bool(value[0])
        elif tag in (0x41, 0x42, 0x44, 0x45, 0x47, 0x48, 0x49):
            value = value.decode("utf-8", "replace")
        else:
            value = None
        attrs.setdefault(name, []).append(value)
    return attrs


def _ipp_ink(attributes):
    """Keep only explicitly reported CMYK ink percentages; negative values mean unknown."""
    import re
    names = attributes.get("marker-names", [])
    colours = attributes.get("marker-colors", [])
    levels = attributes.get("marker-levels", [])
    types = attributes.get("marker-types", [])
    hex_names = {"#000000":"Black", "#00ffff":"Cyan", "#ff00ff":"Magenta", "#ffff00":"Yellow"}
    found = {}
    for i, level in enumerate(levels):
        if type(level) is not int or not 0 <= level <= 100: continue
        kind = str(types[i] if i < len(types) else "").lower()
        name = str(names[i] if i < len(names) else "").lower()
        if kind and kind not in ("ink", "ink-cartridge", "ink-ribbon"): continue
        if any(word in name for word in ("waste", "maintenance")): continue
        colour = str(colours[i] if i < len(colours) else "").lower()
        label = hex_names.get(colour)
        if not label:
            label = next((word.title() for word in ("black", "cyan", "magenta", "yellow") if re.search(r"\b"+word+r"\b", name)), None)
        if label: found[label] = level
    return [{"colour":label, "percent":found[label]} for label in ("Black", "Cyan", "Magenta", "Yellow") if label in found]


def _epson_web_status(markup):
    """Read Epson percentage bars or ET-3850 image bars (verified 50px tanks)."""
    from html.parser import HTMLParser
    import re

    class Page(HTMLParser):
        def __init__(self):
            super().__init__()
            self.root = {"tag":"", "attrs":{}, "children":[], "text":[]}
            self.stack = [self.root]

        def handle_starttag(self, tag, attrs):
            node = {"tag":tag, "attrs":dict(attrs), "children":[], "text":[]}
            self.stack[-1]["children"].append(node)
            if tag not in ("area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"):
                self.stack.append(node)

        def handle_startendtag(self, tag, attrs):
            self.handle_starttag(tag, attrs)
            self.handle_endtag(tag)

        def handle_endtag(self, tag):
            for i in range(len(self.stack)-1, 0, -1):
                if self.stack[i]["tag"] == tag:
                    del self.stack[i:]
                    break

        def handle_data(self, data):
            for node in self.stack:
                node["text"].append(data)

    page = Page(); page.feed(markup)
    def walk(node):
        yield node
        for child in node["children"]:
            yield from walk(child)
    def classes(node):
        return (node["attrs"].get("class") or "").lower().split()
    def text_of(node):
        return " ".join(" ".join(node["text"]).split())
    colours = {"BK":"Black", "BLACK":"Black", "C":"Cyan", "CYAN":"Cyan",
               "M":"Magenta", "MAGENTA":"Magenta", "Y":"Yellow", "YELLOW":"Yellow"}
    ink, state, connection, estimated = {}, None, None, False
    for node in walk(page.root):
        if node["attrs"].get("id", "").upper() == "PRT_STATUS":
            state = re.sub(r"^printer\s+status\s*[:\-]?\s*", "", text_of(node), flags=re.I).strip()[:200] or None
        if node["tag"] == "tr":
            cells = [n for n in node["children"] if n["tag"] == "td"]
            if len(cells) == 2 and text_of(cells[0]).rstrip(" :") == "Connection Status":
                connection = text_of(cells[1])[:200]
        if node["tag"] != "li" or "tank" not in classes(node):
            continue
        descendants = list(walk(node))
        if any("mbicn" in classes(n) for n in descendants):
            continue
        label = next((colours.get(text_of(n).upper()) for n in descendants if "clrname" in classes(n)), None)
        if not label: continue
        # This firmware renders CMYK as image heights inside 50px tanks.
        # Match each image to its colour label; exclude the maintenance-box gauge.
        code = {"Black":"K", "Cyan":"C", "Magenta":"M", "Yellow":"Y"}[label]
        for image in descendants:
            if image["tag"] != "img" or "color" not in classes(image): continue
            src = urllib.parse.urlparse(image["attrs"].get("src") or "").path
            if src.rsplit("/", 1)[-1].lower() != "ink_" + code.lower() + ".png": continue
            height = image["attrs"].get("height") or ""
            if re.fullmatch(r"\d+(?:\.\d+)?", height) and 0 <= float(height) <= 50:
                ink[label] = round(float(height) * 2)
                estimated = True
        for bar in descendants:
            if bar["tag"] != "div" or "tank" not in classes(bar): continue
            style = bar["attrs"].get("style") or ""
            gradient = re.search(r"linear-gradient\((.*)\)", style, re.I|re.S)
            values = re.findall(r"(?<![\d.\-])(\d+(?:\.\d+)?)\s*%", gradient.group(1)) if gradient else []
            # Only trust an explicit shared boundary between the filled and empty stops.
            stops = [float(x) for x in values]
            boundary = stops if len(stops) == 2 else stops[1:3] if len(stops) == 4 and stops[0] == 0 and stops[3] == 100 else []
            if len(boundary) == 2 and boundary[0] == boundary[1]:
                value = boundary[0]
                if 0 <= value <= 100: ink[label] = round(value)
    return {"ink":[{"colour":c, "percent":ink[c]} for c in ("Black", "Cyan", "Magenta", "Yellow") if c in ink], "state":state,
            "connection":connection, "ink_estimated":estimated}


PRINTER_CACHE = {}
PRINTER_LOCK = threading.Lock()

def printer_status():
    with PRINTER_LOCK:
        now = time.monotonic()
        if PRINTER_CACHE and now - PRINTER_CACHE["time"] < 30:
            return PRINTER_CACHE["value"]
        result = _read_printer_status()
        result["checked_at"] = datetime.now(timezone.utc).isoformat()
        PRINTER_CACHE.update(time=time.monotonic(), value=result)
        return result


def _read_printer_status():
    host=_registry_ip("epson_et3850","10.0.0.3")
    result={"ip":host,"online":False,"model":"Epson ET-3850","state":None,
            "ink":[],"alerts":[],"ports":[],"sources":[],"detail":None}
    result["web_url"] = "https://" + host + "/PRESENTATION/HTML/TOP/PRTINFO.HTML"
    ports=[p for p in (80,443,631,9100) if _tcp_open(host,p,timeout=0.22)]
    result["ports"]=ports
    result["online"]=bool(ports)

    # IPP Get-Printer-Attributes: read-only and often gives the cleanest live state.
    if 631 in ports:
        try:
            import http.client, struct
            attrs=[
              (0x47,"attributes-charset","utf-8"),
              (0x48,"attributes-natural-language","en"),
              (0x45,"printer-uri","ipp://"+host+"/ipp/print"),
              (0x44,"requested-attributes","printer-name"),
              (0x44,"requested-attributes","printer-state"),
              (0x44,"requested-attributes","printer-state-reasons"),
              (0x44,"requested-attributes","marker-names"),
              (0x44,"requested-attributes","marker-levels"),
              (0x44,"requested-attributes","marker-colors"),
              (0x44,"requested-attributes","marker-types"),
            ]
            body=bytearray(b"\x02\x00\x00\x0b\x00\x00\x00\x01\x01")
            previous_name = None
            for tag,name,val in attrs:
                nb=("" if name == previous_name else name).encode(); vb=val.encode()
                previous_name = name
                body += bytes([tag])+struct.pack(">H",len(nb))+nb+struct.pack(">H",len(vb))+vb
            body += b"\x03"
            conn=http.client.HTTPConnection(host,631,timeout=2)
            conn.request("POST","/ipp/print",bytes(body),{"Content-Type":"application/ipp"})
            r=conn.getresponse(); raw=r.read(200000)
            result["sources"].append("IPP")
            parsed = _ipp_attributes(raw)
            result["ink"] = _ipp_ink(parsed)
            state = (parsed.get("printer-state") or [None])[0]
            result["state"] = {3:"Ready", 4:"Printing", 5:"Stopped"}.get(state)
            reasons = [x for x in parsed.get("printer-state-reasons", []) if isinstance(x, str) and x != "none"]
            result["alerts"].extend(reasons)
            result["sources"].extend(k for k in ("marker-names", "marker-levels", "marker-colors") if k in parsed)
            conn.close()
        except Exception as exc:
            result["alerts"].append("IPP: "+str(exc)[:100])

    # Epson WebConfig. Fetch both HTTP and HTTPS because firmware differs by model/version.
    import re
    pages=["/PRESENTATION/HTML/TOP/PRTINFO.HTML","/PRESENTATION/HTML/TOP/INDEX.HTML","/","/PRESENTATION/HTML/TOP/STATUS.HTML",
           "/PRESENTATION/HTML/TOP/INK.HTML","/PRESENTATION/HTML/TOP/PRTINFO.JS",
           "/cgi-bin/PrinterStatus.cgi","/cgi-bin/Status.cgi","/cgi-bin/InkLevel.cgi"]
    blobs=[]
    ctx=ssl._create_unverified_context()
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
    complete_web_read=False
    for scheme in (() if result["ink"] else ("https","http")):
        if (scheme=="http" and 80 not in ports) or (scheme=="https" and 443 not in ports):
            continue
        for path in pages:
            try:
                req=urllib.request.Request(scheme+"://"+host+path,headers={"User-Agent":"Mozilla/5.0 Eldoret"})
                with opener.open(req,timeout=2) as response:
                    body=response.read(250000).decode("utf-8",errors="replace")
                if body:
                    blobs.append((path,body))
                    if len(_epson_web_status(body)["ink"]) == 4:
                        complete_web_read=True
                        break
            except Exception:
                pass
        if complete_web_read:
            break
    colours={"black":"Black","cyan":"Cyan","magenta":"Magenta","yellow":"Yellow"}
    found={}
    for path,body in blobs:
        low=body.lower()
        web_status = _epson_web_status(body)
        if web_status["state"] and not result["state"]:
            result["state"] = web_status["state"]
        if web_status["connection"]:
            result["connection"] = web_status["connection"]
        if web_status["ink_estimated"]:
            result["ink_estimated"] = True
        for item in web_status["ink"]:
            found[item["colour"]] = item["percent"]
        if web_status["ink"]:
            result["sources"].append("Epson WebConfig ink bars")
        if "epson" in low: result["sources"].append("Epson WebConfig")
        title=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
        if title:
            clean=" ".join(re.sub(r"<[^>]+>"," ",title.group(1)).split())
            if "et-3850" in clean.lower(): result["model"]="Epson ET-3850"
        plain=" ".join(re.sub(r"<[^>]+>"," ",body).replace("&nbsp;"," ").split())
        for k,label in colours.items():
            # Epson pages vary: colour followed by a numeric percentage/value nearby.
            for pat in [
                r"(?i)\b"+k+r"\b[^0-9]{0,60}(100|[0-9]{1,2})\s*%"
            ]:
                m=re.search(pat,plain)
                if m:
                    v=int(m.group(1))
                    if 0 <= v <= 100:
                        found[label]=v; break
    if not result["ink"]:
        result["ink"]=[{"colour":x,"percent":found[x]} for x in ("Black","Cyan","Magenta","Yellow") if x in found]
    result["sources"]=list(dict.fromkeys(result["sources"]))
    if result["ink"]:
        result["detail"]="Live Epson ink levels read successfully."
    elif result["online"]:
        result["detail"]="Epson is reachable, but the current reader has not decoded ink percentages from its status feeds."
    else:
        result["detail"]="Epson did not answer."
    return result

def infrastructure_status():
    targets = [
        {"ip":"10.0.0.1","name":"Main Router","ports":[22,53,80,443,8080,8443]},
        {"ip":"10.0.0.6","name":"UniFi Office/Kitchen","ports":[22,80,443,8080,8443]},
        {"ip":"10.0.0.7","name":"UniFi Utility","ports":[22,80,443,8080,8443]},
        {"ip":"10.0.0.8","name":"UniFi Garden","ports":[22,80,443,8080,8443]},
        {"ip":"10.0.0.9","name":"UniFi Landing","ports":[22,80,443,8080,8443]},
    ]
    out = []
    ctx = ssl._create_unverified_context()
    import re
    for target in targets:
        open_ports = [p for p in target["ports"] if _tcp_open(target["ip"], p, timeout=0.35)]
        item = {"ip":target["ip"],"name":target["name"],"online":bool(open_ports),
                "ports":open_ports,"web":[]}
        for scheme, port in (("http",80),("https",443),("http",8080),("https",8443)):
            if port not in open_ports:
                continue
            try:
                url = scheme + "://" + target["ip"] + ((":" + str(port)) if port not in (80,443) else "") + "/"
                req = urllib.request.Request(url, headers={"User-Agent":"Eldoret/1.0"})
                with urllib.request.urlopen(req, timeout=2, context=ctx if scheme=="https" else None) as response:
                    body = response.read(65536).decode("utf-8", errors="replace")
                    headers = dict(response.headers.items())
                    status = getattr(response, "status", 200)
                m = re.search(r"<title[^>]*>(.*?)</title>", body, re.I|re.S)
                title = " ".join(re.sub(r"<[^>]+>"," ",m.group(1)).split())[:160] if m else None
                item["web"].append({"url":url,"status":status,"title":title,
                                    "server":headers.get("Server"),
                                    "location":headers.get("Location")})
            except Exception as exc:
                item["web"].append({"port":port,"scheme":scheme,"error":str(exc)[:160]})
        out.append(item)
    return {"targets":out,"checked_at":datetime.now(timezone.utc).isoformat(),
            "mode":"read-only fingerprint"}

def local_neighbor_table():
    # Read-only view of the Chromebook's existing kernel neighbour/ARP cache.
    # This does not contact or authenticate to any device.
    import subprocess
    wanted="70:ee:50:5b:fb:b5"
    rows=[]
    commands=[["ip","neigh","show"],["arp","-an"]]
    output=""
    used=None
    for cmd in commands:
        try:
            output=subprocess.check_output(cmd,stderr=subprocess.STDOUT,timeout=3,text=True)
            used=" ".join(cmd)
            if output: break
        except Exception:
            continue
    for line in output.splitlines():
        low=line.lower()
        if "10.0.0." in low:
            rows.append(line.strip()[:300])
    matches=[x for x in rows if wanted in x.lower()]
    return {"target_mac":wanted,"matches":matches,"neighbors":rows,
            "source":used,"checked_at":datetime.now(timezone.utc).isoformat(),
            "mode":"read-only local neighbour cache"}

def homekit_discovery(timeout=3.0):
    # Read-only mDNS browse for HomeKit accessories (_hap._tcp.local).
    result={"services":[],"checked_at":datetime.now(timezone.utc).isoformat(),"mode":"read-only HomeKit mDNS discovery"}
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM,socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        sock.settimeout(0.35)
        # DNS query: PTR _hap._tcp.local
        labels=["_hap","_tcp","local"]
        q=b"".join(bytes([len(x)])+x.encode() for x in labels)+b"\x00"
        packet=b"\x00\x00\x00\x00\x00\x01\x00\x00\x00\x00\x00\x00"+q+b"\x00\x0c\x00\x01"
        sock.sendto(packet,("224.0.0.251",5353))
        end=time.time()+timeout
        seen=set()
        while time.time()<end:
            try:
                data,addr=sock.recvfrom(8192)
                if not data: continue
                key=(addr[0],data)
                if key in seen: continue
                seen.add(key)
                # Keep only safe printable clues from the mDNS reply.
                text="".join(chr(b) if 32<=b<127 else " " for b in data)
                clean=" ".join(text.split())
                if "_hap" in clean.lower() or "velux" in clean.lower():
                    result["services"].append({"ip":addr[0],"clue":clean[:700]})
            except socket.timeout:
                continue
    finally:
        sock.close()
    return result

def velux_active_discovery():
    # VELUX ACTIVE / App Control with Netatmo uses a local pairing service on TCP 25050.
    # This is a read-only reachability search; it does not authenticate or pair.
    found=[]
    for last in range(1,255):
        ip="10.0.0."+str(last)
        if _tcp_open(ip,25050,timeout=0.045):
            found.append({"ip":ip,"port":25050,"candidate":"VELUX ACTIVE / App Control gateway"})
    return {"devices":found,"checked_at":datetime.now(timezone.utc).isoformat(),
            "mode":"read-only VELUX ACTIVE discovery"}

def lan_inventory():
    # Read-only discovery across the home /24 using only services Eldoret already knows about.
    # No authentication, login attempts or configuration changes.
    found=[]
    ports=(80,443,3000,3001,51200,8765,9100,631,49153,49160)
    for last in range(1,255):
        ip="10.0.0."+str(last)
        open_ports=[p for p in ports if _tcp_open(ip,p,timeout=0.035)]
        if not open_ports:
            continue
        kind=[]
        if 3000 in open_ports or 3001 in open_ports: kind.append("LG webOS candidate")
        if 51200 in open_ports: kind.append("VELUX KLF candidate")
        if 8765 in open_ports: kind.append("Eldoret")
        if 9100 in open_ports or 631 in open_ports: kind.append("Printer")
        if 49153 in open_ports or 49160 in open_ports: kind.append("Sky Q")
        found.append({"ip":ip,"ports":open_ports,"candidates":kind or ["Network device"]})
    return {"devices":found,"checked_at":datetime.now(timezone.utc).isoformat(),
            "mode":"read-only known-service discovery"}

# Router telemetry is read-only and restricted to the verified DrayTek LAN address.
ROUTER_SNMP_DIR = os.path.expanduser('~/eldoret-connector/router-snmp')
ROUTER_LOCK = threading.Lock()
ROUTER_STATE = {'online': False, 'message': 'Waiting for the first router reading.', 'history': []}
ROUTER_PREVIOUS = None
ROUTER_ACTIVE = False
ROUTER_LAST_REQUEST = 0

def _router_rates(previous, current, elapsed):
    if not previous or not 0 < elapsed < 25:
        return None, None
    if current['uptime_ticks'] <= previous['uptime_ticks']:
        return None, None
    # Agent time and wall time must agree; pauses/restarts invalidate a sample.
    if abs((current['uptime_ticks'] - previous['uptime_ticks']) / 100 - elapsed) > 3:
        return None, None
    if current['link_code'] != 1 or previous['link_code'] != 1:
        return None, None
    if current['last_change'] != previous['last_change'] or current['discontinuity'] != previous['discontinuity']:
        return None, None
    result = []
    for key in ('in_octets', 'out_octets'):
        old, new = previous[key], current[key]
        if new < old and not (old > 3 * 2**30 and new < 2**30):
            return None, None
        delta = (new - old) % 2**32
        mbps = delta * 8 / elapsed / 1e6
        if mbps > 1000:
            return None, None
        result.append(round(mbps, 3))
    return tuple(result)

def _router_read():
    import re
    import stat
    configured = os.path.isfile(os.path.join(ROUTER_SNMP_DIR, 'snmp.conf'))
    level = 'authPriv' if configured else 'noAuthNoPriv'
    if configured:
        config_stat = os.stat(os.path.join(ROUTER_SNMP_DIR, 'snmp.conf'))
        if config_stat.st_uid != os.getuid() or stat.S_IMODE(config_stat.st_mode) & 0o077:
            raise RuntimeError('Router credential file must be private to the Eldoret user (chmod 600).')
    # An isolated config path prevents unrelated ~/.snmp defaults affecting this probe.
    env = dict(os.environ, SNMPCONFPATH=ROUTER_SNMP_DIR, MIBS='')
    oids = ['.1.3.6.1.2.1.1.1.0', '.1.3.6.1.2.1.1.3.0',
            '.1.3.6.1.2.1.2.2.1.2.5', '.1.3.6.1.2.1.2.2.1.8.5',
            '.1.3.6.1.2.1.2.2.1.10.5', '.1.3.6.1.2.1.2.2.1.16.5',
            '.1.3.6.1.2.1.2.2.1.9.5', '.1.3.6.1.2.1.31.1.1.1.19.5']
    cmd = ['snmpget', '-v3', '-u', 'eldoret', '-l', level, '-a', 'SHA', '-x', 'AES',
           '-t', '2', '-r', '1', '-Oqv', '-Ot', '10.0.0.1'] + oids
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=10, env=env)
    except FileNotFoundError:
        raise RuntimeError('The SNMP reader is not installed on the Eldoret host.')
    except subprocess.TimeoutExpired:
        raise RuntimeError('The router did not reply in time.')
    # Never return command stderr: local configuration diagnostics may contain secrets.
    if proc.returncode:
        raise RuntimeError('Encrypted router read failed. Check the local SNMP settings.' if configured else 'The router did not answer the SNMP read.')
    lines = proc.stdout.strip().splitlines()
    if len(lines) != len(oids):
        raise RuntimeError('The router returned an incomplete reading.')
    def number(value, optional=False):
        if optional and 'No Such' in value:
            return None
        if not re.fullmatch(r'\d+', value.strip()):
            raise RuntimeError('The router returned an unsupported reading.')
        return int(value.strip())
    description = lines[0].strip('"')
    name = lines[2].strip('"')
    if 'Vigor2865' not in description or name != 'WAN2':
        raise RuntimeError('Router or WAN2 identity changed; telemetry needs checking.')
    version = re.search(r'Version:\s*([^,]+)', description)
    cpu = re.search(r'CPU Usage:\s*(\d+)%', description)
    memory = re.search(r'Memory Usage:\s*(\d+)%', description)
    return {'uptime_ticks': number(lines[1]), 'link_code': number(lines[3]),
            'in_octets': number(lines[4]), 'out_octets': number(lines[5]),
            'last_change': number(lines[6], True), 'discontinuity': number(lines[7], True),
            'firmware': version.group(1).strip() if version else None,
            'cpu_percent': int(cpu.group(1)) if cpu and int(cpu.group(1)) <= 100 else None,
            'memory_percent': int(memory.group(1)) if memory and int(memory.group(1)) <= 100 else None,
            'security': level}

def _router_loop():
    global ROUTER_PREVIOUS, ROUTER_ACTIVE
    while True:
        start = time.monotonic()
        with ROUTER_LOCK:
            if start - ROUTER_LAST_REQUEST > 120:
                ROUTER_ACTIVE = False
                ROUTER_PREVIOUS = None
                return
        stamp = datetime.now(timezone.utc).isoformat()
        try:
            reading = _router_read()
            now = time.monotonic()
            previous = ROUTER_PREVIOUS
            down, up = _router_rates(previous[1] if previous else None, reading,
                                      now - previous[0] if previous else 0)
            ROUTER_PREVIOUS = (now, reading)
            data = {'online': True, 'checked_at': stamp, 'ip': '10.0.0.1',
                    'interface': 'WAN2', 'link_up': reading['link_code'] == 1,
                    'download_mbps': down, 'upload_mbps': up,
                    'uptime_seconds': reading['uptime_ticks'] / 100,
                    'cpu_percent': reading['cpu_percent'], 'memory_percent': reading['memory_percent'],
                    'firmware': reading['firmware'], 'security': reading['security'],
                    'message': 'Live WAN2 traffic' if down is not None else 'Connected. Collecting the next traffic sample.'}
        except Exception as exc:
            ROUTER_PREVIOUS = None
            message = str(exc) if isinstance(exc, RuntimeError) else 'Router reading unavailable.'
            data = {'online': False, 'checked_at': stamp, 'message': message,
                    'download_mbps': None, 'upload_mbps': None}
        with ROUTER_LOCK:
            history = ROUTER_STATE.get('history', [])[-59:]
            history.append({'at': stamp, 'download': data['download_mbps'], 'upload': data['upload_mbps']})
            ROUTER_STATE.clear()
            ROUTER_STATE.update(data, history=history)
        time.sleep(max(0.1, 5 - (time.monotonic() - start)))

def configure_router_snmp():
    """Prompt locally, test encrypted access, and save only working credentials."""
    import getpass
    import tempfile
    from pathlib import Path
    global ROUTER_SNMP_DIR
    def quote(value):
        if any(c in value for c in '\r\n\x00'):
            raise ValueError('Use passphrases without line breaks.')
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'
    auth = getpass.getpass('Router SNMP Auth Password: ')
    privacy = getpass.getpass('Router SNMP Privacy Password: ')
    if not auth or not privacy:
        raise ValueError('Both SNMP passwords are required.')
    content = 'defAuthPassphrase ' + quote(auth) + '\n' + 'defPrivPassphrase ' + quote(privacy) + '\n'
    target = Path(ROUTER_SNMP_DIR)
    original = ROUTER_SNMP_DIR
    with tempfile.TemporaryDirectory(prefix='eldoret-snmp-') as folder:
        config = Path(folder) / 'snmp.conf'
        config.touch(mode=0o600)
        config.write_text(content)
        try:
            ROUTER_SNMP_DIR = folder
            _router_read()
        finally:
            ROUTER_SNMP_DIR = original
    target.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target, 0o700)
    fd, filename = tempfile.mkstemp(prefix='.snmp-', dir=str(target))
    try:
        with os.fdopen(fd, 'w') as f:
            f.write(content)
        os.replace(filename, target / 'snmp.conf')
    finally:
        if os.path.exists(filename):
            os.unlink(filename)
    print('Encrypted SNMP verified. Credentials saved locally with owner-only access.')
    print('The Network dashboard will use them on its next reading; no restart needed.')

def router_status():
    global ROUTER_LAST_REQUEST, ROUTER_ACTIVE
    with ROUTER_LOCK:
        ROUTER_LAST_REQUEST = time.monotonic()
        if not ROUTER_ACTIVE:
            ROUTER_ACTIVE = True
            ROUTER_STATE.update(online=False, message='Connecting to the router.', download_mbps=None, upload_mbps=None)
            threading.Thread(target=_router_loop, daemon=True).start()
        return dict(ROUTER_STATE)

NETWORK_STATUS_CACHE = {"time":0,"data":None}

def _probe_network_device(d):
    def check(port):
        return port if _tcp_open(d["ip"], port, timeout=0.18) else None
    open_ports=[]
    with ThreadPoolExecutor(max_workers=max(1,len(d["ports"]))) as pool:
        for value in pool.map(check, d["ports"]):
            if value is not None:
                open_ports.append(value)
    ps = playstation_status(d["ip"]) if d["ip"] == "10.0.0.48" else None
    online = bool(open_ports) or bool(ps and ps.get("online"))
    detail = ("Open ports: " + ", ".join(map(str, open_ports))) if open_ports else "No configured service answered"
    if ps and ps.get("online"):
        detail = ps.get("detail") or "PlayStation detected"
        extras = [ps.get("host_type"), ps.get("host_name"), ps.get("running_app_name")]
        extras = [str(x) for x in extras if x]
        if extras:
            detail += " · " + " · ".join(extras)
    item = {"ip": d["ip"], "name": d["name"], "online": online, "ports": sorted(open_ports), "detail": detail}
    if ps:
        item["playstation"] = ps
    return item

UNIFI_CONFIG_FILE = os.path.expanduser('~/eldoret-connector/unifi/config.json')
UNIFI_LOCK = threading.Lock()
UNIFI_CACHE = {}
UNIFI_CLIENT = None
UNIFI_LAST_GOOD = None


def _unifi_config():
    import stat
    try:
        info = os.stat(UNIFI_CONFIG_FILE)
    except FileNotFoundError:
        return None
    if stat.S_IMODE(info.st_mode) & 0o077 or info.st_uid != os.getuid():
        raise ValueError('UniFi configuration must be owned by you with mode 600.')
    with open(UNIFI_CONFIG_FILE, encoding='utf-8') as file:
        return json.load(file)


def _unifi_address(url):
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.path not in ('', '/') or parsed.query or parsed.fragment:
        raise ValueError('Enter the HTTPS controller address only, including its port.')
    return parsed.hostname, parsed.port or 443


class _UniFiClient:
    """Standalone Network Server API; pin TLS before transmitting credentials."""
    def __init__(self, config):
        self.config = config
        self.host, self.port = _unifi_address(config['url'])
        self.cookies = {}

    def request(self, path, body=None):
        import http.client
        from http.cookies import SimpleCookie
        connection = http.client.HTTPSConnection(self.host, self.port, timeout=5, context=ssl._create_unverified_context())
        try:
            connection.connect()
            fingerprint = hashlib.sha256(connection.sock.getpeercert(binary_form=True)).hexdigest()
            if not secrets.compare_digest(fingerprint, self.config['certificate_sha256']):
                raise ValueError('UniFi certificate changed. Verify the controller and rerun local setup.')
            headers = {'Accept': 'application/json', 'Content-Type': 'application/json'}
            if self.cookies:
                headers['Cookie'] = '; '.join(key + '=' + value for key, value in self.cookies.items())
            connection.request('POST' if body is not None else 'GET', path,
                               json.dumps(body).encode() if body is not None else None, headers)
            response = connection.getresponse()
            for key, value in response.getheaders():
                if key.lower() == 'set-cookie':
                    cookie = SimpleCookie(); cookie.load(value)
                    self.cookies.update({name: morsel.value for name, morsel in cookie.items()})
            if response.status in (401, 403):
                raise PermissionError('UniFi rejected the local login or view permissions.')
            if response.status != 200:
                raise RuntimeError('UniFi returned HTTP ' + str(response.status) + '.')
            raw = response.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise RuntimeError('UniFi response is too large.')
            payload = json.loads(raw)
            if not isinstance(payload, dict):
                raise RuntimeError('Unexpected UniFi response.')
            if payload.get('meta', {}).get('rc') != 'ok':
                if 'login' in str(payload.get('meta', {}).get('msg', '')).lower():
                    raise PermissionError('UniFi session expired.')
                raise RuntimeError('UniFi could not complete the read.')
            return payload.get('data', [])
        finally:
            connection.close()

    def devices(self):
        site = urllib.parse.quote(self.config.get('site', 'default'), safe='')
        path = '/api/s/' + site + '/stat/device'
        if self.cookies:
            try:
                data = self.request(path)
            except PermissionError:
                self.cookies.clear()
        if not self.cookies:
            self.request('/api/login', {'username': self.config['username'], 'password': self.config['password'], 'remember': False})
            data = self.request(path)
        if not isinstance(data, list) or any(not isinstance(row, dict) for row in data):
            raise RuntimeError('Unexpected UniFi device list.')
        return data


def _unifi_devices(rows):
    import math
    def number(value, maximum=None):
        if isinstance(value, bool): return None
        try:
            result = float(value)
        except (ValueError, TypeError):
            return None
        return result if math.isfinite(result) and result >= 0 and (maximum is None or result <= maximum) else None
    devices = []
    for row in rows:
        if row.get('type') != 'uap': continue
        stats = row.get('system-stats') or {}
        online = row.get('state') == 1 and row.get('disabled') is not True
        devices.append({
            'name': row.get('name') or row.get('model') or 'Access point',
            'model': row.get('model'), 'online': online,
            'state': 'disabled' if row.get('disabled') else ('connected' if online else 'not_connected'),
            'clients': number(row.get('num_sta')) if online else None,
            'cpu_percent': number(stats.get('cpu'), 100) if online else None,
            'memory_percent': number(stats.get('mem'), 100) if online else None,
            'uptime_seconds': number(row.get('uptime', stats.get('uptime'))) if online else None,
            'firmware': row.get('version') if online else None,
        })
    return sorted(devices, key=lambda row: str(row['name']).casefold())



# Lightweight direct access-point monitoring. Credentials remain ONLY in Bulldog's
# owner-readable unifi/snmp.conf; the public GitHub repository never stores them.
UNIFI_SNMP_APS = (
    ("10.0.0.6", "Office / Kitchen"),
    ("10.0.0.7", "Utility"),
    ("10.0.0.8", "Garden"),
    ("10.0.0.9", "Landing"),
)
UNIFI_SNMP_PRIVATE = os.path.expanduser("~/eldoret-connector/unifi/snmp.conf")
UNIFI_SNMP_HISTORY = os.path.expanduser("~/eldoret-connector/unifi/direct-history.json")
UNIFI_SNMP_CACHE = {"expires": 0, "data": None, "previous": {}, "last_save": 0}
UNIFI_SNMP_LOCK = threading.Lock()
UNIFI_CLIENT_COUNT_CACHE = {}  # per-AP SNMP results, refreshed at most once per 90s
UNIFI_SNMP_OIDS = (
    "1.3.6.1.2.1.1.1.0",          # sysDescr
    "1.3.6.1.2.1.1.5.0",          # sysName
    "1.3.6.1.2.1.1.3.0",          # sysUpTime
    "1.3.6.1.2.1.31.1.1.1.1.2",  # ifName.2; verify it really is eth0
    "1.3.6.1.2.1.31.1.1.1.6.2",  # ifHCInOctets.2
    "1.3.6.1.2.1.31.1.1.1.10.2", # ifHCOutOctets.2
)

def _unifi_snmp_enabled():
    import stat
    try:
        s = os.stat(UNIFI_SNMP_PRIVATE)
        parent = os.stat(os.path.dirname(UNIFI_SNMP_PRIVATE))
        return (s.st_uid == os.getuid() and stat.S_ISREG(s.st_mode)
                and stat.S_IMODE(s.st_mode) & 0o077 == 0
                and parent.st_uid == os.getuid()
                and stat.S_IMODE(parent.st_mode) & 0o077 == 0)
    except OSError:
        return False

def _unifi_snmp_probe(ap):
    ip, label = ap
    item = {"ip": ip, "name": label, "model": None, "firmware": None,
            "online": False, "snmp_online": False, "latency_ms": None,
            "uptime_seconds": None, "rx_mbps": None, "tx_mbps": None,
            "clients": None, "source": "snmpv3"}
    # Keep credentials out of process arguments, command output and repository.
    env = dict(os.environ)
    env["SNMPCONFPATH"] = os.path.dirname(UNIFI_SNMP_PRIVATE)
    try:
        proc = subprocess.run(
            ["snmpget", "-m", "", "-v3", "-l", "authPriv", "-u", "eldoret-monitor",
             "-a", "SHA", "-x", "AES", "-On", "-t", "2", "-r", "0", ip,
             *UNIFI_SNMP_OIDS],
            capture_output=True, text=True, timeout=5, env=env, check=False)
        if proc.returncode == 0:
            values = {}
            for line in proc.stdout.splitlines():
                if " = " in line:
                    oid, value = line.split(" = ", 1)
                    values[oid.lstrip(".")] = value.strip()
            def read(oid):
                return values.get(oid, "")
            def digits(value, token):
                import re
                match = re.search(r"\b" + token + r":\s*(\d+)", value)
                return int(match.group(1)) if match else None
            descr = read(UNIFI_SNMP_OIDS[0])
            name = read(UNIFI_SNMP_OIDS[1])
            up = read(UNIFI_SNMP_OIDS[2])
            iface = read(UNIFI_SNMP_OIDS[3])
            if up.startswith("Timeticks:"):
                import re
                match = re.search(r"\((\d+)\)", up)
                item["uptime_seconds"] = int(match.group(1)) / 100 if match else None
            if descr.startswith("STRING:"):
                raw = descr.split(":", 1)[1].strip().strip('"')
                bits = raw.rsplit(" ", 1)
                item["model"] = bits[0][:80]
                item["firmware"] = (bits[1] if len(bits) > 1 else None)
            if name.startswith("STRING:"):
                item["device_name"] = name.split(":", 1)[1].strip().strip('"')[:80]
            item["online"] = item["snmp_online"] = True
            if iface.startswith("STRING:") and iface.split(":", 1)[1].strip().strip('"') == "eth0":
                item["rx_octets"] = digits(read(UNIFI_SNMP_OIDS[4]), "Counter64")
                item["tx_octets"] = digits(read(UNIFI_SNMP_OIDS[5]), "Counter64")
                item["traffic_interface"] = "eth0"
            else:
                item["traffic_note"] = "Ethernet interface index differs; traffic not reported."
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    try:
        ping = subprocess.run(["ping", "-n", "-c", "1", "-W", "1", ip],
                              capture_output=True, text=True, timeout=3, check=False)
        if ping.returncode == 0:
            import re
            match = re.search(r"\btime=([\d.]+)\s*ms", ping.stdout)
            item["latency_ms"] = round(float(match.group(1)), 1) if match else None
            item["online"] = True
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return item


def unifi_client_count_pilot():
    """Read-only, one-AP test of UniFi vAP client counts; no controller or Mac required."""
    import re
    import shutil
    result = {"ap": "Office / Kitchen", "ip": "10.0.0.6",
              "source": "direct_snmpv3", "clients": None,
              "status": "unavailable",
              "checked_at": datetime.now(timezone.utc).isoformat()}
    if not _unifi_snmp_enabled():
        result["reason"] = "Bulldog direct SNMP credentials are not configured"
        return result
    if not shutil.which("snmpwalk"):
        result["reason"] = "snmpwalk is not installed on Bulldog"
        return result
    env = dict(os.environ)
    env["SNMPCONFPATH"] = os.path.dirname(UNIFI_SNMP_PRIVATE)
    base = "1.3.6.1.4.1.41112.1.6.1.2.1.8"
    try:
        proc = subprocess.run(
            ["snmpwalk", "-m", "", "-v3", "-l", "authPriv",
             "-u", "eldoret-monitor", "-a", "SHA", "-x", "AES",
             "-On", "-t", "2", "-r", "0", "10.0.0.6", base],
            capture_output=True, text=True, timeout=6, env=env, check=False)
        if proc.returncode != 0:
            result["reason"] = "SNMP vAP walk returned no successful response"
            return result
        readings = []
        for line in proc.stdout.splitlines():
            oid, sep, raw = line.strip().partition(" = ")
            oid = oid.lstrip(".")
            if sep and oid.startswith(base + ".") and raw.startswith("INTEGER:"):
                try:
                    value = int(raw.split(":", 1)[1].strip())
                    if value >= 0:
                        readings.append(value)
                except ValueError:
                    pass
        if not readings:
            result["reason"] = "This AP did not expose vAP station counts"
            return result
        result.update(status="ok", clients=sum(readings),
                      virtual_ap_count=len(readings))
    except (OSError, subprocess.TimeoutExpired, ValueError):
        result["reason"] = "SNMP client-count probe timed out or failed"
    return result


def _unifi_snmp_station_count(ip):
    """Read direct wireless station counts, retaining no unique device identities."""
    import shutil
    if not shutil.which("snmpwalk"):
        return None
    base = "1.3.6.1.4.1.41112.1.6.1.2.1.8"  # unifiVapNumStations
    env = dict(os.environ)
    env["SNMPCONFPATH"] = os.path.dirname(UNIFI_SNMP_PRIVATE)
    try:
        proc = subprocess.run(
            ["snmpwalk", "-m", "", "-v3", "-l", "authPriv",
             "-u", "eldoret-monitor", "-a", "SHA", "-x", "AES",
             "-On", "-t", "2", "-r", "0", ip, base],
            capture_output=True, text=True, timeout=6, env=env, check=False)
        if proc.returncode != 0:
            return None
        values = []
        for line in proc.stdout.splitlines():
            oid, sep, raw = line.strip().partition(" = ")
            if sep and oid.lstrip(".").startswith(base + ".") and raw.startswith("INTEGER:"):
                try:
                    count = int(raw.split(":", 1)[1].strip())
                    if count >= 0:
                        values.append(count)
                except ValueError:
                    pass
        if not values:
            return None
        return {"clients": sum(values), "virtual_ap_count": len(values)}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def _unifi_snmp_status():
    with UNIFI_SNMP_LOCK:
        now = time.monotonic()
        if UNIFI_SNMP_CACHE["data"] is not None and now < UNIFI_SNMP_CACHE["expires"]:
            return UNIFI_SNMP_CACHE["data"]
        with ThreadPoolExecutor(max_workers=4) as pool:
            devices = list(pool.map(_unifi_snmp_probe, UNIFI_SNMP_APS))
        checked = datetime.now(timezone.utc).isoformat()
        # Station counts are read directly from the APs, independently of UniFi on Mac.
        # Cached for 90s to reduce CPU/network load on the Pi 3.
        count_now = time.monotonic()
        due = [d for d in devices if d["snmp_online"] and
               count_now >= UNIFI_CLIENT_COUNT_CACHE.get(d["ip"], {}).get("expires", 0)]
        if due:
            with ThreadPoolExecutor(max_workers=4) as pool:
                counts = list(pool.map(_unifi_snmp_station_count, [d["ip"] for d in due]))
            for d, count in zip(due, counts):
                UNIFI_CLIENT_COUNT_CACHE[d["ip"]] = {
                    "expires": time.monotonic() + 90,
                    "checked_at": checked,
                    "data": count
                }
        for d in devices:
            cached = UNIFI_CLIENT_COUNT_CACHE.get(d["ip"], {})
            count = cached.get("data") if d["snmp_online"] else None
            if count is not None:
                d.update(clients=count["clients"],
                         virtual_ap_count=count["virtual_ap_count"],
                         clients_checked_at=cached.get("checked_at"))
        previous = UNIFI_SNMP_CACHE["previous"]
        for device in devices:
            prior = previous.get(device["ip"])
            rx, tx = device.pop("rx_octets", None), device.pop("tx_octets", None)
            if (prior and rx is not None and tx is not None
                and prior["rx"] is not None and prior["tx"] is not None
                and rx >= prior["rx"] and tx >= prior["tx"]
                and 0 < now - prior["at"] < 180):
                elapsed = now - prior["at"]
                device["rx_mbps"] = round((rx - prior["rx"]) * 8 / elapsed / 1000000, 2)
                device["tx_mbps"] = round((tx - prior["tx"]) * 8 / elapsed / 1000000, 2)
            if rx is not None and tx is not None:
                previous[device["ip"]] = {"rx": rx, "tx": tx, "at": now}
            elif not device["snmp_online"]:
                previous.pop(device["ip"], None)
        # Persist a bounded 7-day, five-minute history, plus immediate state changes.
        history = {"samples": [], "events": []}
        try:
            with open(UNIFI_SNMP_HISTORY, encoding="utf-8") as stream:
                saved = json.load(stream)
            if isinstance(saved, dict):
                history = {"samples": saved.get("samples", [])[-2016:],
                           "events": saved.get("events", [])[-200:]}
        except (OSError, ValueError, TypeError):
            pass
        states = {d["ip"]: d["online"] for d in devices}
        old_states = history["samples"][-1]["states"] if history["samples"] else {}
        changes = [d for d in devices if d["ip"] in old_states
                   and bool(old_states[d["ip"]]) != d["online"]]
        should_save = bool(changes) or now - UNIFI_SNMP_CACHE["last_save"] > 300 or not history["samples"]
        if should_save:
            for d in changes:
                history["events"].append({"at": checked, "ip": d["ip"], "name": d["name"],
                                          "state": "restored" if d["online"] else "unreachable"})
            history["events"] = history["events"][-200:]
            history["samples"].append({"at": checked, "states": states,
                "rates": {d["ip"]: {"rx": d["rx_mbps"], "tx": d["tx_mbps"]} for d in devices}})
            history["samples"] = history["samples"][-2016:]
            try:
                path = UNIFI_SNMP_HISTORY + ".new"
                with open(path, "w", encoding="utf-8") as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    json.dump(history, stream, separators=(",", ":"))
                os.replace(path, UNIFI_SNMP_HISTORY)
                UNIFI_SNMP_CACHE["last_save"] = now
            except OSError:
                pass
        payload = {"configured": True, "source": "direct_snmp",
                   "controller_online": False, "direct_online": any(d["snmp_online"] for d in devices),
                   "devices": devices, "checked_at": checked, "last_seen_at": checked,
                   "events": history["events"][-12:],
                   "message": "Direct encrypted monitoring from Bulldog; UniFi server not required."}
        UNIFI_SNMP_CACHE.update(data=payload, expires=time.monotonic() + 20)
        return payload


# Lightweight on-device health snapshot for Bulldog. No secrets or remote execution.
BULLDOG_LOCK = threading.Lock()
BULLDOG_CPU_PREVIOUS = None
def bulldog_status():
    global BULLDOG_CPU_PREVIOUS
    import shutil
    import re
    from pathlib import Path
    from datetime import datetime, timezone
    result = {"name": "Bulldog", "checked_at": datetime.now(timezone.utc).isoformat()}
    def read(path):
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    result["hostname"] = socket.gethostname()
    result["python"] = platform.python_version()
    result["kernel"] = platform.release()
    result["architecture"] = platform.machine()
    result["os"] = "Raspberry Pi OS"
    model = read("/proc/device-tree/model").replace("\x00", "")
    result["model"] = model or "Raspberry Pi"
    try:
        result["uptime_seconds"] = int(float(read("/proc/uptime").split()[0]))
    except (ValueError, IndexError):
        result["uptime_seconds"] = None
    try:
        result["load_1m"], result["load_5m"], result["load_15m"] = [round(x, 2) for x in os.getloadavg()]
    except OSError:
        result["load_1m"] = result["load_5m"] = result["load_15m"] = None
    result["logical_cpus"] = os.cpu_count()
    try:
        with open("/proc/stat", encoding="ascii") as fp:
            parts = [int(x) for x in fp.readline().split()[1:]]
        total, idle = sum(parts), parts[3] + (parts[4] if len(parts) > 4 else 0)
        with BULLDOG_LOCK:
            previous = BULLDOG_CPU_PREVIOUS
            BULLDOG_CPU_PREVIOUS = (total, idle)
        if previous is not None and total > previous[0]:
            result["cpu_percent"] = round(100 * max(0, min(1, 1 - (idle - previous[1]) / (total - previous[0]))), 1)
        else:
            result["cpu_percent"] = None
    except (OSError, ValueError, IndexError, ZeroDivisionError):
        result["cpu_percent"] = None
    mem = {}
    for line in read("/proc/meminfo").splitlines():
        if ":" in line:
            key, val = line.split(":", 1)
            try:
                mem[key] = int(val.strip().split()[0]) * 1024
            except (ValueError, IndexError):
                pass
    total = mem.get("MemTotal", 0)
    available = mem.get("MemAvailable", 0)
    result["memory_total_bytes"] = total or None
    result["memory_used_bytes"] = max(0, total - available) if total else None
    result["memory_percent"] = round(100 * (total - available) / total, 1) if total else None
    result["swap_used_bytes"] = max(0, mem.get("SwapTotal", 0) - mem.get("SwapFree", 0))
    result["swap_total_bytes"] = mem.get("SwapTotal", 0)
    try:
        disk = shutil.disk_usage("/")
        result["disk_total_bytes"] = disk.total
        result["disk_used_bytes"] = disk.used
        result["disk_percent"] = round(100 * disk.used / disk.total, 1)
    except OSError:
        result["disk_total_bytes"] = result["disk_used_bytes"] = result["disk_percent"] = None
    try:
        result["temperature_c"] = round(int(read("/sys/class/thermal/thermal_zone0/temp")) / 1000, 1)
    except ValueError:
        result["temperature_c"] = None
    result["wifi_connected"] = Path("/sys/class/net/wlan0/carrier").exists() and read("/sys/class/net/wlan0/carrier") == "1"
    result["ethernet_connected"] = read("/sys/class/net/eth0/carrier") == "1"
    try:
        result["ip_addresses"] = [a for a in socket.gethostbyname_ex(socket.gethostname())[2] if a.startswith("10.") or a.startswith("192.168.") or a.startswith("172.")]
    except OSError:
        result["ip_addresses"] = []
    result["eldoret_running"] = True  # The API response itself is proof the connector process is alive.
    try:
        result["boot_id"] = read("/proc/sys/kernel/random/boot_id")[:8]
    except OSError:
        result["boot_id"] = ""
    return result

# Bounded 24-hour sampling continues even when nobody has the dashboard open.
BULLDOG_HISTORY_FILE = os.path.expanduser("~/eldoret-connector/bulldog-health-history.json")
BULLDOG_HISTORY_LOCK = threading.Lock()
BULLDOG_HISTORY = []
def _bulldog_history_load():
    global BULLDOG_HISTORY
    try:
        with open(BULLDOG_HISTORY_FILE, encoding="utf-8") as stream:
            data = json.load(stream)
        if isinstance(data, list):
            BULLDOG_HISTORY = [row for row in data[-1440:] if isinstance(row, dict)]
    except (OSError, ValueError):
        BULLDOG_HISTORY = []

def _bulldog_history_loop():
    _bulldog_history_load()
    while True:
        try:
            snapshot = bulldog_status()
            row = {k: snapshot.get(k) for k in ("checked_at", "cpu_percent",
                "temperature_c", "memory_percent", "disk_percent", "load_1m")}
            with BULLDOG_HISTORY_LOCK:
                BULLDOG_HISTORY.append(row)
                del BULLDOG_HISTORY[:-1440]
                if len(BULLDOG_HISTORY) % 5 == 0:
                    new = BULLDOG_HISTORY_FILE + ".new"
                    with open(new, "w", encoding="utf-8") as stream:
                        os.fchmod(stream.fileno(), 0o600)
                        json.dump(BULLDOG_HISTORY, stream, separators=(",", ":"))
                    os.replace(new, BULLDOG_HISTORY_FILE)
        except Exception:
            pass
        time.sleep(60)

def bulldog_health():
    status = bulldog_status()
    concerns = []
    temp = status.get("temperature_c")
    mem = status.get("memory_percent")
    disk = status.get("disk_percent")
    if isinstance(temp, (int, float)) and temp >= 80:
        concerns.append("CPU temperature high")
    elif isinstance(temp, (int, float)) and temp >= 70:
        concerns.append("CPU running warm")
    if isinstance(mem, (int, float)) and mem >= 90:
        concerns.append("Memory almost full")
    elif isinstance(mem, (int, float)) and mem >= 80:
        concerns.append("Memory use elevated")
    if isinstance(disk, (int, float)) and disk >= 90:
        concerns.append("Storage almost full")
    elif isinstance(disk, (int, float)) and disk >= 80:
        concerns.append("Storage use elevated")
    status["health"] = "warning" if concerns else "good"
    status["health_messages"] = concerns
    with BULLDOG_HISTORY_LOCK:
        status["history"] = list(BULLDOG_HISTORY[-1440:])
    return status


# Home Connect: read-only, bounded API; credentials and tokens remain on Bulldog.
HOME_CONNECT_LOCK = threading.Lock()
HOME_CONNECT_CACHE = {"expires":0,"data":None}
# A single bounded snapshot every 2 hours; changes between snapshots arrive via SSE.
HOME_CONNECT_SNAPSHOT_INTERVAL = 7200
HOME_CONNECT_LAST_GOOD_FILE = os.path.expanduser("~/.config/eldoret/home-connect-last-good.json")
HOME_CONNECT_COOLDOWN_FILE = os.path.expanduser("~/.config/eldoret/home-connect-cooldown.json")
# On HTTP 429, honour Retry-After, with a conservative one-hour fallback.
HOME_CONNECT_RATE_LIMIT_UNTIL = 0
HOME_CONNECT_CONFIG = os.path.expanduser("~/.config/home-connect.json")
HOME_CONNECT_TOKENS = os.path.expanduser("~/.config/home-connect-tokens.json")
HOME_CONNECT_ACCEPT = "application/vnd.bsh.sdk.v1+json"
HOME_CONNECT_BASE = "https://api.home-connect.com/api"
HOME_CONNECT_TOKEN_URL = "https://api.home-connect.com/security/oauth/token"
HOME_CONNECT_DETAILS_CACHE = {}
HOME_CONNECT_DEVICE_IDS = {}
HOME_CONNECT_EVENTS_FILE = os.path.expanduser("~/eldoret-connector/home-connect-activity.json")
HOME_CONNECT_EVENTS = []
HOME_CONNECT_LAST_STATES = {}


def _hc_read_private(path):
    import stat
    st=os.stat(path)
    if st.st_uid != os.getuid() or (stat.S_IMODE(st.st_mode) & 0o077):
        raise PermissionError("Private Home Connect configuration permissions are unsafe")
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)

def _hc_write_private(path, value):
    target=path+".new"
    fd=os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as stream:
        json.dump(value, stream)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(target,path)
    os.chmod(path,0o600)

def _hc_token():
    config=_hc_read_private(HOME_CONNECT_CONFIG)
    tokens=_hc_read_private(HOME_CONNECT_TOKENS)
    expires=int(tokens.get("obtained_at",0))+int(tokens.get("expires_in",0))
    if tokens.get("access_token") and time.time() < expires-300:
        return tokens["access_token"]
    refresh=tokens.get("refresh_token")
    if not refresh:
        raise RuntimeError("Home Connect authorisation has expired; refresh token missing")
    payload=urllib.parse.urlencode({
        "grant_type":"refresh_token", "refresh_token":refresh,
        "client_id":config["client_id"],"client_secret":config["client_secret"]
    }).encode()
    req=urllib.request.Request(HOME_CONNECT_TOKEN_URL,data=payload,
        headers={"Content-Type":"application/x-www-form-urlencoded","Accept":"application/json"},
        method="POST")
    if _hc_cooldown_seconds()>0:
        raise RuntimeError("Home Connect appliance list HTTP 429")
    try:
        with urllib.request.urlopen(req,timeout=15) as response:
            new=json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code==429:
            _hc_set_cooldown(_hc_retry_after(exc))
        raise RuntimeError("Home Connect appliance list HTTP "+str(exc.code)) from None
    if not new.get("access_token"):
        raise RuntimeError("Home Connect did not return an access token")
    # Some refresh responses omit refresh_token; preserve the previous one.
    if not new.get("refresh_token"):
        new["refresh_token"]=refresh
    new["obtained_at"]=int(time.time())
    _hc_write_private(HOME_CONNECT_TOKENS,new)
    return new["access_token"]


def _hc_private_snapshot_write(path,payload):
    """Write only safe appliance telemetry/cooldown values; never store IDs or credentials."""
    try:
        folder=os.path.dirname(path)
        os.makedirs(folder,mode=0o700,exist_ok=True)
        os.chmod(folder,0o700)
        target=path+".new"
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            json.dump(payload,stream,separators=(",",":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(target,path)
        os.chmod(path,0o600)
    except (OSError,ValueError,TypeError):
        pass

def _hc_private_snapshot_read(path):
    try:
        value=_hc_read_private(path)
        return value if isinstance(value,dict) else None
    except (OSError,ValueError,TypeError):
        return None

def _hc_retry_after(exc):
    from email.utils import parsedate_to_datetime
    value=exc.headers.get("Retry-After","") if exc.headers else ""
    try:
        return max(60,int(value))
    except (ValueError,TypeError):
        try:
            return max(60,int(parsedate_to_datetime(value).timestamp()-time.time()))
        except (ValueError,TypeError,OverflowError):
            return 3600

def _hc_set_cooldown(seconds=3600):
    global HOME_CONNECT_RATE_LIMIT_UNTIL
    HOME_CONNECT_RATE_LIMIT_UNTIL=max(HOME_CONNECT_RATE_LIMIT_UNTIL,time.monotonic()+seconds)
    _hc_private_snapshot_write(HOME_CONNECT_COOLDOWN_FILE,
        {"retry_after_epoch":time.time()+max(0,HOME_CONNECT_RATE_LIMIT_UNTIL-time.monotonic())})

def _hc_cooldown_seconds():
    global HOME_CONNECT_RATE_LIMIT_UNTIL
    saved=_hc_private_snapshot_read(HOME_CONNECT_COOLDOWN_FILE)
    if saved and isinstance(saved.get("retry_after_epoch"),(int,float)):
        wait=max(0,saved["retry_after_epoch"]-time.time())
        if wait>0:
            HOME_CONNECT_RATE_LIMIT_UNTIL=max(HOME_CONNECT_RATE_LIMIT_UNTIL,time.monotonic()+wait)
    return max(0,int(HOME_CONNECT_RATE_LIMIT_UNTIL-time.monotonic()))

def _hc_safe_snapshot(devices,checked_at):
    """Only local display fields. Avoid remote account IDs, device IDs and secrets."""
    keys=("name","brand","model","type","connected","status","active_program",
          "program_options","remaining_updated_at")
    safe=[]
    for d in devices[:16]:
        if not isinstance(d,dict):continue
        safe.append({k:d.get(k) for k in keys if k in d})
    return {"devices":safe,"checked_at":checked_at}

def _hc_get(token, endpoint):
    from urllib.error import HTTPError
    global HOME_CONNECT_RATE_LIMIT_UNTIL
    # A request during the cooldown must never hit Home Connect.
    if _hc_cooldown_seconds()>0:
        return {},429
    req=urllib.request.Request(HOME_CONNECT_BASE+endpoint,headers={
        "Authorization":"Bearer "+token, "Accept":HOME_CONNECT_ACCEPT})
    try:
        with urllib.request.urlopen(req,timeout=12) as response:
            return json.load(response).get("data",{}),None
    except HTTPError as exc:
        if exc.code==429:
            _hc_set_cooldown(_hc_retry_after(exc))
        # 404 is normal when no active programme is available.
        return {},exc.code

def home_connect_status():
    """Low-volume Home Connect snapshot with persistent last-good fallback.

    Browser refreshes read a local cache. SSE delivers mid-cycle updates. A 429
    is respected across restarts; never request more during the cooldown.
    """
    with HOME_CONNECT_LOCK:
        now=time.monotonic()
        remaining=_hc_cooldown_seconds()
        if HOME_CONNECT_CACHE["data"] is not None and now<HOME_CONNECT_CACHE["expires"]:
            cached=HOME_CONNECT_CACHE["data"]
            if remaining and not cached.get("stale"):
                return dict(cached,stale=True,error_code="cloud_http_429",
                    error="Home Connect API rate limit; showing last-known readings",
                    retry_after_seconds=remaining)
            if remaining and cached.get("stale"):
                return dict(cached,retry_after_seconds=remaining)
            return cached
        checked=datetime.now(timezone.utc).isoformat()
        result={"configured":False,"source":"Home Connect cloud","devices":[],
                "checked_at":checked,"stale":False}
        previous=_hc_private_snapshot_read(HOME_CONNECT_LAST_GOOD_FILE)
        if previous and not isinstance(previous.get("devices"),list):
            previous=None
        if remaining:
            result.update(configured=True,stale=True,error_code="cloud_http_429",
                error="Home Connect API rate limit; showing last-known readings",
                retry_after_seconds=remaining)
        else:
            try:
                token=_hc_token()
                result["configured"]=True
                listing,error=_hc_get(token,"/homeappliances")
                if error:
                    raise RuntimeError("Home Connect appliance list HTTP "+str(error))
                all_devices=listing.get("homeappliances",[])
                if not isinstance(all_devices,list):
                    raise RuntimeError("Unexpected Home Connect response")
                # Limit read calls: one appliance-list request every two hours,
                # then one status and one active-program request per connected device.
                # SSE handles events between snapshots; no browser-driven cloud reads.
                def probe(ap):
                    aid=ap.get("haId","")
                    item={"name":ap.get("name","Appliance"),"brand":ap.get("brand"),
                          "model":ap.get("vib"),"type":ap.get("type"),
                          "connected":ap.get("connected",False),"status":{},
                          "active_program":None,"program_options":[]}
                    if not aid or not item["connected"]:
                        return item
                    endpoint="/homeappliances/"+urllib.parse.quote(aid,safe="")
                    details,err=_hc_get(token,endpoint+"/status")
                    if err==429:
                        raise RuntimeError("Home Connect appliance list HTTP 429")
                    if not err and isinstance(details.get("status"),list):
                        item["status"]={v["key"].split(".")[-1]:v.get("value")
                                        for v in details["status"] if isinstance(v,dict) and v.get("key")}
                    program,err=_hc_get(token,endpoint+"/programs/active")
                    if err==429:
                        raise RuntimeError("Home Connect appliance list HTTP 429")
                    if not err and isinstance(program.get("program"),dict):
                        active=program["program"]
                        item["active_program"]=active.get("key")
                        item["remaining_updated_at"]=datetime.now(timezone.utc).isoformat()
                        item["program_options"]=[{"key":str(v.get("key","")).split(".")[-1],
                            "value":v.get("value"),"unit":v.get("unit")}
                            for v in active.get("options",[]) if isinstance(v,dict)]
                    return item
                # Avoid concurrent bursts, and prevent one 429 being hidden by other successes.
                devices=[]
                for ap in all_devices[:16]:
                    devices.append(probe(ap))
                HOME_CONNECT_DEVICE_IDS.clear()
                HOME_CONNECT_DEVICE_IDS.update({str(ap.get("name")):str(ap.get("haId"))
                    for ap in all_devices if ap.get("name") and ap.get("haId")})
                result["devices"]=devices
                result["online_count"]=sum(bool(d["connected"]) for d in devices)
                _hc_record_activity(devices)
                result["events"]=HOME_CONNECT_EVENTS[-60:]
                _hc_private_snapshot_write(HOME_CONNECT_LAST_GOOD_FILE,
                    _hc_safe_snapshot(devices,checked))
            except (OSError,ValueError,KeyError,RuntimeError,urllib.error.URLError) as exc:
                message=str(exc)
                import re
                http_match=re.fullmatch(r"Home Connect appliance list HTTP ([1-5][0-9]{2})",message)
                if http_match:
                    code=int(http_match.group(1))
                    result["error_code"]="cloud_http_"+str(code)
                    if code==429:
                        if _hc_cooldown_seconds()<=0:
                            _hc_set_cooldown(3600)
                        result["error"]="Home Connect API rate limit; showing last-known readings"
                    elif code in (401,403):
                        result["error"]="Home Connect rejected API access; verify authorisation"
                    else:
                        result["error"]="Home Connect cloud request failed (HTTP "+str(code)+")"
                elif "refresh token" in message.lower() or "authorisation" in message.lower():
                    result["error_code"]="auth"
                    result["error"]="Home Connect needs reauthorisation"
                else:
                    result["error_code"]="cloud_unavailable"
                    result["error"]="Home Connect cloud temporarily unavailable"
                result["stale"]=True
        if result.get("stale") and previous:
            result["devices"]=previous["devices"]
            result["last_successful_at"]=previous.get("checked_at")
            result["online_count"]=sum(bool(d.get("connected")) for d in result["devices"])
        elif result.get("stale"):
            result["devices"]=[]
        if result.get("stale"):
            result["retry_after_seconds"]=_hc_cooldown_seconds()
        # Cache cloud successes 2 hours; errors until next safe retry window.
        ttl=(max(120,_hc_cooldown_seconds()) if result.get("error_code")=="cloud_http_429"
            else (600 if result.get("stale") else HOME_CONNECT_SNAPSHOT_INTERVAL))
        HOME_CONNECT_CACHE.update(data=result,expires=time.monotonic()+ttl)
        return result


def _hc_record_activity(devices):
    """Store meaningful state transitions; no credentials, identifiers or continuous spam."""
    global HOME_CONNECT_EVENTS
    if not HOME_CONNECT_EVENTS:
        try:
            with open(HOME_CONNECT_EVENTS_FILE,encoding="utf-8") as stream:
                saved=json.load(stream)
            if isinstance(saved,list):
                HOME_CONNECT_EVENTS=[r for r in saved[-300:] if isinstance(r,dict)]
        except (OSError,ValueError):
            pass
    now=datetime.now(timezone.utc).isoformat()
    changed=False
    for d in devices:
        name=str(d.get("name",""))[:90]
        if not name:
            continue
        status=d.get("status") or {}
        current={"connected":bool(d.get("connected")),
                 "operation":str(status.get("OperationState","")).split(".")[-1],
                 "door":str(status.get("DoorState","")).split(".")[-1],
                 "program":str(d.get("active_program") or "").split(".")[-1]}
        old=HOME_CONNECT_LAST_STATES.get(name)
        if old is not None:
            for field,label in (("connected","Connectivity"),("operation","Operation"),
                                ("door","Door"),("program","Programme")):
                if current[field]!=old.get(field):
                    value=str(current[field])[:100] or "None"
                    HOME_CONNECT_EVENTS.append({"at":now,"name":name,
                        "event":label,"value":value})
                    changed=True
        HOME_CONNECT_LAST_STATES[name]=current
    if changed:
        HOME_CONNECT_EVENTS=HOME_CONNECT_EVENTS[-300:]
        try:
            target=HOME_CONNECT_EVENTS_FILE+".new"
            fd=os.open(target,os.O_WRONLY | os.O_CREAT | os.O_TRUNC,0o600)
            with os.fdopen(fd,"w",encoding="utf-8") as stream:
                json.dump(HOME_CONNECT_EVENTS,stream,separators=(",",":"))
            os.replace(target,HOME_CONNECT_EVENTS_FILE)
        except OSError:
            pass

def home_connect_details(name):
    # Per-appliance read-only on-demand details; cached to limit cloud requests.
    if not isinstance(name,str) or len(name)>120:
        return {"error":"Invalid appliance"}
    with HOME_CONNECT_LOCK:
        now=time.monotonic()
        hit=HOME_CONNECT_DETAILS_CACHE.get(name)
        if hit and hit["expires"]>now:
            return hit["data"]
        aid=HOME_CONNECT_DEVICE_IDS.get(name)
        if not aid:
            return {"error":"Open the Appliances page first, then select a device."}
        result={"name":name,"settings":[],"available_programs":[],
                "selected_program":None,"selected_options":[],
                "read_only":True,"checked_at":datetime.now(timezone.utc).isoformat()}
        try:
            token=_hc_token()
            root="/homeappliances/"+urllib.parse.quote(aid,safe="")
            selected,serr=_hc_get(token,root+"/programs/selected")
            if not serr:
                p=selected.get("program")
                if isinstance(p,dict):
                    result["selected_program"]=p.get("key")
                    result["selected_options"]=[{"name":str(v.get("key","")).split(".")[-1],
                        "value":v.get("value"),"unit":v.get("unit")}
                        for v in p.get("options",[])[:35] if isinstance(v,dict)]
            available,aerr=_hc_get(token,root+"/programs/available")
            if not aerr:
                result["available_programs"]=[{"name":str(p.get("key","")).split(".")[-1]}
                    for p in available.get("programs",[])[:45] if isinstance(p,dict)]
            # The current OAuth token has IdentifyAppliance + Monitor only.
            # Do not query /settings without Settings scope: repeated 403s can
            # trigger Home Connect error-rate blocking.
            result["availability"]={"selected":serr,"programs":aerr,"settings":"scope_not_granted"}
        except (OSError,ValueError,KeyError,RuntimeError,urllib.error.URLError):
            result["error"]="Home Connect detail information temporarily unavailable"
        HOME_CONNECT_DETAILS_CACHE[name]={"expires":time.monotonic()+600,"data":result}
        return result


# One persistent server-sent event stream avoids exhausting Home Connect's
# daily REST allowance. Reconnect with backoff, never loop aggressively.
HOME_CONNECT_SSE_CONNECTED = False
HOME_CONNECT_LAST_EVENT_AT = None
HOME_CONNECT_EVENTS_LAST_SAVE = 0
def _hc_sse_event(kind, payload, appliance_id):
    global HOME_CONNECT_LAST_EVENT_AT, HOME_CONNECT_EVENTS_LAST_SAVE
    if kind in ("KEEP-ALIVE", ""):
        return
    if kind not in ("STATUS", "NOTIFY", "EVENT", "CONNECTED", "DISCONNECTED",
                    "PAIRED", "DEPAIRED"):
        return
    with HOME_CONNECT_LOCK:
        name=next((name for name,aid in HOME_CONNECT_DEVICE_IDS.items()
                   if aid==appliance_id),None)
        if not name:
            return
        cache=HOME_CONNECT_CACHE.get("data")
        if not cache:
            return
        device=next((d for d in cache.get("devices",[]) if d.get("name")==name),None)
        if device is None:
            return
        now=datetime.now(timezone.utc).isoformat()
        updates=[]
        if kind in ("CONNECTED","DISCONNECTED"):
            connected=(kind=="CONNECTED")
            if device.get("connected")!=connected:
                device["connected"]=connected
                updates.append(("Connectivity","Connected" if connected else "Disconnected"))
        if kind in ("STATUS","NOTIFY","EVENT"):
            for item in payload.get("items",[])[:30]:
                if not isinstance(item,dict):
                    continue
                rawkey=item.get("key")
                if not isinstance(rawkey,str) or len(rawkey)>200:
                    continue
                key=rawkey.split(".")[-1]
                value=item.get("value")
                if key in ("OperationState","DoorState","CurrentCavityTemperature",
                           "InteriorIlluminationActive","RemoteControlActive",
                           "RemoteControlStartAllowed","LocalControlActive"):
                    prev=device.setdefault("status",{}).get(key)
                    device["status"][key]=value
                    if prev != value:
                        updates.append((key,str(value).split(".")[-1][:100]))
                if key in ("RemainingProgramTime","ElapsedProgramTime",
                           "ProgramProgress","EstimatedTotalProgramTime",
                           "RemainingProgramTimeIsEstimated"):
                    if key=="RemainingProgramTime":
                        device["remaining_updated_at"]=now
                    options=device.setdefault("program_options",[])
                    found=next((v for v in options if v.get("key")==key),None)
                    if found is None:
                        options.append({"key":key,"value":value,"unit":item.get("unit")})
                    else:
                        found.update(value=value,unit=item.get("unit"))
                if kind=="EVENT" and key in ("ProgramFinished","ProgramAborted",
                                               "ProgramStarted","ProgramPaused"):
                    updates.append(("Event",key))
        for label,value in updates:
            HOME_CONNECT_EVENTS.append({"at":now,"name":name,
                                        "event":label,"value":value})
        if updates:
            del HOME_CONNECT_EVENTS[:-300]
            cache["events"]=HOME_CONNECT_EVENTS[-60:]
            cache["online_count"]=sum(bool(d.get("connected")) for d in cache.get("devices",[]))
            if time.monotonic()-HOME_CONNECT_EVENTS_LAST_SAVE>120:
                try:
                    path=HOME_CONNECT_EVENTS_FILE+".new"
                    fd=os.open(path,os.O_WRONLY | os.O_CREAT | os.O_TRUNC,0o600)
                    with os.fdopen(fd,"w",encoding="utf-8") as stream:
                        json.dump(HOME_CONNECT_EVENTS[-300:],stream,separators=(",",":"))
                    os.replace(path,HOME_CONNECT_EVENTS_FILE)
                    HOME_CONNECT_EVENTS_LAST_SAVE=time.monotonic()
                except OSError:
                    pass
        HOME_CONNECT_LAST_EVENT_AT=now

def _hc_event_loop():
    global HOME_CONNECT_SSE_CONNECTED, HOME_CONNECT_RATE_LIMIT_UNTIL
    import urllib.error
    failures=0
    while True:
        # The event stream shares the same cooldown as appliance polling.
        remaining=_hc_cooldown_seconds()
        if remaining>0:
            HOME_CONNECT_SSE_CONNECTED=False
            time.sleep(min(remaining,60))
            continue
        if not HOME_CONNECT_DEVICE_IDS:
            time.sleep(60)
            continue
        try:
            with HOME_CONNECT_LOCK:
                if _hc_cooldown_seconds()>0:
                    continue
                token=_hc_token()
            req=urllib.request.Request(HOME_CONNECT_BASE+"/homeappliances/events",
                headers={"Authorization":"Bearer "+token,"Accept":"text/event-stream",
                         "Cache-Control":"no-cache"})
            with urllib.request.urlopen(req,timeout=85) as response:
                HOME_CONNECT_SSE_CONNECTED=True
                failures=0
                event_type=""
                event_id=""
                data=[]
                while True:
                    raw=response.readline()
                    if not raw:
                        break
                    line=raw.decode("utf-8",errors="replace").rstrip("\r\n")
                    if not line:
                        if data:
                            try:
                                payload=json.loads("\n".join(data))
                                if isinstance(payload,dict):
                                    _hc_sse_event(event_type,payload,event_id)
                            except ValueError:
                                pass
                        event_type=""
                        event_id=""
                        data=[]
                    elif line.startswith("event:"):
                        event_type=line[6:].strip()
                    elif line.startswith("id:"):
                        event_id=line[3:].strip()
                    elif line.startswith("data:"):
                        data.append(line[5:].lstrip())
            HOME_CONNECT_SSE_CONNECTED=False
            failures+=1
        except urllib.error.HTTPError as exc:
            HOME_CONNECT_SSE_CONNECTED=False
            failures+=1
            if exc.code==429:
                _hc_set_cooldown(_hc_retry_after(exc))
        except Exception:
            HOME_CONNECT_SSE_CONNECTED=False
            failures+=1
        time.sleep(min(3600,max(300,300*(2**min(4,failures-1)))))

def unifi_status():
    if _unifi_snmp_enabled():
        return _unifi_snmp_status()
    global UNIFI_CLIENT, UNIFI_LAST_GOOD
    with UNIFI_LOCK:
        now = time.monotonic()
        if UNIFI_CACHE.get('expires', 0) > now:
            return UNIFI_CACHE['data']
        result = {'configured': False, 'controller_online': False, 'devices': [],
                  'checked_at': datetime.now(timezone.utc).isoformat(), 'last_seen_at': None}
        try:
            config = _unifi_config()
            if not config:
                result['message'] = 'Run connector.py --configure-unifi locally to link UniFi.'
            else:
                result['configured'] = True
                if UNIFI_CLIENT is None or UNIFI_CLIENT.config != config:
                    UNIFI_CLIENT = _UniFiClient(config)
                    UNIFI_LAST_GOOD = None
                result['devices'] = _unifi_devices(UNIFI_CLIENT.devices())
                result['controller_online'] = True
                result['last_seen_at'] = datetime.now(timezone.utc).isoformat()
                UNIFI_LAST_GOOD = {'devices': result['devices'], 'last_seen_at': result['last_seen_at']}
                result['message'] = 'Live readings from UniFi Network Server.'
        except PermissionError:
            result['message'] = 'UniFi login or permissions rejected. Check the local view-only account.'
        except ValueError:
            result['message'] = 'UniFi local configuration or certificate needs checking. Rerun local setup.'
        except Exception:
            result['message'] = 'UniFi controller unavailable. Check that its host is awake and Network Server is running. Wi-Fi may still be working.'
        if not result['controller_online'] and result['configured'] and UNIFI_LAST_GOOD:
            result.update(UNIFI_LAST_GOOD)
        UNIFI_CACHE.update(data=result, expires=time.monotonic() + (30 if result['controller_online'] else 10))
        return result


def configure_unifi():
    import getpass
    import tempfile
    from pathlib import Path
    url = input('UniFi controller HTTPS address (including port): ').strip().rstrip('/')
    host, port = _unifi_address(url)
    username = input('UniFi local username [eldoret]: ').strip() or 'eldoret'
    site = input('UniFi site [default]: ').strip() or 'default'
    with socket.create_connection((host, port), timeout=5) as sock:
        with ssl._create_unverified_context().wrap_socket(sock, server_hostname=host) as tls:
            fingerprint = hashlib.sha256(tls.getpeercert(binary_form=True)).hexdigest()
    print('Controller certificate SHA-256:', fingerprint)
    if input('Trust this local controller certificate? Type yes: ').strip().lower() != 'yes':
        raise ValueError('Controller certificate was not trusted; nothing saved.')
    config = {'url': url, 'username': username, 'site': site, 'certificate_sha256': fingerprint,
              'password': getpass.getpass('UniFi view-only password: ')}
    devices = _unifi_devices(_UniFiClient(config).devices())
    folder = Path(UNIFI_CONFIG_FILE).parent
    folder.mkdir(mode=0o700, parents=True, exist_ok=True)
    folder.chmod(0o700)
    fd, name = tempfile.mkstemp(prefix='.config-', dir=str(folder))
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            os.fchmod(file.fileno(), 0o600)
            json.dump(config, file)
        os.replace(name, UNIFI_CONFIG_FILE)
    finally:
        if os.path.exists(name): os.unlink(name)
    print('UniFi read verified:', len(devices), 'access points. Credentials saved locally with owner-only access.')
    print('The Network page will pick these up on its next reading; no router reboot needed.')


def network_status():
    now=time.time()
    cached=NETWORK_STATUS_CACHE.get("data")
    if cached and now-NETWORK_STATUS_CACHE.get("time",0) < 8:
        return cached
    devices=[]
    with ThreadPoolExecutor(max_workers=16) as pool:
        futures=[pool.submit(_probe_network_device,d) for d in NETWORK_PROBES]
        for future in as_completed(futures):
            try:
                devices.append(future.result())
            except Exception:
                pass
    order={d["ip"]:i for i,d in enumerate(NETWORK_PROBES)}
    devices.sort(key=lambda x:order.get(x["ip"],999))
    data={"devices":devices,"checked_at":datetime.now(timezone.utc).isoformat()}
    NETWORK_STATUS_CACHE["time"]=time.time()
    NETWORK_STATUS_CACHE["data"]=data
    return data

def sky_send_key(key):
    if key not in SKY_KEY_MAP:
        raise ValueError("Unsupported Sky key")
    code = SKY_KEY_MAP[key]
    command = [4,1,0,0,0,0,224 + (code // 16),code % 16]
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(4)
    try:
        client.connect((sky_q_host(), SKY_Q_REMOTE_PORT))
        length = 12
        while True:
            data = client.recv(1024)
            if not data:
                raise RuntimeError("Sky Q closed connection")
            if len(data) < 24:
                client.send(data[:length])
                length = 1
            else:
                client.send(bytes(command))
                command[1] = 0
                client.send(bytes(command))
                return
    finally:
        client.close()

# Hue credentials are optional at startup; individual Hue requests validate their keys.

def fetch_github(path):
    now = time.time()
    cached = STATIC_CACHE.get(path)
    if cached and (now - cached["time"] < (15 if path in ("tvs.html", "index.html", "velux.js", "velux.html") else STATIC_CACHE_TTL)):
        return cached["data"]
    try:
        req = urllib.request.Request(
            GITHUB_BASE + path,
            headers={"User-Agent": "Eldoret-Connector/1.0", "Cache-Control": "no-cache"},
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read()
        STATIC_CACHE[path] = {"time": now, "data": data}
        return data
    except Exception:
        if cached:
            return cached["data"]
        raise

def hue_get(bridge_name, path):
    bridge = BRIDGES[bridge_name]
    url = f"http://{bridge['ip']}/api/{bridge['key']}/{path}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read()

HUE_SENSOR_CACHE = {}
HUE_SENSOR_LOCK = threading.Lock()

def _normalise_hue_sensors(bridge_name, resources):
    if not isinstance(resources, dict): raise ValueError("Hue sensor response unavailable")
    devices = {}
    for sensor_id, sensor in resources.items():
        if not isinstance(sensor, dict) or "error" in sensor: continue
        state, config = sensor.get("state") or {}, sensor.get("config") or {}
        if not any(k in state for k in ("presence", "temperature", "lightlevel", "buttonevent")) and "battery" not in config: continue
        unique = str(sensor.get("uniqueid") or sensor_id).split("-")[0]
        key = bridge_name+":"+unique
        item = devices.setdefault(key, {"id":key, "bridge":bridge_name, "name":sensor.get("name") or "Hue sensor", "model":sensor.get("modelid"), "motion":None, "temperature":None, "lux":None, "battery":None, "reachable":None, "updated_at":None})
        if "presence" in state: item["name"] = sensor.get("name") or item["name"]
        if isinstance(config.get("reachable"), bool):
            item["reachable"] = config["reachable"] if item["reachable"] is None else item["reachable"] and config["reachable"]
        battery = config.get("battery")
        if type(battery) in (int, float) and 0 <= battery <= 100: item["battery"] = battery
        valid = state.get("status") not in ("notavailable", "unknown")
        if valid and isinstance(state.get("presence"), bool): item["motion"] = state["presence"]
        temperature = state.get("temperature")
        if valid and state.get("temperaturevalid", True) and type(temperature) in (int, float) and -5000 <= temperature <= 10000: item["temperature"] = round(temperature/100, 1)
        light = state.get("lightlevel")
        if valid and state.get("lightlevelvalid", True) and type(light) in (int, float) and 0 <= light <= 65534:
            item["lux"] = round(10 ** ((light-1)/10000), 1)
        updated = state.get("lastupdated")
        if isinstance(updated, str) and updated != "none":
            stamp = updated if updated.endswith("Z") else updated+"Z"
            if not item["updated_at"] or stamp > item["updated_at"]: item["updated_at"] = stamp
    return list(devices.values())


def hue_sensors():
    with HUE_SENSOR_LOCK:
        if HUE_SENSOR_CACHE and time.monotonic()-HUE_SENSOR_CACHE["time"] < 10: return HUE_SENSOR_CACHE["value"]
        devices, errors = [], []
        def read(bridge):
            if not BRIDGES[bridge].get("key"): raise ValueError("Bridge not configured")
            return _normalise_hue_sensors(bridge, json.loads(hue_get(bridge, "sensors").decode("utf-8")))
        with ThreadPoolExecutor(max_workers=2) as pool:
            jobs = {pool.submit(read, bridge):bridge for bridge in BRIDGES}
            for job in as_completed(jobs):
                try: devices.extend(job.result())
                except Exception: errors.append(jobs[job].title()+" bridge unavailable")
        devices.sort(key=lambda d:(d["bridge"], d["name"].lower()))
        result = {"devices":devices, "errors":errors, "checked_at":datetime.now(timezone.utc).isoformat()}
        HUE_SENSOR_CACHE.update(time=time.monotonic(), value=result)
        return result


def hue_put(bridge_name, path, payload):
    bridge = BRIDGES[bridge_name]
    url = f"http://{bridge['ip']}/api/{bridge['key']}/{path}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="PUT")
    with urllib.request.urlopen(req, timeout=5) as response:
        return response.read()

def sky_send_channel(channel):
    digits = str(channel)
    if not digits.isdigit() or len(digits) > 4:
        raise ValueError("Invalid channel")

    # Apps such as Netflix can consume digit key presses instead of Sky Q.
    # Only leave the app when Sky Q reports no current media URI.
    try:
        current_uri = sky_get_media_uri()
    except Exception:
        current_uri = None  # Unknown: preserve normal live-TV switching.
    if current_uri == "":
        sky_send_key("home")
        time.sleep(1.8)

    for digit in digits:
        sky_send_key(digit)
        time.sleep(0.12)

def _localname(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag.split(":", 1)[-1]

SKY_SOAP_LOCK=threading.Lock()
SKY_SOAP_DISCOVERY={"host":None,"url":None,"retry_at":0,"last_error":None}

def sky_soap_control_url():
    # Sky Q's discovery service is fragile: never re-scan 50 URLs every 15 seconds.
    host=sky_q_host()
    now=time.monotonic()
    with SKY_SOAP_LOCK:
        if SKY_SOAP_DISCOVERY["host"]!=host:
            SKY_SOAP_DISCOVERY.update(host=host,url=None,retry_at=0,last_error=None)
        if SKY_SOAP_DISCOVERY["url"]:
            return SKY_SOAP_DISCOVERY["url"]
        if now < SKY_SOAP_DISCOVERY["retry_at"]:
            return None
        # One bounded discovery per three-minute failure window, shared by all clients.
        SKY_SOAP_DISCOVERY["retry_at"]=now+1800
    headers={"User-Agent":"SKYPLUS_skyplus"}
    # Stop early if the device is not providing valid XML; do not hammer it 50 times.
    valid_xml=0
    failures=0
    for idx in range(50):
        url=f"http://{host}:49153/description{idx}.xml"
        try:
            req=urllib.request.Request(url,headers=headers)
            with urllib.request.urlopen(req,timeout=0.8) as response:
                root=ET.fromstring(response.read(512*1024))
            valid_xml+=1
            failures=0
            device_type=next((el.text or "" for el in root.iter() if _localname(el.tag)=="deviceType"),"")
            if "SkyControl" not in device_type:
                continue
            for service in root.iter():
                if _localname(service.tag)!="service":continue
                fields={_localname(child.tag):(child.text or "") for child in list(service)}
                if fields.get("serviceId")=="urn:nds-com:serviceId:SkyPlay":
                    path=fields.get("controlURL")
                    if path:
                        result=f"http://{host}:49153{path}"
                        with SKY_SOAP_LOCK:
                            SKY_SOAP_DISCOVERY.update(url=result,retry_at=0,last_error=None)
                        return result
        except Exception:
            failures+=1
            # No service response in first three probes: avoid 47 more requests.
            if failures>=3 and valid_xml==0:break
    with SKY_SOAP_LOCK:
        SKY_SOAP_DISCOVERY["last_error"]="SkyPlay discovery unavailable; retry paused"
    return None

def sky_get_media_uri():
    control_url = sky_soap_control_url()
    if not control_url:
        raise RuntimeError("Sky Q SkyPlay SOAP service not found")
    method = "GetMediaInfo"
    payload = f"""<s:Envelope xmlns:s='http://schemas.xmlsoap.org/soap/envelope/' s:encodingStyle='http://schemas.xmlsoap.org/soap/encoding/'><s:Body><u:{method} xmlns:u="urn:schemas-nds-com:service:SkyPlay:2"><InstanceID>0</InstanceID></u:{method}></s:Body></s:Envelope>""".encode()
    req = urllib.request.Request(
        control_url,
        data=payload,
        headers={
            "Content-Type": 'text/xml; charset="utf-8"',
            "SOAPACTION": '"urn:schemas-nds-com:service:SkyPlay:2#GetMediaInfo"',
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=3) as response:
        root = ET.fromstring(response.read())
    for el in root.iter():
        if _localname(el.tag) == "CurrentURI":
            return el.text or ""
    return ""

def sky_channel_logo_url(service):
    if not service:
        return None
    sid = str(service.get("sid", ""))
    name = str(service.get("t", ""))
    if not sid or not name:
        return None
    chid = "".join(ch for ch in name.lower() if ch.isalnum())
    return f"https://imageservice.sky.com/logo/skychb_{sid}{chid}/600/600?territory=GB&provider=SKY&proposition=SKYQ"

def radio_stations():
    url = "https://de1.api.radio-browser.info/json/stations/search?countrycode=GB&hidebroken=true&order=votes&reverse=true&limit=84"
    req = urllib.request.Request(url, headers={"User-Agent":"EldoretHomeAutomation/1.0"})
    with urllib.request.urlopen(req, timeout=15) as response:
        raw = json.loads(response.read().decode("utf-8", errors="replace"))
    seen, stations = set(), []
    for s in raw:
        name = str(s.get("name") or "").strip()
        stream = s.get("url_resolved") or s.get("url")
        key=(name.lower(),stream)
        if not name or not stream or key in seen: continue
        seen.add(key)
        stations.append({"stationuuid":s.get("stationuuid"),"name":name,"url":s.get("url"),"url_resolved":stream,"homepage":s.get("homepage"),"favicon":s.get("favicon"),"tags":s.get("tags"),"country":s.get("country"),"codec":s.get("codec"),"bitrate":s.get("bitrate")})
    return {"stations":stations}

def sky_recordings_top14():
    data = sky_json("/as/pvr/?limit=14&offset=0")
    items = data.get("pvrItems", []) if isinstance(data, dict) else []
    recordings = []
    for r in items[:14]:
        start_ts = r.get("ast") or r.get("st") or 0
        end_ts = start_ts + (r.get("finald") or r.get("schd") or 0) if start_ts else 0
        recordings.append({
            "pvrid": r.get("pvrid"),
            "title": r.get("t"),
            "channel": r.get("cn"),
            "synopsis": r.get("sy"),
            "summary": r.get("sy"),
            "status": r.get("status"),
            "season": r.get("seasonnumber"),
            "episode": r.get("episodenumber"),
            "programmeuuid": r.get("programmeuuid"),
            "start": datetime.fromtimestamp(start_ts, tz=timezone.utc).isoformat() if start_ts else None,
            "end": datetime.fromtimestamp(end_ts, tz=timezone.utc).isoformat() if end_ts else None,
        })
    return {"recordings": recordings}

def sky_play_recording(pvrid):
    if not pvrid: raise ValueError("Missing pvrid")
    sky_json("/as/pvr/play/" + urllib.parse.quote(str(pvrid), safe=""))
    return True

def sky_radio_guide():
    candidates = ["/as/services/5/1", "/as/services/4/1", "/as/services/1/1"]
    merged = []
    seen = set()
    for path in candidates:
        try:
            url = f"http://{sky_q_host()}:{SKY_Q_JSON_PORT}{path}"
            req = urllib.request.Request(url, headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            for s in data.get("services", []):
                key = (str(s.get("c","")), str(s.get("sid","")))
                if key not in seen:
                    seen.add(key); merged.append(s)
        except Exception:
            pass
    radios = [s for s in merged if str(s.get("sf","")).lower() == "au"]
    if not radios:
        radios = [s for s in merged if str(s.get("c","")).isdigit() and 101 <= int(str(s.get("c"))) <= 999]
    radios.sort(key=lambda s:int(str(s.get("c","0"))) if str(s.get("c","")).isdigit() else 99999)
    channels=[]
    for s in radios:
        raw=str(s.get("c",""))
        display=raw.zfill(4) if raw.isdigit() and len(raw)<4 else raw
        item={"channelno":display,"tune":display,"channel":s.get("t"),"sid":s.get("sid"),"logo":sky_channel_logo_url(s),"is_radio":True,"programme":None,"synopsis":None,"start":None,"end":None}
        if s.get("sid"): item.update(sky_epg_now_next(s.get("sid")))
        channels.append(item)
    return {"channels":channels}

def sky_apps():
    data = sky_json("/as/apps")
    raw = data.get("apps", data) if isinstance(data, dict) else data
    apps = []
    if isinstance(raw, list):
        for a in raw:
            if not isinstance(a, dict): continue
            title = a.get("title") or a.get("name") or a.get("t") or a.get("appName")
            appid = a.get("appId") or a.get("appid") or a.get("id") or a.get("app")
            if title and appid:
                apps.append({"title":title,"appid":appid,"icon":a.get("icon") or a.get("logo") or a.get("image"),"raw":a})
    return {"apps":apps}

def sky_launch_app(appid):
    if not appid: raise ValueError("Missing app id")
    paths = ["/as/apps/" + urllib.parse.quote(str(appid), safe=""), "/as/apps/launch/" + urllib.parse.quote(str(appid), safe="")]
    last = None
    for path in paths:
        try:
            url = f"http://{SKY_Q_HOST}:{SKY_Q_JSON_PORT}{path}"
            req = urllib.request.Request(url, data=b"", method="POST", headers={"User-Agent":"Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as response: response.read()
            return True
        except Exception as exc: last = exc
    if last: raise last
    return False

def sky_search_channels(query):
    q = (query or "").strip().lower()
    if not q:
        return {"results": []}
    services = sky_channel_list()
    results = []
    for service in services:
        name, number = str(service.get("t", "")), str(service.get("c", ""))
        epg = {}
        if service.get("sid"):
            try: epg = sky_epg_now_next(service.get("sid")) or {}
            except Exception: epg = {}
        current, nxt = str(epg.get("programme") or ""), epg.get("next") or {}
        next_title = str(nxt.get("programme") or "")
        matchtype = matchprogramme = matchstart = None
        if q in name.lower() or q == number: matchtype = "channel"
        elif q in current.lower(): matchtype, matchprogramme, matchstart = "now", current, epg.get("start")
        elif q in next_title.lower(): matchtype, matchprogramme, matchstart = "next", next_title, nxt.get("start")
        if matchtype:
            item = {"channel":name,"channelno":number,"sid":service.get("sid"),"logo":sky_channel_logo_url(service),"matchtype":matchtype,"matchprogramme":matchprogramme,"matchstart":matchstart}
            item.update(epg); results.append(item)
    rank = {"now":0,"next":1,"channel":2}
    results.sort(key=lambda x:(rank.get(x.get("matchtype"),9),0 if str(x.get("channel","")).lower().startswith(q) else 1,str(x.get("channelno") or "9999")))
    return {"results":results[:20]}

def sky_range_guide(start, end, page=0, size=14):
    services = sky_channel_list()
    selected = []
    for s in services:
        raw = str(s.get("c", ""))
        if not raw.isdigit():
            continue
        number = int(raw)
        if start <= number <= end:
            selected.append(s)
    selected.sort(key=lambda s: int(str(s.get("c", "99999"))))
    total = len(selected)
    page = max(0, int(page))
    size = max(1, min(30, int(size)))
    chunk = selected[page * size:(page + 1) * size]
    channels = []
    for service in chunk:
        number = str(service.get("c", ""))
        item = {
            "channelno": number,
            "channel": service.get("t"),
            "sid": service.get("sid"),
            "logo": sky_channel_logo_url(service),
            "programme": None,
            "synopsis": None,
            "start": None,
            "end": None,
        }
        if service.get("sid"):
            item.update(sky_epg_now_next(service.get("sid")))
        channels.append(item)
    pages = max(1, (total + size - 1) // size)
    return {"channels": channels, "page": page, "pages": pages, "total": total, "start": start, "end": end}

def sky_top_picks(page=0, size=14):
    services = sky_channel_list()
    priority = [
        "101","102","103","104","105","106","107","108","109","110",
        "301","302","303","304","305","306","307","308",
        "401","402","403","404","405","406","407","408","409",
        "501","502","503","504","505"
    ]
    by_number = {str(s.get("c")): s for s in services}
    ordered = []
    seen = set()
    for number in priority:
        service = by_number.get(number)
        if service:
            ordered.append(service); seen.add(number)
    for service in services:
        number = str(service.get("c",""))
        if number in seen or not number.isdigit():
            continue
        if 101 <= int(number) <= 599:
            ordered.append(service); seen.add(number)

    picks = []
    for service in ordered:
        if len(picks) >= 42:
            break
        item = {
            "channelno": str(service.get("c","")),
            "channel": service.get("t"),
            "sid": service.get("sid"),
            "logo": sky_channel_logo_url(service),
            "programme": None,
            "synopsis": None,
            "start": None,
            "end": None,
        }
        if service.get("sid"):
            try:
                item.update(sky_epg_now_next(service.get("sid")))
            except Exception:
                pass
        if item.get("programme"):
            picks.append(item)

    page = max(0, int(page))
    size = max(1, min(30, int(size)))
    total = len(picks)
    pages = max(1, (total + size - 1) // size)
    page = min(page, pages - 1)
    return {"channels": picks[page*size:(page+1)*size], "page": page, "pages": pages, "total": total}

def sky_named_guide(group):
    services = sky_channel_list()
    numbered = GUIDE_CHANNEL_NUMBERS.get(group)
    channels = []
    if numbered:
        by_number = {str(s.get("c")): s for s in services}
        for number in numbered:
            service = by_number.get(number)
            item = {"requested":number,"channelno":number,"channel":service.get("t") if service else None,"sid":service.get("sid") if service else None,"logo":sky_channel_logo_url(service),"programme":None,"synopsis":None,"start":None,"end":None}
            if service and service.get("sid"): item.update(sky_epg_now_next(service.get("sid")))
            channels.append(item)
        return {"group":group,"channels":channels}
    wanted = GUIDE_GROUPS.get(group, [])
    for requested in wanted:
        req = requested.lower()
        service = next((s for s in services if req in str(s.get("t","")).lower()), None)
        item = {"requested":requested,"channelno":service.get("c") if service else None,"channel":service.get("t") if service else requested,"sid":service.get("sid") if service else None,"logo":sky_channel_logo_url(service),"programme":None,"synopsis":None,"start":None,"end":None}
        if service and service.get("sid"): item.update(sky_epg_now_next(service.get("sid")))
        channels.append(item)
    return {"group":group,"channels":channels}

def sky_sport_guide():
    services = sky_channel_list()
    by_number = {str(s.get("c")): s for s in services}
    channels = []
    for number in SPORT_CHANNEL_NUMBERS:
        service = by_number.get(number)
        item = {
            "channelno": number,
            "channel": service.get("t") if service else None,
            "sid": service.get("sid") if service else None,
            "logo": sky_channel_logo_url(service),
            "programme": None,
            "synopsis": None,
            "start": None,
            "end": None,
        }
        if service and service.get("sid"):
            item.update(sky_epg_now_next(service.get("sid")))
        channels.append(item)
    return {"channels": channels}

SKY_SERVICES_LOCK=threading.Lock()
SKY_SERVICES_CACHE=[]
SKY_SERVICES_NEXT=0
def sky_channel_list():
    global SKY_SERVICES_CACHE, SKY_SERVICES_NEXT
    if not SKY_SERVICES_LOCK.acquire(blocking=False):
        return list(SKY_SERVICES_CACHE)
    try:
        if time.monotonic() >= SKY_SERVICES_NEXT:
            SKY_SERVICES_NEXT=time.monotonic()+1800
            fresh=_sky_channel_list_uncached()
            if fresh:
                SKY_SERVICES_CACHE=fresh
                SKY_SERVICES_NEXT=time.monotonic()+21600
        return list(SKY_SERVICES_CACHE)
    finally:
        SKY_SERVICES_LOCK.release()

def _sky_channel_list_uncached():
    candidates = ["/as/services/4/1", "/as/services/1/1", "/as/services/5/1"]
    for path in candidates:
        try:
            url = f"http://{sky_q_host()}:{SKY_Q_JSON_PORT}{path}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode("utf-8", errors="replace"))
            if isinstance(data, dict) and isinstance(data.get("services"), list):
                return data["services"]
        except Exception:
            pass
    return []

def sky_epg_now(sid):
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y%m%d")
    url = f"http://atlantis.epgsky.com/as/schedule/{date}/{sid}"
    req = urllib.request.Request(url, headers={
        "x-skyott-territory": "GB",
        "x-skyott-provider": "SKY",
        "x-skyott-proposition": "SKYQ",
        "User-Agent": "Eldoret/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        schedule = data.get("schedule", [])
        now_ts = int(now.timestamp())
        for block in schedule:
            for event in block.get("events", []):
                start = int(event.get("st", 0))
                duration = int(event.get("d", 0))
                if start <= now_ts < start + duration:
                    return {
                        "programme": event.get("t"),
                        "synopsis": event.get("sy"),
                        "start": datetime.fromtimestamp(start, tz=timezone.utc).isoformat(),
                        "end": datetime.fromtimestamp(start + duration, tz=timezone.utc).isoformat(),
                        "programmeuuid": event.get("programmeuuid"),
                    }
    except Exception:
        pass
    return {}

SKY_EPG_CACHE={}
SKY_EPG_LOCK=threading.Lock()
def sky_epg_now_next(sid):
    key=str(sid)
    now=time.monotonic()
    with SKY_EPG_LOCK:
        cached=SKY_EPG_CACHE.get(key)
        if cached and now<cached[0]:
            return dict(cached[1])
        SKY_EPG_CACHE[key]=(now+60,{})
    result=_sky_epg_now_next_uncached(sid)
    with SKY_EPG_LOCK:
        SKY_EPG_CACHE[key]=(time.monotonic()+(120 if result else 60),result)
    return result

def _sky_epg_now_next_uncached(sid):
    now = datetime.now(timezone.utc)
    date = now.strftime("%Y%m%d")
    url = f"http://atlantis.epgsky.com/as/schedule/{date}/{sid}"
    req = urllib.request.Request(url, headers={
        "x-skyott-territory": "GB",
        "x-skyott-provider": "SKY",
        "x-skyott-proposition": "SKYQ",
        "User-Agent": "Eldoret/1.0",
    })
    result = {}
    try:
        with urllib.request.urlopen(req, timeout=8) as response:
            data = json.loads(response.read().decode("utf-8", errors="replace"))
        events = []
        for block in data.get("schedule", []):
            events.extend(block.get("events", []))
        events.sort(key=lambda e: int(e.get("st", 0)))
        now_ts = int(now.timestamp())
        current_index = None
        for i, event in enumerate(events):
            start = int(event.get("st", 0))
            duration = int(event.get("d", 0))
            if start <= now_ts < start + duration:
                current_index = i
                result.update({
                    "programme": event.get("t"),
                    "synopsis": event.get("sy"),
                    "start": datetime.fromtimestamp(start, tz=timezone.utc).isoformat(),
                    "end": datetime.fromtimestamp(start + duration, tz=timezone.utc).isoformat(),
                    "programmeuuid": event.get("programmeuuid"),
                })
                break
        if current_index is not None and current_index + 1 < len(events):
            nxt = events[current_index + 1]
            nstart = int(nxt.get("st", 0))
            nduration = int(nxt.get("d", 0))
            result["next"] = {
                "programme": nxt.get("t"),
                "synopsis": nxt.get("sy"),
                "start": datetime.fromtimestamp(nstart, tz=timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(nstart + nduration, tz=timezone.utc).isoformat(),
            }
    except Exception:
        pass
    return result

def sky_now_playing_v2():
    result = {"available": False, "live": False, "host": sky_q_host()}
    try:
        uri = sky_get_media_uri()
        result["uri"] = uri
        if uri.startswith("xsi://"):
            sid = int(uri[6:], 16)
            result.update({"available": True, "live": True, "sid": sid})
            services = sky_channel_list()
            service = next((s for s in services if str(s.get("sid")) == str(sid)), None)
            if service:
                result["channel"] = service.get("t")
                result["channelno"] = service.get("c")
                result["logo"] = sky_channel_logo_url(service)
                result["is_radio"] = str(service.get("sf", "")).lower() == "au"
            result.update(sky_epg_now_next(sid))
            return result
        if "pvr" in uri.lower():
            result.update({"available": True, "live": False, "playback": "recording"})
            return result
        if uri:
            result.update({"available": True, "live": False, "playback": uri})
            return result
        result["error"] = "Sky Q returned no current media URI"
    except Exception as exc:
        result["error"] = str(exc)
    return result

def sky_json(path):
    url = f"http://{SKY_Q_HOST}:{SKY_Q_JSON_PORT}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=3) as response:
        raw = response.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except Exception:
            return raw

def first_json(paths):
    last_error = None
    for path in paths:
        try:
            return path, sky_json(path)
        except Exception as exc:
            last_error = exc
    if last_error:
        raise last_error
    raise RuntimeError("No Sky Q endpoint paths supplied")

def dig(obj, *keys):
    cur = obj
    for key in keys:
        if isinstance(cur, dict):
            if key in cur:
                cur = cur[key]
                continue
            low = {str(k).lower(): v for k, v in cur.items()}
            if str(key).lower() in low:
                cur = low[str(key).lower()]
                continue
        return None
    return cur

def pick(obj, names):
    if not isinstance(obj, dict):
        return None
    low = {str(k).lower(): v for k, v in obj.items()}
    for name in names:
        if name in obj:
            return obj[name]
        if name.lower() in low:
            return low[name.lower()]
    return None

def sky_now_playing():
    result = {
        "available": True,
        "host": sky_q_host(),
        "json_port": SKY_Q_JSON_PORT,
        "power": None,
        "live": False,
        "channel": None,
        "channelno": None,
        "channel_image": None,
        "programme": None,
        "synopsis": None,
        "start": None,
        "end": None,
        "app": None,
        "debug": {},
    }

    try:
        ppath, power = first_json([
            "/as/system/status",
            "/as/system/information",
            "/as/system/device",
        ])
        result["debug"]["power_endpoint"] = ppath
        p = pick(power, ["powerState", "powerstate", "state", "standby", "active"])
        if isinstance(p, bool):
            result["power"] = "ON" if p else "STANDBY"
        elif p is not None:
            result["power"] = str(p)
    except Exception as exc:
        result["debug"]["power_error"] = str(exc)

    try:
        mpath, media = first_json([
            "/as/playback",
            "/as/playback/current",
            "/as/media",
            "/as/player",
            "/as/epg/current",
        ])
        result["debug"]["media_endpoint"] = mpath

        root = media
        if isinstance(media, dict):
            for key in ("current", "playback", "media", "programme", "program"):
                if isinstance(media.get(key), dict):
                    root = media[key]
                    break

        result["channel"] = pick(root, ["channelName", "channel", "serviceName", "servicename"])
        result["channelno"] = pick(root, ["channelNumber", "channelNo", "channelno", "lcn"])
        result["programme"] = pick(root, ["title", "programmeTitle", "programTitle", "name"])
        result["synopsis"] = pick(root, ["synopsis", "description", "shortDescription"])
        result["start"] = pick(root, ["startTime", "starttime", "start"])
        result["end"] = pick(root, ["endTime", "endtime", "end"])
        result["channel_image"] = pick(root, ["imageUrl", "image_url", "logo", "channelLogo"])

        live = pick(root, ["live", "isLive", "islive"])
        if isinstance(live, bool):
            result["live"] = live
        elif result["channel"]:
            result["live"] = True
    except Exception as exc:
        result["debug"]["media_error"] = str(exc)

    try:
        apath, app = first_json([
            "/as/apps/active",
            "/as/app/active",
            "/as/apps",
        ])
        result["debug"]["app_endpoint"] = apath
        if isinstance(app, dict):
            root = app
            if isinstance(app.get("active"), dict):
                root = app["active"]
            result["app"] = pick(root, ["title", "name", "appName"])
    except Exception as exc:
        result["debug"]["app_error"] = str(exc)

    if result["power"] is None and not result["channel"] and not result["programme"] and not result["app"]:
        result["available"] = False
        result["error"] = "Sky Q responded on neither known status nor playback endpoints"

    return result

def _agent_read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default

def _agent_write_json(path, value):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp=path+".new"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        pass

def build_remote_state():
    snapshot={"generated_at":datetime.now(timezone.utc).isoformat(),"hue":{}}
    # Hue: expose only room/group state and brightness, never bridge credentials.
    for bridge_name,group_ids in {"house":["1","2","3","4","5","6","7","8","9","10"],
                                  "utility":["1","2","3","4","5","84","85"]}.items():
        for group in group_ids:
            key=bridge_name+":"+group
            try:
                raw=json.loads(hue_get(bridge_name,"groups/"+group).decode("utf-8",errors="replace"))
                snapshot["hue"][key]={
                    "state":{"any_on":bool((raw.get("state") or {}).get("any_on"))},
                    "action":{"bri":(raw.get("action") or {}).get("bri")}
                }
            except Exception:
                pass
    try:
        sky=sky_gentle_now()
        snapshot["sky_now"]={k:sky.get(k) for k in ("available","live","channel","channelno","logo",
            "is_radio","programme","start","end","synopsis","programmeuuid","playback") if k in sky}
    except Exception:
        snapshot["sky_now"]={"available":False}
    try:
        p=printer_status()
        snapshot["printer"]={k:p.get(k) for k in ("online","model","state","ink","detail") if k in p}
    except Exception:
        snapshot["printer"]={"online":False}
    try:
        ps=playstation_status()
        snapshot["playstation"]={k:ps.get(k) for k in ("online","host_type","host_name","system_version",
            "running_app_name","running_app_titleid","status_code","detail") if k in ps}
    except Exception:
        snapshot["playstation"]={"online":False}
    try:
        reg=_registry_load()
        snapshot["summary"]={
            "lg_tv_count":len([k for k in reg if k.startswith("lg_tv_")]),
            "sky_q":bool(reg.get("sky_q")),
            "printer":bool(reg.get("epson_et3850")),
            "playstation":bool(reg.get("playstation")),
            "velux":bool(reg.get("velux_gateway"))
        }
    except Exception:
        snapshot["summary"]={}
    return snapshot

def publish_remote_state():
    try:
        payload=json.dumps(build_remote_state(),ensure_ascii=False).encode("utf-8")
        req=urllib.request.Request(REMOTE_STATE_URL,data=payload,
            headers={"User-Agent":"Eldoret-Remote/1.0","Content-Type":"text/plain"},method="POST")
        with urllib.request.urlopen(req,timeout=12) as response:
            response.read()
        return True
    except Exception:
        return False

def remote_state_loop():
    while True:
        try:
            publish_remote_state()
        except Exception:
            pass
        time.sleep(60)

def sanitise_agent_result(value):
    task=str(value.get("task") or "")
    result=value.get("result") or {}
    safe={"status":value.get("status"),"task":task,"task_id":value.get("task_id"),
          "finished_at":value.get("finished_at"),"error":value.get("error")}
    if task=="engineering_runtime":
        safe["result"]={"checked_at":result.get("checked_at"),"connector_running":result.get("connector_running"),
                        "uptime_seconds":result.get("uptime_seconds"),"sky_passive_isolation":result.get("sky_passive_isolation"),
                        "pioneer_host":result.get("pioneer_host"),
                        "pioneer_state":(result.get("pioneer_monitor") or {}).get("live",{}).get("state")}
    elif task=="engineering_pioneer":
        safe["result"]={k:result.get(k) for k in ("connected","power","volume","mute","input","error","checked_at")}
    elif task=="engineering_snapshot":
        runtime=result.get("runtime") or {}
        pioneer=result.get("pioneer") or {}
        safe["result"]={"checked_at":runtime.get("checked_at"),
                        "uptime_seconds":runtime.get("uptime_seconds"),
                        "sky_passive_isolation":runtime.get("sky_passive_isolation"),
                        "pioneer":{k:pioneer.get(k) for k in ("connected","power","volume","mute","input","error")}}
    elif task=="printer_status":
        safe["result"]={k:result.get(k) for k in ("online","model","state","ink","detail","sources") if k in result}
    elif task=="playstation_status":
        safe["result"]={k:result.get(k) for k in ("online","host_type","host_name","system_version",
            "running_app_name","running_app_titleid","status_code","detail") if k in result}
    elif task=="lg_status":
        safe["result"]={k:result.get(k) for k in ("online","webos_plain","webos_tls","paired","detail") if k in result}
    elif task=="velux_status":
        safe["result"]={k:result.get(k) for k in ("online","klf200_api","http","https","detail") if k in result}
    elif task=="velux_discovery":
        devices=result.get("devices") or []
        safe["result"]={"device_count":len(devices),"candidates":[d.get("candidate") for d in devices if d.get("candidate")]}
    elif task=="homekit_discovery":
        services=result.get("services") or []
        safe["result"]={"service_count":len(services),"detail":"HomeKit services detected" if services else "No HomeKit service detected"}
    elif task=="network_inventory":
        devices=result.get("devices") or []
        safe["result"]={"device_count":len(devices),"candidates":[d.get("candidates") for d in devices if d.get("candidates")]}
    elif task=="network_status":
        devices=result.get("devices") or []
        safe["result"]={"online_count":sum(1 for d in devices if d.get("online")),"device_count":len(devices)}
    elif task=="infrastructure_status":
        targets=result.get("targets") or []
        safe["result"]={"online_count":sum(1 for d in targets if d.get("online")),"target_count":len(targets)}
    elif task=="remote_access_start":
        safe["result"]={"online":bool(result.get("online")),"tunnel_url":result.get("tunnel_url")}
    elif task=="discover_devices":
        found=result.get("found") or {}
        safe["result"]={"devices_found":sorted(found.keys()),
                        "lg_tv_count":len(found.get("lg_tvs") or []),
                        "sky_q":bool(found.get("sky_q")),
                        "printer":bool(found.get("epson_et3850")),
                        "playstation":bool(found.get("playstation")),
                        "velux":bool(found.get("velux_gateway"))}
    else:
        safe["result"]={"detail":"Task completed"}
    return safe

def agent_relay(value):
    # One-way diagnostic relay. Only sanitised allow-listed results are sent.
    try:
        payload=json.dumps(sanitise_agent_result(value), ensure_ascii=False).encode("utf-8")
        req=urllib.request.Request(
            AGENT_RELAY_URL,
            data=payload,
            headers={"User-Agent":"Eldoret-Agent/1.0","Content-Type":"text/plain"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            response.read()
        return True
    except Exception:
        return False


# Read-only engineering tasks. No shell, sudo, process restarts, or secrets.
def engineering_runtime_diagnostics():
    uptime=None
    try:
        with open("/proc/uptime",encoding="ascii") as f:
            uptime=int(float(f.readline().split()[0]))
    except (OSError,ValueError,IndexError):
        pass
    return {
        "checked_at":datetime.now(timezone.utc).isoformat(),
        "host":socket.gethostname(),
        "uptime_seconds":uptime,
        "python":platform.python_version(),
        "connector_running":True,
        "active_threads":threading.active_count(),
        "sky_passive_isolation":SKY_PASSIVE_ISOLATION,
        "pioneer_host":PIONEER_HOST,
        "pioneer_monitor":pioneer_monitor_summary(),
        "disruptive_actions_enabled":False,
        "credential_access_enabled":False,
    }

def engineering_pioneer_diagnostics():
    result=pioneer_status()
    result["monitor"]=pioneer_monitor_summary()
    result["checked_at"]=datetime.now(timezone.utc).isoformat()
    return result

def engineering_snapshot():
    return {"runtime":engineering_runtime_diagnostics(),
            "pioneer":engineering_pioneer_diagnostics()}

def run_agent_task(task):
    # Deliberately allow-listed. No arbitrary commands or shell execution.
    allowed = {
        "engineering_runtime": engineering_runtime_diagnostics,
        "engineering_pioneer": engineering_pioneer_diagnostics,
        "engineering_snapshot": engineering_snapshot,
        "network_inventory": lan_inventory,
        "network_status": network_status,
        "velux_discovery": velux_active_discovery,
        "homekit_discovery": homekit_discovery,
        "velux_status": velux_status,
        "lg_status": lg_tv_status,
        "playstation_status": playstation_status,
        "printer_status": printer_status,
        "infrastructure_status": infrastructure_status,
        "discover_devices": discover_known_devices,
        "remote_access_start": start_remote_tunnel,
    }
    fn=allowed.get(task)
    if not fn:
        raise ValueError("Task is not in the Eldoret allow-list")
    return fn()

def agent_loop():
    global AGENT_RESULT
    state=_agent_read_json(AGENT_STATE_FILE, {})
    last_id=state.get("last_task_id")
    while True:
        try:
            req=urllib.request.Request(AGENT_TASK_URL, headers={"User-Agent":"Eldoret-Agent/1.0","Cache-Control":"no-cache"})
            with urllib.request.urlopen(req, timeout=10) as response:
                job=json.loads(response.read().decode("utf-8",errors="replace"))
            task_id=str(job.get("id") or "")
            task=str(job.get("task") or "")
            if task_id and task and task_id != last_id:
                AGENT_RESULT={"status":"running","task":task,"task_id":task_id,"result":None,"error":None,
                              "finished_at":None}
                _agent_write_json(AGENT_RESULTS_FILE, AGENT_RESULT)
                try:
                    result=run_agent_task(task)
                    AGENT_RESULT={"status":"complete","task":task,"task_id":task_id,"result":result,"error":None,
                                  "finished_at":datetime.now(timezone.utc).isoformat()}
                except Exception as exc:
                    AGENT_RESULT={"status":"error","task":task,"task_id":task_id,"result":None,"error":str(exc)[:500],
                                  "finished_at":datetime.now(timezone.utc).isoformat()}
                _agent_write_json(AGENT_RESULTS_FILE, AGENT_RESULT)
                agent_relay(AGENT_RESULT)
                last_id=task_id
                _agent_write_json(AGENT_STATE_FILE, {"last_task_id":last_id})
        except Exception:
            saved=_agent_read_json(AGENT_RESULTS_FILE, None)
            if saved:
                AGENT_RESULT=saved
        time.sleep(30)

def _remote_request(handler):
    return bool(handler.headers.get("CF-Connecting-IP") or handler.headers.get("CF-Ray"))

def _remote_session_ok(handler):
    if not _remote_request(handler):
        return True
    cookie=handler.headers.get("Cookie","")
    for part in cookie.split(";"):
        if part.strip().startswith("eldoret_session="):
            token=part.strip().split("=",1)[1]
            return token in REMOTE_SESSIONS
    return False

def _verify_remote_password(password):
    try:
        salt=base64.b64decode(REMOTE_LOGIN_SALT)
        expected=base64.b64decode(REMOTE_LOGIN_HASH)
        actual=hashlib.scrypt(password.encode("utf-8"),salt=salt,n=2**14,r=8,p=1,dklen=32)
        return secrets.compare_digest(actual,expected)
    except Exception:
        return False

def _login_page(error=False):
    msg='<p class="err">That password was not accepted.</p>' if error else ''
    return """<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="theme-color" content="#0b1018"><title>Eldoret Login</title><style>
    *{box-sizing:border-box}body{margin:0;min-height:100dvh;background:radial-gradient(circle at 20% 0,#1a2942,#0b1018 42%,#070b11);color:#f4f7fb;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;display:grid;place-items:center;padding:24px}
    .card{width:min(440px,100%);background:#121a26;border:1px solid #2a3748;border-radius:28px;padding:30px;box-shadow:0 24px 70px #0008}.ey{color:#73d5b1;letter-spacing:.18em;font-weight:900;font-size:12px}.mark{width:72px;height:72px;border-radius:22px;background:linear-gradient(135deg,#73d5b1,#786fe9);display:grid;place-items:center;font-size:38px;margin-bottom:22px}h1{margin:5px 0 8px;font-size:34px}p{color:#9eacbe;line-height:1.5}.err{color:#ff9c9c}input{width:100%;min-height:58px;border:1px solid #36475e;border-radius:16px;background:#0b111a;color:white;padding:0 16px;font-size:18px;margin:12px 0}button{width:100%;min-height:58px;border:0;border-radius:16px;background:#73d5b1;color:#07120e;font-size:17px;font-weight:900}small{display:block;color:#77869a;margin-top:16px;text-align:center}</style></head><body><form class="card" method="post" action="/login"><div class="mark">E</div><div class="ey">ELDORET</div><h1>Welcome home</h1><p>Enter your Eldoret password to connect securely to Donkey.</p>"""+msg+"""<input name="password" type="password" autocomplete="current-password" placeholder="Eldoret password" autofocus><button type="submit">Open Eldoret</button><small>Remote access · encrypted HTTPS tunnel</small></form></body></html>"""

def start_remote_tunnel():
    global REMOTE_TUNNEL_PROCESS
    saved=_agent_read_json(REMOTE_TUNNEL_FILE,{})
    if REMOTE_TUNNEL_PROCESS is not None and REMOTE_TUNNEL_PROCESS.poll() is None and saved.get("url"):
        return {"online":True,"tunnel_url":saved.get("url"),"reused":True}
    arch=platform.machine().lower()
    asset="cloudflared-linux-arm64" if arch in ("aarch64","arm64") else "cloudflared-linux-amd64"
    folder=os.path.expanduser("~/eldoret-connector")
    os.makedirs(folder,exist_ok=True)
    binary=os.path.join(folder,"cloudflared")
    if not os.path.exists(binary):
        url="https://github.com/cloudflare/cloudflared/releases/latest/download/"+asset
        req=urllib.request.Request(url,headers={"User-Agent":"Eldoret/1.0"})
        with urllib.request.urlopen(req,timeout=45) as r, open(binary,"wb") as f:
            while True:
                chunk=r.read(1024*1024)
                if not chunk: break
                f.write(chunk)
        os.chmod(binary,0o755)
    proc=subprocess.Popen([binary,"tunnel","--url","http://127.0.0.1:8765","--no-autoupdate"],
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,text=True,bufsize=1)
    REMOTE_TUNNEL_PROCESS=proc
    deadline=time.time()+25
    tunnel_url=None
    while time.time()<deadline:
        line=proc.stderr.readline()
        if not line:
            if proc.poll() is not None: break
            time.sleep(.1); continue
        import re
        m=re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com",line)
        if m:
            tunnel_url=m.group(0); break
    if not tunnel_url:
        try: proc.terminate()
        except Exception: pass
        REMOTE_TUNNEL_PROCESS=None
        raise RuntimeError("Cloudflare quick tunnel did not return a URL")
    data={"url":tunnel_url,"started_at":datetime.now(timezone.utc).isoformat()}
    _agent_write_json(REMOTE_TUNNEL_FILE,data)
    return {"online":True,"tunnel_url":tunnel_url,"reused":False}

# Temporary, cart-only browser sessions. Audio never passes through this relay.
PLAYOUT_ORIGIN = "https://nickabull.github.io"
PLAYOUT_LOCK = threading.Lock()
PLAYOUT_SESSIONS = {}

def playout_http(handler):
    origin = handler.headers.get("Origin", "")
    def reply(code, data):
        body = json.dumps(data).encode()
        handler.send_response(code)
        if origin == PLAYOUT_ORIGIN:
            handler.send_header("Access-Control-Allow-Origin", PLAYOUT_ORIGIN)
            handler.send_header("Vary", "Origin")
            handler.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            handler.send_header("Access-Control-Allow-Private-Network", "true")
        handler.send_header("Content-Type", "application/json")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    if origin != PLAYOUT_ORIGIN:
        reply(403, {"error": "Open the Eldoret playout website to pair"}); return
    if handler.command == "OPTIONS":
        reply(200, {"ok": True}); return
    if handler.command not in ("GET", "POST"):
        reply(405, {"error": "Unsupported method"}); return
    try:
        length = int(handler.headers.get("Content-Length", "0"))
        if length < 0 or length > 16384:
            reply(413, {"error": "Message too large"}); return
        payload = json.loads(handler.rfile.read(length) or b"{}") if handler.command == "POST" else {}
        if not isinstance(payload, dict):
            raise ValueError("Expected an object")
    except (ValueError, UnicodeError):
        reply(400, {"error": "Invalid message"}); return
    path = urllib.parse.urlparse(handler.path).path
    now = time.monotonic()
    with PLAYOUT_LOCK:
        expired = [sid for sid, s in PLAYOUT_SESSIONS.items() if now-s["created"] > 43200 or now-s["heartbeat"] > 300]
        for sid in expired:
            del PLAYOUT_SESSIONS[sid]
        if path == "/api/playout/session" and handler.command == "POST":
            # Pairing can only be enabled through Donkey's loopback interface.
            host = handler.headers.get("Host", "").split(":")[0]
            if handler.client_address[0] not in ("127.0.0.1", "::1") or host not in ("localhost", "127.0.0.1") or any(handler.headers.get(h) for h in ("Forwarded", "X-Forwarded-For", "X-Forwarded-Host", "CF-Connecting-IP")):
                reply(403, {"error": "Enable hosting on Donkey using localhost"}); return
            if len(PLAYOUT_SESSIONS) >= 8:
                reply(409, {"error": "Too many sessions; wait five minutes and retry"}); return
            sid = secrets.token_urlsafe(12)
            host_key, control_key = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            PLAYOUT_SESSIONS[sid] = {"created": now, "heartbeat": now, "state": None,
                "host_key": host_key, "control_key": control_key, "commands": [], "seen": set()}
            reply(201, {"session": sid, "hostKey": host_key, "controlKey": control_key}); return
        parts = path.strip("/").split("/")
        if len(parts) != 4 or parts[:2] != ["api", "playout"]:
            reply(404, {"error": "Unknown playout route"}); return
        sid, action = parts[2:]
        session = PLAYOUT_SESSIONS.get(sid)
        token = handler.headers.get("Authorization", "")
        token = token[7:] if token.startswith("Bearer ") else ""
        if not session:
            reply(404, {"error": "Pairing ended; create a new link on Donkey"}); return
        host_auth = secrets.compare_digest(token, session["host_key"])
        control_auth = secrets.compare_digest(token, session["control_key"])
        if not host_auth and not control_auth:
            reply(401, {"error": "Invalid pairing key"}); return
        if action == "end" and handler.command == "POST" and host_auth:
            del PLAYOUT_SESSIONS[sid]
            reply(200, {"ok": True}); return
        if action == "host" and handler.command == "POST" and host_auth:
            raw_carts, bank = payload.get("carts"), payload.get("bank")
            if type(bank) is not int or not 0 <= bank < 4 or not isinstance(raw_carts, list) or len(raw_carts) != 3:
                reply(400, {"error": "Invalid host state"}); return
            carts = []
            for item in raw_carts:
                if not isinstance(item, dict):
                    reply(400, {"error": "Invalid cart state"}); return
                try:
                    duration, position = float(item.get("duration", 0)), float(item.get("position", 0))
                    if not (0 <= duration <= 86400 and 0 <= position <= 86400):
                        raise ValueError()
                except (ValueError, TypeError, OverflowError):
                    reply(400, {"error": "Invalid cart timing"}); return
                carts.append({"title": str(item.get("title", ""))[:240], "artist": str(item.get("artist", ""))[:240],
                    "loaded": item.get("loaded") is True, "playing": item.get("playing") is True,
                    "duration": duration, "position": position})
            session["heartbeat"] = now
            session["state"] = {"bank": bank, "carts": carts}
            commands = [c for c in session["commands"] if now-c["queued"] <= 2 and c["bank"] == bank]
            session["commands"] = []
            reply(200, {"commands": [{k:v for k,v in c.items() if k != "queued"} for c in commands]}); return
        if action == "state" and handler.command == "GET" and control_auth:
            age = now-session["heartbeat"]
            reply(200, {"online": session["state"] is not None and age <= 3, "ageMs": round(age*1000),
                "state": session["state"]}); return
        if action == "command" and handler.command == "POST" and control_auth:
            state = session["state"]
            if not state or now-session["heartbeat"] > 3:
                reply(409, {"error": "Donkey is offline; no command queued"}); return
            slot, bank, name, command_id = payload.get("slot"), payload.get("bank"), payload.get("action"), payload.get("id")
            if type(slot) is not int or not 0 <= slot < 3 or type(bank) is not int or bank != state["bank"] or name not in ("start", "stop") or not isinstance(command_id, str) or not 8 <= len(command_id) <= 80:
                reply(400, {"error": "Invalid cart command or bank changed"}); return
            if name == "start" and not state["carts"][slot]["loaded"]:
                reply(409, {"error": "Load audio into this cart on Donkey first"}); return
            if command_id in session["seen"]:
                reply(200, {"ok": True, "duplicate": True}); return
            if len(session["commands"]) >= 20 or len(session["seen"]) >= 10000:
                reply(429, {"error": "Command limit reached; reconnect"}); return
            session["seen"].add(command_id)
            session["commands"].append({"id": command_id, "action": name, "slot": slot, "bank": bank, "queued": now})
            reply(202, {"ok": True}); return
        reply(403, {"error": "Not permitted for this pairing key"})


# Compact home briefing. External reads are cached independently of local controls.
HOME_BRIEFING_CACHE = {}
HOME_BRIEFING_LOCK = threading.Lock()

def _home_cached(key, ttl, read):
    # Keep failures cached briefly too, so a disconnected service is not hammered.
    with HOME_BRIEFING_LOCK:
        cached = HOME_BRIEFING_CACHE.get(key)
        if cached and time.monotonic() - cached["at"] < cached["ttl"]:
            return cached["value"]
    try:
        value = read()
        value.update(available=True, checked_at=datetime.now(timezone.utc).isoformat())
        cache_for = ttl
    except Exception:
        value = {"available": False, "message": "Reading temporarily unavailable."}
        cache_for = 60
    with HOME_BRIEFING_LOCK:
        if len(HOME_BRIEFING_CACHE) > 100:
            HOME_BRIEFING_CACHE.clear()
        HOME_BRIEFING_CACHE[key] = {"at": time.monotonic(), "ttl": cache_for, "value": value}
    return value

def _home_external(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Eldoret-Home/1.0"})
    with urllib.request.urlopen(req, timeout=7) as response:
        return response.read(1000000)

def home_news():
    def read():
        root = ET.fromstring(_home_external("https://feeds.bbci.co.uk/news/rss.xml"))
        for item in root.findall("./channel/item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            url = urllib.parse.urlparse(link)
            if title and url.scheme == "https" and url.hostname in ("bbc.co.uk", "www.bbc.co.uk", "bbc.com", "www.bbc.com"):
                return {"title": title, "url": link, "published_at": item.findtext("pubDate"), "source": "BBC News"}
        raise ValueError("No BBC headline")
    return _home_cached("news", 300, read)

def home_locations(name):
    name = name.strip()[:80]
    if len(name) < 2:
        return {"available": False, "results": []}
    def read():
        params = urllib.parse.urlencode({"name": name, "count": 6, "language": "en", "format": "json", "countryCode": "GB"})
        data = json.loads(_home_external("https://geocoding-api.open-meteo.com/v1/search?" + params))
        results = [{k: x.get(k) for k in ("name", "admin1", "admin2", "country", "latitude", "longitude")}
                   for x in data.get("results", []) if x.get("country_code") == "GB"]
        return {"results": results}
    return _home_cached("location:" + name.casefold(), 86400, read)

def home_weather(latitude, longitude):
    try:
        lat, lon = float(latitude), float(longitude)
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("Invalid coordinates")
    except (ValueError, TypeError):
        return {"available": False, "message": "Choose your weather location."}
    def read():
        params = urllib.parse.urlencode({"latitude": lat, "longitude": lon,
            "current": "temperature_2m,weather_code", "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
            "forecast_days": 1, "timezone": "Europe/London"})
        data = json.loads(_home_external("https://api.open-meteo.com/v1/forecast?" + params))
        current, daily = data["current"], data["daily"]
        return {"temperature": current["temperature_2m"], "weather_code": current["weather_code"],
            "high": daily["temperature_2m_max"][0], "low": daily["temperature_2m_min"][0],
            "rain_chance": daily["precipitation_probability_max"][0], "forecast_at": current["time"], "source": "Open-Meteo"}
    return _home_cached("weather:" + str(round(lat, 3)) + ":" + str(round(lon, 3)), 900, read)

# VELUX HAP is strictly read-only until supervised rain-safe window tests are completed.
# The local script uses isolated aiohomekit credentials; never return or log its JSON key file.
_VELUX_READ_CACHE = {"at": 0.0, "data": None}
_VELUX_READ_LOCK = threading.Lock()

def velux_homekit_readonly():
    with _VELUX_READ_LOCK:
        now = time.monotonic()
        if _VELUX_READ_CACHE["data"] is not None and now - _VELUX_READ_CACHE["at"] < 20:
            return dict(_VELUX_READ_CACHE["data"])
        python_bin = os.path.expanduser("~/velux-homekit-venv/bin/python")
        script = os.path.expanduser("~/eldoret-connector/velux-readonly.py")
        if not os.path.isfile(python_bin) or not os.path.isfile(script):
            return {"connected": False, "mode": "read-only", "climate": None,
                    "windows": [], "error": "VELUX local reader not installed on Bulldog"}
        try:
            p = subprocess.run([python_bin, script], capture_output=True, text=True,
                               timeout=18, check=False)
            if p.returncode != 0:
                raise RuntimeError("Local VELUX reader returned an error")
            data = json.loads(p.stdout)
            if not isinstance(data, dict):
                raise ValueError("Invalid local VELUX response")
        except (subprocess.SubprocessError, ValueError, OSError, json.JSONDecodeError) as exc:
            data = {"connected": False, "mode": "read-only", "climate": None,
                    "windows": [], "error": "VELUX local read unavailable: " + type(exc).__name__}
        _VELUX_READ_CACHE.update(at=now, data=data)
        return dict(data)


# Manual, supervised VELUX HomeKit movement. No automatic comfort control.
VELUX_COMMAND_LOCK = threading.Lock()
VELUX_COMMAND_LAST = 0.0

def velux_manual_command(aid, action):
    global VELUX_COMMAND_LAST
    if type(aid) is not int or aid not in (3, 4) or action not in ("test_open", "open", "close"):
        return {"ok": False, "detail": "Unsupported window or action"}
    target = {"test_open": 10, "open": 100, "close": 0}[action]
    if not VELUX_COMMAND_LOCK.acquire(blocking=False):
        return {"ok": False, "detail": "Another VELUX command is still processing"}
    try:
        if time.monotonic() - VELUX_COMMAND_LAST < 5:
            return {"ok": False, "detail": "Please let previous movement settle"}
        state = velux_homekit_readonly()
        try:
            age_seconds = (datetime.now(timezone.utc) - datetime.fromisoformat(state["checked_at"])).total_seconds()
        except (KeyError, ValueError, TypeError):
            age_seconds = 999
        if not state.get("connected") or not -5 < age_seconds < 60:
            return {"ok": False, "detail": "No recent HomeKit reading; no command sent"}
        if not any(w.get("aid") == aid for w in state.get("windows", [])):
            return {"ok": False, "detail": "Window not detected in HomeKit"}
        python_bin = os.path.expanduser("~/velux-homekit-venv/bin/python")
        script = os.path.expanduser("~/eldoret-connector/velux-window-command.py")
        if not os.path.isfile(python_bin) or not os.path.isfile(script):
            return {"ok": False, "detail": "VELUX manual writer not installed on Bulldog"}
        VELUX_COMMAND_LAST = time.monotonic()
        try:
            result = subprocess.run([python_bin, script, str(aid), str(target)],
                capture_output=True, text=True, timeout=20, check=False)
            if result.returncode:
                raise RuntimeError("VELUX writer returned an error")
            parsed = json.loads(result.stdout)
            if not isinstance(parsed, dict) or type(parsed.get("ok")) is not bool:
                raise ValueError("Bad writer result")
            if parsed["ok"]:
                with _VELUX_READ_LOCK:
                    _VELUX_READ_CACHE.update(at=0, data=None)
            return parsed
        except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired):
            return {"ok": False, "detail": "Command outcome unknown; inspect window physically before retrying"}
    finally:
        VELUX_COMMAND_LOCK.release()


# Pioneer XC-HM82D-K - manually initiated LAN control only.
PIONEER_HOST = os.environ.get("PIONEER_HOST", "10.0.0.78")
PIONEER_PORT = 8102
PIONEER_LOCK = threading.Lock()
PIONEER_LAST_COMMAND = 0.0
PIONEER_COMMANDS = {"volume_up":"VU", "volume_down":"VD", "mute_on":"MO",
                    "mute_off":"MF", "power_off":"PF", "power_on":"PO",
                    "source_next":"FU", "source_tv_test":"59FN", "source_studio_test":"51FN"}

def pioneer_exchange(command, timeout=1.5):
    with socket.create_connection((PIONEER_HOST,PIONEER_PORT), timeout=timeout) as sock:
        sock.settimeout(timeout)
        sock.sendall((command + "\r").encode("ascii"))
        try:
            return sock.recv(256).decode("ascii", errors="replace").strip()
        except socket.timeout:
            return ""

def pioneer_status():
    # One manual TCP session for all queries. The XC-HM82 may temporarily refuse
    # a second connection opened immediately after the first has closed.
    # No device writes or background status polling; never retry automatically.
    result={"host":PIONEER_HOST,"connected":False,"power":None,
            "volume":None,"mute":None,"input":None,
            "checked_at":datetime.now(timezone.utc).isoformat(),
            "query_results":[],"connection_mode":"single_socket"}
    if not PIONEER_LOCK.acquire(blocking=False):
        result["error"]="Another Pioneer request is in progress"
        return result
    try:
        try:
            sock=socket.create_connection((PIONEER_HOST,PIONEER_PORT),timeout=1.5)
        except (OSError,ValueError) as exc:
            result["error"]="Pioneer connection failed: "+type(exc).__name__
            result["query_results"].append({"field":"connection","status":"connection_failed",
                                             "error":type(exc).__name__})
            return result
        with sock:
            sock.settimeout(1.5)
            # Makefile preserves framing even if TCP returns partial lines.
            with sock.makefile("rb") as stream:
                for command,key,prefix in (("?P","power","PWR"),("?V","volume","VOL"),
                                           ("?M","mute","MUT"),("?F","input","FN")):
                    started=time.monotonic()
                    try:
                        sock.sendall((command+"\r").encode("ascii"))
                        raw=stream.readline(256)
                        reply=raw.decode("ascii",errors="replace").strip() if raw else ""
                    except (OSError,ValueError) as exc:
                        result["query_results"].append({
                            "field":key,"status":"socket_failed",
                            "error":type(exc).__name__,
                            "elapsed_ms":round((time.monotonic()-started)*1000)})
                        result["error"]="Pioneer "+key+" check failed: "+type(exc).__name__
                        break
                    item={"field":key,"status":"no_reply" if not reply else "unexpected_reply",
                          "elapsed_ms":round((time.monotonic()-started)*1000)}
                    if key=="power" and reply.startswith("PWR"):
                        result["connected"]=True
                        result[key]="On" if reply=="PWR0" else ("Standby" if reply=="PWR2" else reply)
                        item["status"]="ok"
                    elif reply.startswith(prefix):
                        result["connected"]=True
                        code=reply[len(prefix):]
                        result[key]=("Muted" if code=="0" else "Not muted") if key=="mute" and code in ("0","1") else code
                        item["status"]="ok"
                    result["query_results"].append(item)
                    if item["status"]!="ok":
                        result["error"]="Pioneer "+key+" query returned "+item["status"]
                        break
        return result
    finally:
        PIONEER_LOCK.release()


def pioneer_connection_diagnostics():
    """User-triggered bounded checks. Do not send Pioneer control commands."""
    result={"host":PIONEER_HOST,"checked_at":datetime.now(timezone.utc).isoformat(),
            "ping":pioneer_monitor_summary().get("live",{}),
            "control_port":8102,"control_port_open":False,
            "web_port_open":False,"power_query":"not_sent"}
    for port,key in ((8102,"control_port_open"),(80,"web_port_open")):
        try:
            with socket.create_connection((PIONEER_HOST,port),timeout=1.2):
                result[key]=True
        except OSError as exc:
            result[key+"_error"]=type(exc).__name__
    result["diagnosis"]=("Control port accepts connections" if result["control_port_open"]
                         else "No TCP control connection: receiver may be rebooting, in standby, or rejecting port 8102")
    return result

def pioneer_control(action):
    global PIONEER_LAST_COMMAND
    if action not in PIONEER_COMMANDS:
        return {"ok":False,"error":"Unsupported command"}
    if not PIONEER_LOCK.acquire(blocking=False):
        return {"ok":False,"error":"Receiver busy"}
    try:
        now=time.monotonic()
        if now-PIONEER_LAST_COMMAND<1.2:
            return {"ok":False,"error":"Please wait before sending another command"}
        PIONEER_LAST_COMMAND=now
        reply=pioneer_exchange(PIONEER_COMMANDS[action])
        return {"ok":True,"command":action,"reply":reply[:80],"host":PIONEER_HOST,
                "device_confirmed":False,
                "note":"Sent to control socket; check actual receiver input manually."}
    except (OSError, ValueError) as exc:
        return {"ok":False,"error":"Receiver connection failed: "+type(exc).__name__}
    finally:
        PIONEER_LOCK.release()


# Pioneer stability observation: ICMP only (never opens the control socket).
# A loss of ping is not proof of an amplifier reboot.
PIONEER_MONITOR_FILE = os.path.join(os.path.expanduser("~/eldoret-connector"),"pioneer-connectivity.jsonl")
PIONEER_MONITOR_LOCK = threading.Lock()
PIONEER_MONITOR_LIVE = {"state":"unknown","observed_at":None,"since":None,"host":PIONEER_HOST}
PIONEER_MONITOR_INTERVAL = 30

def pioneer_monitor_log(event):
    with PIONEER_MONITOR_LOCK:
        os.makedirs(os.path.dirname(PIONEER_MONITOR_FILE),exist_ok=True)
        with open(PIONEER_MONITOR_FILE,"a",encoding="utf-8") as out:
            out.write(json.dumps(event,separators=(",",":"))+"\n")

def pioneer_monitor_loop():
    previous=None
    misses=0
    successes=0
    while True:
        now=datetime.now(timezone.utc).isoformat()
        try:
            check=subprocess.run(["ping","-n","-c","1","-W","1",PIONEER_HOST],
                                 capture_output=True,timeout=3,check=False)
            alive=check.returncode==0
        except (OSError,subprocess.TimeoutExpired):
            alive=False
        misses=0 if alive else misses+1
        successes=successes+1 if alive else 0
        confirmed=("reachable" if successes>=2 else "unreachable" if misses>=2 else None)
        with PIONEER_MONITOR_LOCK:
            PIONEER_MONITOR_LIVE["observed_at"]=now
            PIONEER_MONITOR_LIVE["last_probe_reachable"]=alive
        if confirmed and confirmed!=previous:
            event={"at":now,"state":confirmed,"host":PIONEER_HOST,
                   "method":"ICMP ping; two consecutive samples",
                   "note":"Connectivity transition, not verified power reboot"}
            pioneer_monitor_log(event)
            with PIONEER_MONITOR_LOCK:
                PIONEER_MONITOR_LIVE.update(state=confirmed,since=now)
            previous=confirmed
        time.sleep(PIONEER_MONITOR_INTERVAL)

def pioneer_monitor_summary():
    with PIONEER_MONITOR_LOCK:
        live=dict(PIONEER_MONITOR_LIVE)
        try:
            with open(PIONEER_MONITOR_FILE,"r",encoding="utf-8") as f:
                lines=f.readlines()[-200:]
        except OSError:
            lines=[]
    events=[]
    for line in lines:
        try:
            record=json.loads(line)
            if record.get("state") in ("reachable","unreachable"):
                events.append(record)
        except (ValueError,TypeError):
            continue
    return {"host":PIONEER_HOST,"live":live,"interval_seconds":PIONEER_MONITOR_INTERVAL,
            "events":events[-25:],
            "outages_observed":sum(e["state"]=="unreachable" for e in events),
            "note":"Ping reachability changes may reflect link/network changes. They do not prove a Pioneer reboot. Logging starts when this version is deployed."}


# Read-only myenergi Zappi telemetry. The secret exists ONLY in Bulldog's
# private ~/.config/eldoret/myenergi.json (0600), never in GitHub.
MYENERGI_CONFIG=os.path.expanduser("~/.config/eldoret/myenergi.json")
MYENERGI_CACHE={"updated":0,"value":None}
MYENERGI_LOCK=threading.Lock()

def _myenergi_config():
    import stat
    try:
        st=os.stat(MYENERGI_CONFIG)
        if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)!=0o600:
            raise ValueError("Myenergi config must be owned by Bulldog user with chmod 600")
        with open(MYENERGI_CONFIG,encoding="utf-8") as fp:
            conf=json.load(fp)
        if not isinstance(conf,dict) or not str(conf.get("gateway_serial","")).isdigit() or not str(conf.get("api_key","")):
            raise ValueError("Myenergi gateway serial/API key missing")
        return conf
    except FileNotFoundError:
        return None

def myenergi_decode_zappi(z):
    """Translate documented Zappi status fields; preserve absent fields as unknown."""
    states={1:"Paused",3:"Charging",5:"Complete"}
    plugs={"A":"Vehicle unplugged","B1":"Vehicle connected",
           "B2":"Waiting for vehicle","C1":"Vehicle ready",
           "C2":"Charging","F":"Fault"}
    modes={1:"Fast",2:"Eco",3:"Eco+",4:"Stopped"}
    sta=z.get("sta")
    pst=z.get("pst")
    mode=z.get("zmo")
    charging_state=("Charging" if pst=="C2" else
                    "Vehicle unplugged" if pst=="A" else
                    "Fault" if pst=="F" else
                    states.get(sta) if sta in (1,5) else
                    plugs.get(pst) or states.get(sta))
    def numeric(k):
        val=z.get(k)
        if isinstance(val,bool) or not isinstance(val,(int,float)) or not math.isfinite(val):
            return None
        return float(val)
    diversion=numeric("div")
    energy=numeric("che")
    return {"charging_state":charging_state,
            "charge_power_kw":round(diversion/1000,3) if diversion is not None else None,
            "session_energy_kwh":round(energy,3) if energy is not None else None,
            "charge_mode":modes.get(mode),
            "plug_status":plugs.get(pst),
            "raw_plug_code":pst,
            "power_source":"div (W)",
            "energy_source":"che (kWh)"}

def myenergi_status():
    conf=None
    try:
        conf=_myenergi_config()
    except (ValueError,OSError,TypeError) as exc:
        return {"configured":False,"mode":"read-only","error":"Local key file problem: "+type(exc).__name__,
                "detail":"Check Bulldog's private myenergi.json setup and permissions"}
    if conf is None:
        return {"configured":False,"mode":"read-only","charging_state":None,"charge_power_kw":None,
                "session_energy_kwh":None,"checked_at":None,
                "detail":"Awaiting gateway serial number and API key in Bulldog's private config. No network request sent."}
    now=time.monotonic()
    with MYENERGI_LOCK:
        if MYENERGI_CACHE["value"] is not None and now-MYENERGI_CACHE["updated"]<120:
            return dict(MYENERGI_CACHE["value"])
        try:
            import urllib.error
            # Only myenergi-owned HTTPS endpoints; no arbitrary cloud URL supplied by configuration.
            serial=str(conf["gateway_serial"])
            key=str(conf["api_key"])
            class NoRedirect(urllib.request.HTTPRedirectHandler):
                def redirect_request(self,*args,**kwargs):
                    return None
            # Stable documented community telemetry endpoint. Redirects blocked.
            import re
            # myenergi director advertises the account's current server shard.
            # Never follow redirects and never accept arbitrary hosts.
            server="https://s18.myenergi.net"
            try:
                director_req=urllib.request.Request("https://director.myenergi.net/",method="HEAD",
                    headers={"User-Agent":"Eldoret-Bulldog/1.0"})
                with urllib.request.build_opener(NoRedirect()).open(director_req,timeout=4) as d:
                    advertised=d.headers.get("x_myenergi-asn","")
                m=re.fullmatch(r"s?([0-9]{1,3})",advertised.strip().lower())
                if m:
                    server="https://s"+m.group(1)+".myenergi.net"
            except (OSError,urllib.error.URLError,ValueError):
                pass
            manager=urllib.request.HTTPPasswordMgrWithDefaultRealm()
            manager.add_password(None,server+"/",serial,key)
            auth=urllib.request.HTTPDigestAuthHandler(manager)
            opener=urllib.request.build_opener(auth,NoRedirect())
            req=urllib.request.Request(server+"/cgi-jstatus-Z",
                headers={"Accept":"application/json","User-Agent":"Eldoret-Bulldog/1.0"})
            with opener.open(req,timeout=8) as response:
                payload=json.loads(response.read(200000).decode("utf-8"))
            items=payload.get("zappi") if isinstance(payload,dict) else None
            if not isinstance(items,list) or not items or not isinstance(items[0],dict):
                raise ValueError("Unexpected Zappi status response; no zappi entries")
            z=items[0]
            # Documented API units: 'div' is diverted/charging power in W;
            # 'che' is charge energy in kWh. Absent values remain unknown.
            decoded=myenergi_decode_zappi(z)
            result={"configured":True,"connected":True,"mode":"read-only",
                    **decoded,
                    "raw_status_code":z.get("sta"),"raw_mode_code":z.get("zmo"),
                    "raw_diversion":z.get("div"),"raw_charge_energy":z.get("che"),
                    "checked_at":datetime.now(timezone.utc).isoformat(),
                    "device_time":str(z.get("dat",""))+" "+str(z.get("tim","")),
                    "detail":"Live myenergi status received. Decoded charging fields use documented API units; power is not necessarily the car battery's net power."}
            MYENERGI_CACHE.update(updated=now,value=result)
            return dict(result)
        except (OSError,ValueError,TypeError,urllib.error.URLError,KeyError,AttributeError) as exc:
            return {"configured":True,"connected":False,"mode":"read-only",
                    "charging_state":None,"charge_power_kw":None,
                    "session_energy_kwh":None,"error":type(exc).__name__,
                    "detail":"myenergi API request failed. Check account key, gateway serial or server availability; no charger changes made."}

# Bulldog Design Centre: local, draft-only design store.
# Saved JSON is independent of the deployed HTML and never executes code.
DESIGN_CENTRE_DIR=os.path.join(os.path.expanduser("~/eldoret-connector"),"design-centre")
DESIGN_CENTRE_LOCK=threading.RLock()
DESIGN_CENTRE_PRESETS={"wide":(1920,1080),"ipad":(1024,768),"pi":(800,480)}
DESIGN_CENTRE_TYPES={"text","button","panel","image"}

def design_centre_key(query):
    name=(query.get("name") or [""])[0]
    preset=(query.get("preset") or [""])[0]
    import re
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,39}",name) or preset not in DESIGN_CENTRE_PRESETS:
        raise ValueError("Invalid page name or layout preset")
    return name,preset

def design_centre_file(name,preset):
    return os.path.join(DESIGN_CENTRE_DIR,name+"-"+preset+".json")

def design_centre_validate(value,name,preset):
    if not isinstance(value,dict) or value.get("version")!=1 or value.get("page")!=name or value.get("preset")!=preset:
        raise ValueError("Invalid design metadata")
    width,height=DESIGN_CENTRE_PRESETS[preset]
    if (value.get("width"),value.get("height"))!=(width,height):
        raise ValueError("Invalid canvas dimensions")
    bg=value.get("background")
    import re
    if not isinstance(bg,str) or not re.fullmatch(r"#[0-9a-fA-F]{6}",bg):
        raise ValueError("Invalid background colour")
    elems=value.get("elements")
    if not isinstance(elems,list) or len(elems)>150:
        raise ValueError("Too many layers")
    names=set()
    for e in elems:
        if not isinstance(e,dict) or not {"id","type","name","label","src","x","y","w","h","size","radius","color","bg","opacity","locked","behaviour"}.issubset(set(e)) or not set(e).issubset({"id","type","name","label","src","x","y","w","h","size","radius","color","bg","opacity","locked","behaviour","font","bold","italic","underline","strike","align","scale","rotation","hidden"}):
            raise ValueError("Invalid layer structure")
        if "hidden" in e and not isinstance(e["hidden"],bool):
            raise ValueError("Invalid layer visibility")
        for key,minimum,maximum in (("scale",20,300),("rotation",-180,180)):
            if key in e and (not isinstance(e[key],(int,float)) or isinstance(e[key],bool) or not math.isfinite(e[key]) or not minimum<=e[key]<=maximum):
                raise ValueError("Invalid layer transform")
        if "font" in e and e["font"] not in ("Arial","Georgia","Verdana","Tahoma","Impact","Trebuchet MS","Courier New"):
            raise ValueError("Unsupported font")
        if "align" in e and e["align"] not in ("left","center","right"):
            raise ValueError("Invalid text alignment")
        for key in ("bold","italic","underline","strike"):
            if key in e and not isinstance(e[key],bool):
                raise ValueError("Invalid formatting flag")
        if not isinstance(e["id"],str) or not 1<=len(e["id"])<=100 or e["id"] in names:
            raise ValueError("Invalid or duplicate layer ID")
        names.add(e["id"])
        if e["type"] not in DESIGN_CENTRE_TYPES or not isinstance(e["locked"],bool):
            raise ValueError("Invalid element type or lock")
        for key,limit in (("name",160),("label",2000),("src",500),("behaviour",4000)):
            if not isinstance(e[key],str) or len(e[key])>limit:
                raise ValueError("Invalid layer text")
        # Images can only point to same-origin static assets; never external URLs.
        if e["src"] and (not re.fullmatch(r"/?[a-zA-Z0-9_./-]+",e["src"]) or ".." in e["src"]):
            raise ValueError("Artwork URL must be a local static asset path")
        for key in ("color","bg"):
            if not re.fullmatch(r"#[0-9a-fA-F]{6}",e[key]):
                raise ValueError("Invalid layer colour")
        if not all(isinstance(e[k],(int,float)) and not isinstance(e[k],bool) and math.isfinite(e[k]) for k in ("x","y","w","h","size","radius","opacity")):
            raise ValueError("Invalid layer dimension")
        if (e["x"]<0 or e["y"]<0 or e["w"]<20 or e["h"]<20 or e["x"]+e["w"]>width+1 or
            e["y"]+e["h"]>height+1 or not 8<=e["size"]<=500 or not 0<=e["radius"]<=1000 or not 0<=e["opacity"]<=100):
            raise ValueError("Element out of canvas bounds")
    return value

def design_centre_read(name,preset):
    path=design_centre_file(name,preset)
    with DESIGN_CENTRE_LOCK:
        try:
            with open(path,"r",encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None

def design_centre_save(name,preset,design):
    design_centre_validate(design,name,preset)
    path=design_centre_file(name,preset)
    with DESIGN_CENTRE_LOCK:
        os.makedirs(DESIGN_CENTRE_DIR,mode=0o700,exist_ok=True)
        tmp=path+".new"
        with open(tmp,"w",encoding="utf-8") as f:
            os.fchmod(f.fileno(),0o600)
            json.dump(design,f,ensure_ascii=False,separators=(",",":"))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp,path)
    return {"ok":True,"saved_at":datetime.now(timezone.utc).isoformat()}

# Nissan Ariya helper stays in a restricted local virtual environment.
# Cloud credentials live only in ~/.config/eldoret/nissan.json (0600).
NISSAN_BRIDGE=os.path.expanduser("~/eldoret-connector/nissan-bridge.py")
NISSAN_PYTHON=os.path.expanduser("~/nissan-test/venv/bin/python")
NISSAN_CACHE={"updated":0.0,"value":None}
NISSAN_LOCK=threading.Lock()

def _ariya_invoke(mode,payload=None):
    args=[NISSAN_PYTHON,NISSAN_BRIDGE,mode]
    run=subprocess.run(args,input=json.dumps(payload) if payload is not None else None,
                       text=True,capture_output=True,timeout=45,check=False,
                       env={**os.environ,"PYTHONUNBUFFERED":"1"})
    if run.returncode!=0:
        raise RuntimeError("Nissan helper failed")
    return json.loads(run.stdout)

# SmartThings refrigerator: private read-only API. Never proxy raw device status.
SMARTTHINGS_PRIVATE_FILE=os.path.expanduser("~/.config/eldoret/smartthings.json")
SMARTTHINGS_LOCK=threading.Lock()
SMARTTHINGS_CACHE={"expires":0.0,"value":None}

def smartthings_fridge_status():
    import stat
    import urllib.error
    from urllib.parse import quote
    checked=datetime.now(timezone.utc).isoformat()
    empty={"configured":False,"connected":False,"source":"SmartThings cloud",
           "mode":"read-only","checked_at":checked}
    with SMARTTHINGS_LOCK:
        now=time.monotonic()
        if SMARTTHINGS_CACHE["value"] is not None and now<SMARTTHINGS_CACHE["expires"]:
            return dict(SMARTTHINGS_CACHE["value"])
        try:
            st=os.stat(SMARTTHINGS_PRIVATE_FILE)
            if st.st_uid!=os.getuid() or stat.S_IMODE(st.st_mode)&0o077:
                raise ValueError("Private token permissions invalid")
            with open(SMARTTHINGS_PRIVATE_FILE,encoding="utf-8") as file:
                token=json.load(file).get("token")
            if not isinstance(token,str) or len(token)<16:
                raise ValueError("Token missing")
        except FileNotFoundError:
            return dict(empty,detail="SmartThings read-only token not installed on Bulldog.")
        except (OSError,ValueError,TypeError):
            return dict(empty,detail="SmartThings token file needs local attention.")
        try:
            base="https://api.smartthings.com/v1"
            headers={"Authorization":"Bearer "+token,"Accept":"application/json",
                     "User-Agent":"Eldoret-Bulldog/1.0"}
            def get(path):
                req=urllib.request.Request(base+path,headers=headers)
                with urllib.request.urlopen(req,timeout=12) as response:
                    raw=response.read(1024*1024+1)
                if len(raw)>1024*1024: raise ValueError("Unexpected large response")
                data=json.loads(raw)
                if not isinstance(data,dict): raise ValueError("Invalid response")
                return data
            devices=get("/devices").get("items",[])
            if not isinstance(devices,list): raise ValueError("Invalid list")
            found=next((d for d in devices if isinstance(d,dict)
                and "refrigerator" in (str(d.get("label") or "")+" "+str(d.get("name") or "")).lower()
                and isinstance(d.get("deviceId"),str)),None)
            if not found:
                result=dict(empty,configured=True,detail="No refrigerator in authorized device list.")
            else:
                raw=get("/devices/"+quote(found["deviceId"],safe="")+"/status")
                parts=raw.get("components") or {}
                def val(component,capability,attribute):
                    obj=parts.get(component,{}).get(capability,{}).get(attribute,{})
                    return obj.get("value") if isinstance(obj,dict) else None
                def numeric(v):
                    if type(v) in (int,float) and abs(v)<10000: return round(float(v),1)
                    return None
                fridge=numeric(val("cooler","temperatureMeasurement","temperature"))
                freezer=numeric(val("freezer","temperatureMeasurement","temperature"))
                doors={name:val(name,"contactSensor","contact") for name in ("cooler","freezer","cvroom")}
                doors={k:v for k,v in doors.items() if v in ("open","closed")}
                filter_state=val("main","custom.waterFilter","waterFilterStatus")
                filter_usage=numeric(val("main","custom.waterFilter","waterFilterUsage"))
                result={"configured":True,"connected":True,"source":"SmartThings cloud",
                    "mode":"read-only","checked_at":checked,"name":"Samsung Refrigerator",
                    "fridge_c":fridge,"freezer_c":freezer,
                    "flexzone_mode":val("cvroom","custom.fridgeMode","fridgeMode"),
                    "doors":doors,
                    "ice_maker":val("icemaker","switch","switch"),
                    "ice_maker_state":val("icemaker","samsungce.fridgeIcemakerOperatingState","operatingState"),
                    "power_cool":val("main","samsungce.powerCool","activated"),
                    "power_freeze":val("main","samsungce.powerFreeze","activated"),
                    "auto_fill":val("main","samsungce.autoFillPitcher","autoFillPitcher"),
                    "water_filter_status":filter_state if filter_state in ("replace","normal","good","ok") else None,
                    "water_filter_usage_percent":filter_usage}
            SMARTTHINGS_CACHE.update(value=result,expires=now+(120 if result.get("connected") else 30))
            return result
        except urllib.error.HTTPError as e:
            result=dict(empty,configured=True,detail=("SmartThings token rejected or expired" if e.code in (401,403)
                else "SmartThings status request failed"),http_status=e.code)
        except (OSError,ValueError,TypeError,KeyError):
            result=dict(empty,configured=True,detail="SmartThings temporarily unavailable.")
        SMARTTHINGS_CACHE.update(value=result,expires=now+30)
        return result

def ariya_status():
    with NISSAN_LOCK:
        now=time.monotonic()
        if NISSAN_CACHE["value"] is not None and now-NISSAN_CACHE["updated"]<120:
            return dict(NISSAN_CACHE["value"])
        if not os.path.isfile(NISSAN_BRIDGE):
            return {"configured":False,"connected":False,
                    "detail":"Nissan helper not yet installed on Bulldog."}
        try:
            result=_ariya_invoke("status")
            if isinstance(result,dict) and result.get("connected"):
                NISSAN_CACHE.update(updated=now,value=result)
            return result
        except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):
            return {"configured":True,"connected":False,
                    "detail":"Nissan service unavailable. Please retry later; no commands sent."}

def ariya_control(action,temperature_c):
    if action not in ("start","stop") or type(temperature_c)!=int or not 16<=temperature_c<=26:
        return {"ok":False,"detail":"Invalid climate request"}
    with NISSAN_LOCK:
        try:
            result=_ariya_invoke("control",{"action":action,"temperature_c":temperature_c})
            NISSAN_CACHE.update(updated=0.0,value=None)
            return result
        except (OSError,ValueError,RuntimeError,subprocess.TimeoutExpired):
            return {"ok":False,"detail":"Nissan climate command failed. Verify the car's actual state."}

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, data, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_OPTIONS(self):
        if urllib.parse.urlparse(self.path).path.startswith('/api/playout/'):
            playout_http(self); return
        self.send_error(404)

    def do_GET(self):
        if urllib.parse.urlparse(self.path).path.startswith('/api/playout/'):
            playout_http(self); return
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        if path == "/api/design-centre":
            if _remote_request(self): self.send_error(403); return
            try:
                name,preset=design_centre_key(query)
                self.send_bytes(json.dumps({"design":design_centre_read(name,preset)}).encode()); return
            except ValueError:
                self.send_error(400); return
        if path == "/api/smartthings/fridge/status":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(smartthings_fridge_status()).encode()); return
        if path == "/api/ariya/status":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(ariya_status()).encode()); return
        if path == "/api/zappi/status":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(myenergi_status()).encode()); return
        if path == "/api/pioneer/connection":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(pioneer_connection_diagnostics()).encode()); return
        if path == "/api/pioneer/monitor":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(pioneer_monitor_summary()).encode()); return
        if path == "/api/pioneer/status":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(pioneer_status()).encode()); return
        if path == "/api/studio/status":
            if _remote_request(self) and not _remote_session_ok(self):
                self.send_response(401); self.end_headers(); return
            try:
                self.send_bytes(json.dumps(studio_status()).encode())
            except Exception:
                self.send_bytes(json.dumps({"available":False,"channels":[],"detail":"Studio reading unavailable"}).encode())
            return
        if path == "/api/sky/isolation":
            with SKY_PASSIVE_LOCK: blocked=dict(SKY_PASSIVE_BLOCKED)
            self.send_bytes(json.dumps({"enabled":SKY_PASSIVE_ISOLATION,
                "detail":"Passive Sky Q reads suspended; manual remote and channel commands still available." if SKY_PASSIVE_ISOLATION else "Sky Q read endpoints active.",
                "gentle_readback":True,"blocked_get_counts":blocked}).encode())
            return
        if path == "/api/sky/now":
            if _remote_request(self) and not _remote_session_ok(self):
                self.send_response(401); self.end_headers(); return
            self.send_bytes(json.dumps(sky_gentle_now()).encode())
            return
        if SKY_PASSIVE_ISOLATION and path.startswith("/api/sky/") and path not in ("/api/sky/search","/api/sky/guide","/api/sky/guide-range","/api/sky/top-picks","/api/sky/sport-guide"):
            with SKY_PASSIVE_LOCK:
                SKY_PASSIVE_BLOCKED[path]=SKY_PASSIVE_BLOCKED.get(path,0)+1
            # Return safe offline states without touching Sky Q at all.
            result={"available":False,"live":False,"isolated":True,
                "detail":"Sky Q readback temporarily suspended to diagnose box freezes.",
                "error":"Diagnostic isolation: Sky Q reading paused; manual remote remains available.",
                "channels":[],"apps":[],"results":[],"stations":[],"page":0,"pages":1}
            self.send_bytes(json.dumps(result).encode())
            return
        if path == "/login":
            self.send_bytes(_login_page(False).encode(),"text/html; charset=utf-8")
            return
        if _remote_request(self) and not _remote_session_ok(self):
            if path.startswith("/api/"):
                self.send_response(401); self.end_headers(); return
            self.send_response(302); self.send_header("Location","/login"); self.end_headers(); return
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/home-briefing.js": ("home-briefing.js", "application/javascript; charset=utf-8"),
            "/home.js": ("home.js", "application/javascript; charset=utf-8"),
            "/velux.html": ("velux.html", "text/html; charset=utf-8"),
            "/velux-ipad-v10.html": ("velux-ipad-v10.html", "text/html; charset=utf-8"),
            "/velux-ipad-v11.html": ("velux-ipad-v11.html", "text/html; charset=utf-8"),
            "/velux-ipad-v12.html": ("velux-ipad-v12.html", "text/html; charset=utf-8"),
            "/velux-ipad-v13.html": ("velux-ipad-v13.html", "text/html; charset=utf-8"),
            "/velux-control.html": ("velux-ipad-v13.html", "text/html; charset=utf-8"),
            "/pioneer.html": ("pioneer.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v10.html": ("pioneer-ipad-v10.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v11.html": ("pioneer-ipad-v11.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v12.html": ("pioneer-ipad-v12.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v13.html": ("pioneer-ipad-v13.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v14.html": ("pioneer-ipad-v14.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v15.html": ("pioneer-ipad-v15.html", "text/html; charset=utf-8"),
            "/pioneer-ipad-v16.html": ("pioneer-ipad-v16.html", "text/html; charset=utf-8"),
            "/eldoret.webmanifest": ("eldoret.webmanifest", "application/manifest+json; charset=utf-8"),
            # Stable action page; future approved Pioneer versions update only this mapping.
            "/pioneer-ipad-v17.html": ("pioneer-ipad-v17.html", "text/html; charset=utf-8"),
            "/pioneer-control.html": ("pioneer-ipad-v17.html", "text/html; charset=utf-8"),
            "/epson-ipad-v10.html": ("epson-ipad-v10.html", "text/html; charset=utf-8"),
            "/epson-ipad-v11.html": ("epson-ipad-v11.html", "text/html; charset=utf-8"),
            "/epson-ipad-v12.html": ("epson-ipad-v12.html", "text/html; charset=utf-8"),
            "/epson-ipad-v13.html": ("epson-ipad-v13.html", "text/html; charset=utf-8"),
            "/printer-control.html": ("epson-ipad-v13.html", "text/html; charset=utf-8"),
            "/network-ipad-v10.html": ("network-ipad-v10.html", "text/html; charset=utf-8"),
            "/network-ipad-v11.html": ("network-ipad-v11.html", "text/html; charset=utf-8"),
            "/network-ipad-v12.html": ("network-ipad-v12.html", "text/html; charset=utf-8"),
            "/network-ipad-v13.html": ("network-ipad-v13.html", "text/html; charset=utf-8"),
            "/network-ipad-v14.html": ("network-ipad-v14.html", "text/html; charset=utf-8"),
            "/network-control.html": ("network-ipad-v14.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v10.html": ("playstation-ipad-v10.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v11.html": ("playstation-ipad-v11.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v12.html": ("playstation-ipad-v12.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v13.html": ("playstation-ipad-v13.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v14.html": ("playstation-ipad-v14.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v15.html": ("playstation-ipad-v15.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v16.html": ("playstation-ipad-v16.html", "text/html; charset=utf-8"),
            "/playstation-control.html": ("playstation-ipad-v17.html", "text/html; charset=utf-8"),
            "/playstation-ipad-v17.html": ("playstation-ipad-v17.html", "text/html; charset=utf-8"),
            "/network-patchbay-background.webp": ("network-patchbay-background.webp", "image/webp"),
            "/engineering.html": ("engineering.html", "text/html; charset=utf-8"),
            "/design-centre.html": ("design-centre.html", "text/html; charset=utf-8"),
            "/design-centre.js": ("design-centre.js", "application/javascript; charset=utf-8"),
            "/zappi.html": ("zappi.html", "text/html; charset=utf-8"),
            "/ariya-ipad.html": ("ariya-ipad.html", "text/html; charset=utf-8"),
            "/ariya-ipad-v11.html": ("ariya-ipad-v11.html", "text/html; charset=utf-8"),
            "/ariya-ipad-v11-approved.html": ("ariya-ipad-v11-approved.html", "text/html; charset=utf-8"),
            # Stable Ariya control URL; promote future revisions by updating only this mapping.
            "/ariya-ipad-v12.html": ("ariya-ipad-v12.html", "text/html; charset=utf-8"),
            "/ariya-ipad-v13.html": ("ariya-ipad-v13.html", "text/html; charset=utf-8"),
            "/ariya-control.html": ("ariya-ipad-v13.html", "text/html; charset=utf-8"),
            "/ariya-design-v11.json": ("ariya-design-v11.json", "application/json"),
            "/ipad2.html": ("ipad2.html", "text/html; charset=utf-8"),
            "/ipad3.html": ("ipad3.html", "text/html; charset=utf-8"),
            "/ipad4.html": ("ipad4.html", "text/html; charset=utf-8"),
            "/ipad5.html": ("ipad5.html", "text/html; charset=utf-8"),
            "/ipad6.html": ("ipad6.html", "text/html; charset=utf-8"),
            "/ipad7.html": ("ipad7.html", "text/html; charset=utf-8"),
            "/ipad8.html": ("ipad8.html", "text/html; charset=utf-8"),
            "/ipad9.html": ("ipad9.html", "text/html; charset=utf-8"),
            "/ipad10.html": ("ipad10.html", "text/html; charset=utf-8"),
            "/ipad11.html": ("ipad11.html", "text/html; charset=utf-8"),
            "/ipad12.html": ("ipad12.html", "text/html; charset=utf-8"),
            "/ipad13.html": ("ipad13.html", "text/html; charset=utf-8"),
            "/ipad14.html": ("ipad14.html", "text/html; charset=utf-8"),
            "/ipad15.html": ("ipad15.html", "text/html; charset=utf-8"),
            "/ipad16.html": ("ipad16.html", "text/html; charset=utf-8"),
            # Permanent iPad bookmark/PWA address. Promote only by changing this mapping.
            "/studio-control.html": ("studio-monitor-v10.html", "text/html; charset=utf-8"),
            "/nerd-control.html": ("nerd-central-v219.html", "text/html; charset=utf-8"),
            "/nerd-central-v219.html": ("nerd-central-v219.html", "text/html; charset=utf-8"),
            "/tv-menu.html": ("tv-menu-v10.html", "text/html; charset=utf-8"),
            "/tv-menu-v10.html": ("tv-menu-v10.html", "text/html; charset=utf-8"),
            "/tv-room-v10.html": ("tv-room-v10.html", "text/html; charset=utf-8"),
            "/tv-room-v11.html": ("tv-room-v11.html", "text/html; charset=utf-8"),
            "/appliance-menu.html": ("appliance-menu-v10.html", "text/html; charset=utf-8"),
            "/appliance-menu-v10.html": ("appliance-menu-v10.html", "text/html; charset=utf-8"),
            "/appliance-detail-v10.html": ("appliance-detail-v10.html", "text/html; charset=utf-8"),
            "/nerd-central-v218.html": ("nerd-central-v218.html", "text/html; charset=utf-8"),
            "/eldoret-artwork-v1.css": ("eldoret-artwork-v1.css", "text/css; charset=utf-8"),
            "/eldoret-network.jpg": ("eldoret-network.jpg", "image/jpeg"),
            "/eldoret-televisions.jpg": ("eldoret-televisions.jpg", "image/jpeg"),
            "/eldoret-lighting.jpg": ("eldoret-lighting.jpg", "image/jpeg"),
            "/eldoret-appliances.jpg": ("eldoret-appliances.jpg", "image/jpeg"),
            "/eldoret-ariya.jpg": ("eldoret-ariya.jpg", "image/jpeg"),
            "/eldoret-printer.jpg": ("eldoret-printer.jpg", "image/jpeg"),
            "/eldoret-playstation.jpg": ("eldoret-playstation.jpg", "image/jpeg"),
            "/eldoret-velux.jpg": ("eldoret-velux.jpg", "image/jpeg"),
            "/eldoret-audio.jpg": ("eldoret-audio.jpg", "image/jpeg"),
            "/eldoret-bulldog.jpg": ("eldoret-bulldog.jpg", "image/jpeg"),
            "/eldoret-home.jpg": ("eldoret-home.jpg", "image/jpeg"),
            "/eldoret-sources.jpg": ("eldoret-sources.jpg", "image/jpeg"),
            "/pioneer.js": ("pioneer.js", "application/javascript; charset=utf-8"),
            "/velux.js": ("velux.js", "application/javascript; charset=utf-8"),
            "/home.css": ("home.css", "text/css; charset=utf-8"),
            "/lights.html": ("lights.html", "text/html; charset=utf-8"),
            "/lights.js": ("lights.js", "application/javascript; charset=utf-8"),
            "/kiosk.js": ("kiosk.js", "application/javascript; charset=utf-8"),
            "/entertainment.html": ("entertainment.html", "text/html; charset=utf-8"),
            "/mobile.js": ("mobile.js", "application/javascript; charset=utf-8"),
            "/remote.js": ("remote.js", "application/javascript; charset=utf-8"),
            "/manifest.webmanifest": ("manifest.webmanifest", "application/manifest+json; charset=utf-8"),
            "/sw.js": ("sw.js", "application/javascript; charset=utf-8"),

            "/house.html": ("house.html", "text/html; charset=utf-8"),
            "/utility.html": ("utility.html", "text/html; charset=utf-8"),
            "/sky.html": ("sky.html", "text/html; charset=utf-8"),
            "/sky-control.html": ("sky-control-v14.html", "text/html; charset=utf-8"),
            "/sky-control-v14.html": ("sky-control-v14.html", "text/html; charset=utf-8"),
            "/sky-control-v13.html": ("sky-control-v13.html", "text/html; charset=utf-8"),
            "/sky-control-v12.html": ("sky-control-v12.html", "text/html; charset=utf-8"),
            "/sky-control-v11.html": ("sky-control-v11.html", "text/html; charset=utf-8"),
            "/sky-control-v10.html": ("sky-control-v10.html", "text/html; charset=utf-8"),
            "/sport.html": ("sport.html", "text/html; charset=utf-8"),
            "/sport.js": ("sport.js", "application/javascript; charset=utf-8"),
            "/devices.js": ("devices.js", "application/javascript; charset=utf-8"),
            "/network.html": ("network.html", "text/html; charset=utf-8"),
            "/bulldog.html": ("bulldog.html", "text/html; charset=utf-8"),
            "/heartbeats.html": ("heartbeats-v2.html", "text/html; charset=utf-8"),
            "/bulldog-monitor-v10.html": ("bulldog-nerd-monitor-v10.html", "text/html; charset=utf-8"),
            "/bulldog-monitor-v11.html": ("bulldog-nerd-monitor-v11.html", "text/html; charset=utf-8"),
            "/bulldog-monitor-v12.html": ("bulldog-nerd-monitor-v12.html", "text/html; charset=utf-8"),
            "/bulldog-monitor-v13.html": ("bulldog-nerd-monitor-v13.html", "text/html; charset=utf-8"),
            "/bulldog-monitor.html": ("bulldog-nerd-monitor-v13.html", "text/html; charset=utf-8"),
            "/heartbeats-legacy.html": ("heartbeats-legacy.html", "text/html; charset=utf-8"),
            "/heartbeats-v2.html": ("heartbeats-v2.html", "text/html; charset=utf-8"),
            "/heartbeats-v2-1.html": ("heartbeats-v2-1.html", "text/html; charset=utf-8"),
            "/lg-tivvy-test.html": ("lg-tivvy-test.html", "text/html; charset=utf-8"),
            "/lg-bulldog.html": ("lg-bulldog.html", "text/html; charset=utf-8"),
            "/av.html": ("av.html", "text/html; charset=utf-8"),
            "/tvs.html": ("tvs.html", "text/html; charset=utf-8"),
            "/appliances.html": ("appliances.html", "text/html; charset=utf-8"),
            "/fridge.html": ("fridge.html", "text/html; charset=utf-8"),
            "/nerd-home.js": ("nerd-home.js", "application/javascript; charset=utf-8"),
            "/office.html": ("office.html", "text/html; charset=utf-8"),
            "/radio.html": ("radio.html", "text/html; charset=utf-8"),
            "/sky-radio.html": ("sky-radio.html", "text/html; charset=utf-8"),
            "/apps.html": ("apps.html", "text/html; charset=utf-8"),
            "/sky-apps.js": ("sky-apps.js", "application/javascript; charset=utf-8"),
            "/sky-radio.js": ("sky-radio.js", "application/javascript; charset=utf-8"),
            "/radio.js": ("radio.js", "application/javascript; charset=utf-8"),
            "/recordings.html": ("recordings.html", "text/html; charset=utf-8"),
            "/recordings.js": ("recordings.js", "application/javascript; charset=utf-8"),
            "/movies.html": ("movies.html", "text/html; charset=utf-8"),
            "/news.html": ("news.html", "text/html; charset=utf-8"),
            "/documentaries.html": ("documentaries.html", "text/html; charset=utf-8"),
            "/hd.html": ("hd.html", "text/html; charset=utf-8"),
            "/plus1.html": ("plus1.html", "text/html; charset=utf-8"),
            "/music.html": ("music.html", "text/html; charset=utf-8"),
            "/top-picks.html": ("top-picks.html", "text/html; charset=utf-8"),
            "/guide-sport.js": ("guide-sport.js", "application/javascript; charset=utf-8"),
            "/sky-search.js": ("sky-search.js", "application/javascript; charset=utf-8"),
            "/guide.js": ("guide.js", "application/javascript; charset=utf-8"),
            "/sky.js": ("sky.js", "application/javascript; charset=utf-8"),
            "/sky-streaming-background.png": ("sky-streaming-background.png", "image/png"),
            "/Apps Banner.png": ("Apps Banner.png", "image/png"),
            "/eldoret-house-night.webp": ("eldoret-house-night.webp", "image/webp"),
            "/eldoret-home-dusk.webp": ("eldoret-home-dusk.webp", "image/webp"),
            "/network-patchbay-background.webp": ("network-patchbay-background.webp", "image/webp"),
            "/epson-et3850-background.webp": ("epson-et3850-background.webp", "image/webp"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        if path in files:
            filename, ctype = files[path]
            self.send_bytes(fetch_github(filename), ctype)
            return
        if path == "/lg-pair":
            self.send_bytes(lg_pair_page().encode(), "text/html; charset=utf-8")
            return
        if path == "/api/radio/stations":
            try: self.send_bytes(json.dumps(radio_stations()).encode())
            except Exception as e: self.send_bytes(json.dumps({"stations":[],"error":str(e)}).encode())
            return
        if path == "/api/agent/results":
            try:
                saved=_agent_read_json(AGENT_RESULTS_FILE, AGENT_RESULT)
                self.send_bytes(json.dumps(saved).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"status":"error","error":str(e)}).encode())
            return
        if path == "/api/remote/state":
            try:
                self.send_bytes(json.dumps(build_remote_state()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"error":str(e)}).encode())
            return
        if path == "/api/devices/registry":
            try:
                self.send_bytes(json.dumps({"registry":_registry_load()}).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"registry":{},"error":str(e)}).encode())
            return
        if path == "/api/home/news":
            self.send_bytes(json.dumps(home_news()).encode())
            return
        if path == "/api/home/locations":
            self.send_bytes(json.dumps(home_locations(query.get("q", [""])[0])).encode())
            return
        if path == "/api/home/weather":
            self.send_bytes(json.dumps(home_weather(query.get("lat", [None])[0], query.get("lon", [None])[0])).encode())
            return
        if path == "/api/router/status":
            self.send_bytes(json.dumps(router_status()).encode())
            return
        if path == "/api/home-connect/details":
            name=(query.get("name") or [""])[0]
            self.send_bytes(json.dumps(home_connect_details(name)).encode())
            return
        if path == "/api/home-connect/status":
            health=home_connect_status()
            health["sse_connected"]=HOME_CONNECT_SSE_CONNECTED
            health["last_event_at"]=HOME_CONNECT_LAST_EVENT_AT
            self.send_bytes(json.dumps(health).encode())
            return
        if path == "/api/bulldog/status":
            try:
                self.send_bytes(json.dumps(bulldog_health()).encode())
            except Exception:
                self.send_bytes(json.dumps({"error":"Bulldog health temporarily unavailable"}).encode())
            return
        if path == "/api/unifi/client-count-pilot":
            self.send_bytes(json.dumps(unifi_client_count_pilot()).encode())
            return
        if path == "/api/unifi/status":
            self.send_bytes(json.dumps(unifi_status()).encode())
            return
        if path == "/api/network/status":
            try:
                self.send_bytes(json.dumps(network_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"devices": [], "error": str(e)}).encode())
            return
        if path == "/api/network/inventory":
            try:
                self.send_bytes(json.dumps(lan_inventory()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"devices": [], "error": str(e)}).encode())
            return
        if path == "/api/velux/homekit":
            self.send_bytes(json.dumps(velux_homekit_readonly()).encode())
            return
        if path == "/api/velux/discovery":
            try:
                self.send_bytes(json.dumps(velux_active_discovery()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"devices": [], "error": str(e)}).encode())
            return
        if path == "/api/homekit/discovery":
            try:
                self.send_bytes(json.dumps(homekit_discovery()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"services": [], "error": str(e)}).encode())
            return
        if path == "/api/network/neighbors":
            try:
                self.send_bytes(json.dumps(local_neighbor_table()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"matches": [], "neighbors": [], "error": str(e)}).encode())
            return
        if path == "/api/network/neighbours":
            try:
                self.send_bytes(json.dumps(local_neighbor_table()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"matches": [], "neighbors": [], "error": str(e)}).encode())
            return
        if path == "/api/network/infrastructure":
            try:
                self.send_bytes(json.dumps(infrastructure_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"targets": [], "error": str(e)}).encode())
            return
        if path == "/api/playstation/activity":
            if _remote_request(self): self.send_error(403); return

            self.send_bytes(json.dumps(playstation_activity_status()).encode())
            return
        if path == "/api/playstation/psn":
            if _remote_request(self): self.send_error(403); return
            self.send_bytes(json.dumps(playstation_network_status()).encode()); return
        if path == "/api/playstation/status":
            try:
                self.send_bytes(json.dumps(playstation_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"online": False, "error": str(e)}).encode())
            return
        if path == "/api/lg/discovery":
            try:
                self.send_bytes(json.dumps(lg_discovery_status()).encode())
            except Exception:
                self.send_bytes(json.dumps({"candidates":[],"error":"LG discovery unavailable"}).encode())
            return
        if path == "/api/lg/wol-status":
            try:self.send_bytes(json.dumps(lg_lounge_wol_status()).encode())
            except Exception:self.send_bytes(json.dumps({"ready":False,"detail":"Wake status unavailable"}).encode())
            return
        if path == "/api/lg/live":
            self.send_bytes(json.dumps(lg_lounge_live()).encode())
            return
        if path == "/api/lg/kitchen/wol-status":
            self.send_bytes(json.dumps(lg_kitchen_wol_status()).encode())
            return
        if path.startswith("/api/lg/room/"):
            bits=path.strip("/").split("/")
            if len(bits)!=5 or bits[0:3]!=["api","lg","room"] or bits[3] not in LG_EXTRA_ROOMS or bits[4] not in ("status","wol-status"):
                self.send_error(404);return
            try:
                result=_lg_extra_status(bits[3]) if bits[4]=="status" else lg_extra_wol_status(bits[3])
                self.send_bytes(json.dumps(result).encode())
            except Exception as e:self.send_bytes(json.dumps({"error":str(e)[:180]}).encode())
            return
        if path == "/api/lg/kitchen/reachability":
            try:self.send_bytes(json.dumps(lg_kitchen_reachability()).encode())
            except Exception:self.send_bytes(json.dumps({"paired":False,"reachable":False,"detail":"Kitchen TV reachability check unavailable"}).encode())
            return
        if path == "/api/lg/kitchen/status":
            self.send_bytes(json.dumps(lg_kitchen_status()).encode())
            return
        if path == "/api/lg/control-status":
            self.send_bytes(json.dumps(lg_bulldog_status()).encode())
            return
        if path == "/api/lg/status":
            try:
                self.send_bytes(json.dumps(lg_tv_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"online": False, "error": str(e)}).encode())
            return
        if path == "/api/velux/status":
            try:
                self.send_bytes(json.dumps(velux_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"online": False, "error": str(e)}).encode())
            return
        if path == "/api/printer/status":
            try:
                self.send_bytes(json.dumps(printer_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"online": False, "error": str(e)}).encode())
            return
        if path == "/api/sky/apps":
            try: self.send_bytes(json.dumps(sky_apps()).encode())
            except Exception as e: self.send_bytes(json.dumps({"apps":[],"error":str(e)}).encode())
            return
        if path == "/api/sky/radio":
            try: self.send_bytes(json.dumps(sky_radio_guide()).encode())
            except Exception as e: self.send_bytes(json.dumps({"channels":[],"error":str(e)}).encode())
            return
        if path == "/api/sky/recordings":
            try: self.send_bytes(json.dumps(sky_recordings_top14()).encode())
            except Exception as e: self.send_bytes(json.dumps({"recordings":[],"error":str(e)}).encode())
            return
        if path == "/api/sky/search":
            try:
                term = query.get("q", [""])[0]
                self.send_bytes(json.dumps(sky_search_channels(term)).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"results": [], "error": str(e)}).encode())
            return
        if path == "/api/sky/guide":
            try:
                group = query.get("group", [""])[0]
                self.send_bytes(json.dumps(sky_named_guide(group)).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"channels": [], "error": str(e)}).encode())
            return
        if path == "/api/sky/top-picks":
            try:
                page = int(query.get("page", ["0"])[0])
                size = int(query.get("size", ["14"])[0])
                self.send_bytes(json.dumps(sky_top_picks(page, size)).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"channels": [], "page": 0, "pages": 1, "error": str(e)}).encode())
            return
        if path == "/api/sky/guide-range":
            try:
                start = int(query.get("start", ["301"])[0])
                end = int(query.get("end", ["399"])[0])
                page = int(query.get("page", ["0"])[0])
                size = int(query.get("size", ["14"])[0])
                self.send_bytes(json.dumps(sky_range_guide(start, end, page, size)).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"channels": [], "page": 0, "pages": 1, "error": str(e)}).encode())
            return
        if path == "/api/sky/sport-guide":
            try:
                payload = json.dumps(sky_sport_guide()).encode()
                self.send_bytes(payload)
            except Exception as e:
                self.send_bytes(json.dumps({"channels": [], "error": str(e)}).encode())
            return
        if path == "/api/sky/now":
            try:
                payload = json.dumps(sky_now_playing_v2()).encode()
                self.send_bytes(payload)
            except Exception as e:
                payload = json.dumps({"available": False, "error": str(e)}).encode()
                self.send_bytes(payload)
            return
        if path == "/api/hue/sensors":
            try: self.send_bytes(json.dumps(hue_sensors()).encode())
            except Exception: self.send_bytes(json.dumps({"devices":[], "errors":["Hue sensors unavailable"]}).encode())
            return
        if path == "/api/hue/group":
            bridge_name = query.get("bridge", [None])[0]
            group = query.get("group", [None])[0]
            if bridge_name not in BRIDGES or not group:
                self.send_error(400); return
            try:
                self.send_bytes(hue_get(bridge_name, f"groups/{group}"))
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        self.send_error(404)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path.startswith('/api/playout/'):
            playout_http(self); return
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length)
        if self.path == "/login":
            form=urllib.parse.parse_qs(raw_body.decode("utf-8",errors="replace"))
            password=(form.get("password") or [""])[0]
            if _verify_remote_password(password):
                token=secrets.token_urlsafe(32); REMOTE_SESSIONS.add(token)
                self.send_response(303)
                self.send_header("Location","/")
                self.send_header("Set-Cookie","eldoret_session="+token+"; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=604800")
                self.end_headers()
            else:
                body=_login_page(True).encode()
                self.send_response(401); self.send_header("Content-Type","text/html; charset=utf-8"); self.send_header("Content-Length",str(len(body))); self.end_headers(); self.wfile.write(body)
            return
        if _remote_request(self) and not _remote_session_ok(self):
            self.send_response(401); self.end_headers(); return
        if urllib.parse.urlparse(self.path).path == "/api/design-centre":
            origin=self.headers.get("Origin","")
            host=self.headers.get("Host","")
            if (_remote_request(self) or
                host not in ("10.0.0.34:8765","localhost:8765","127.0.0.1:8765") or
                origin!="http://"+host or
                self.headers.get("Content-Type","").split(";")[0].strip()!="application/json" or
                length>200000):
                self.send_error(403); return
            try:
                query=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                name,preset=design_centre_key(query)
                payload=json.loads(raw_body)
                if not isinstance(payload,dict) or set(payload)!={"design"}:
                    raise ValueError("Invalid save request")
                self.send_bytes(json.dumps(design_centre_save(name,preset,payload["design"])).encode()); return
            except (ValueError, TypeError, json.JSONDecodeError):
                self.send_error(400); return
        if urllib.parse.urlparse(self.path).path == "/api/ariya/climate":
            origin=self.headers.get("Origin","")
            host=self.headers.get("Host","")
            if (_remote_request(self) or
                host not in ("10.0.0.34:8765","localhost:8765","127.0.0.1:8765") or
                origin!="http://"+host or
                self.headers.get("Content-Type","").split(";")[0].strip()!="application/json" or
                length>128):
                self.send_error(403); return
            try:
                req=json.loads(raw_body)
                if not isinstance(req,dict) or set(req)!={"action","temperature_c"}:
                    raise ValueError("Invalid climate payload")
                result=ariya_control(req["action"],req["temperature_c"])
                self.send_bytes(json.dumps(result).encode()); return
            except (ValueError,TypeError,json.JSONDecodeError):
                self.send_error(400); return
        if urllib.parse.urlparse(self.path).path == "/api/velux/manual-window":
            origin=self.headers.get("Origin","")
            host=self.headers.get("Host","")
            if (_remote_request(self) or
                host not in ("10.0.0.34:8765","localhost:8765","127.0.0.1:8765") or
                origin!="http://"+host or
                self.headers.get("Content-Type","").split(";")[0].strip()!="application/json" or
                length>160):
                self.send_error(403); return
            try:
                request=json.loads(raw_body)
                if (not isinstance(request,dict) or set(request)!={"aid","action","supervised"}
                    or request["supervised"] is not True):
                    raise ValueError("Invalid supervised request")
                result=velux_manual_command(request["aid"],request["action"])
                self.send_bytes(json.dumps(result).encode()); return
            except (ValueError,TypeError,json.JSONDecodeError):
                self.send_error(400); return
        if urllib.parse.urlparse(self.path).path == "/api/pioneer/control":
            origin=self.headers.get("Origin","")
            host=self.headers.get("Host","")
            if (_remote_request(self) or not host or
                not host.startswith(("10.0.0.34:","localhost:","127.0.0.1:")) or
                origin!="http://"+host or
                self.headers.get("Content-Type","").split(";")[0].strip()!="application/json" or
                length>128):
                self.send_error(403); return
            try:
                request=json.loads(raw_body)
                if not isinstance(request,dict) or set(request)!={"action"} or not isinstance(request["action"],str):
                    raise ValueError("Invalid control request")
                result=pioneer_control(request["action"])
                self.send_bytes(json.dumps(result).encode()); return
            except (ValueError, TypeError):
                self.send_error(400); return
        payload = json.loads(raw_body or b"{}")
        if self.path.startswith("/api/lg/room/") or self.path in ("/api/lg/pair","/api/lg/open-tivvy","/api/lg/control","/api/lg/learn-mac","/api/lg/wake","/api/lg/kitchen/pair","/api/lg/kitchen/open-tivvy","/api/lg/kitchen/learn-mac","/api/lg/kitchen/wake","/api/lg/kitchen/hdmi1","/api/lg/hdmi1"):
            # Same-origin LAN UI only; never expose TV actions via the remote tunnel.
            origin=self.headers.get("Origin","")
            host=self.headers.get("Host","")
            if (_remote_request(self) or origin!="http://"+host or not host or
                not host.startswith(("10.0.0.34:","localhost:","127.0.0.1:"))):
                self.send_error(403); return
            if self.headers.get("Content-Type","").split(";")[0].strip()!="application/json" or len(raw_body)>128:
                self.send_error(400); return
            if self.path!="/api/lg/control" and payload:
                self.send_error(400); return
            if self.path=="/api/lg/control" and (not isinstance(payload,dict) or set(payload)-{"action","input_id"}):
                self.send_error(400); return
            try:
                if self.path.startswith("/api/lg/room/"):
                    bits=self.path.strip("/").split("/")
                    if len(bits)!=5 or bits[0:3]!=["api","lg","room"]:
                        raise ValueError("Invalid TV endpoint")
                    room,action=bits[3],bits[4]
                    cfg=_lg_extra_config(room)
                    if action=="pair":
                        started=lg_extra_pair_start(room)
                        result={"ok":started,"detail":"Pairing started. Accept Eldoret prompt on "+room+" TV." if started else "TV pairing already in progress"}
                    elif action in ("volume_up","volume_down","mute","unmute","channel_up","channel_down"):
                        result=lg_extra_control(room,action)
                    elif cfg["media"] and action in ("tivvy","hdmi1"):
                        result=lg_extra_media(room,action)
                    elif cfg["media"] and action=="learn-mac":
                        result=lg_extra_learn_mac(room)
                    elif cfg["media"] and action=="wake":
                        result=lg_extra_wake(room)
                    else:raise ValueError("This TV does not permit that action")
                elif self.path=="/api/lg/kitchen/hdmi1":
                    result=lg_switch_sky_hdmi1("kitchen")
                elif self.path=="/api/lg/hdmi1":
                    result=lg_switch_sky_hdmi1("lounge")
                elif self.path=="/api/lg/kitchen/learn-mac":
                    result=lg_kitchen_learn_mac()
                elif self.path=="/api/lg/kitchen/wake":
                    result=lg_kitchen_wake()
                elif self.path=="/api/lg/kitchen/pair":
                    started=lg_kitchen_pair_start()
                    result={"ok":started,"detail":"Kitchen LG pairing request starting — accept the prompt on the kitchen screen." if started else "Kitchen pairing is already in progress."}
                elif self.path=="/api/lg/kitchen/open-tivvy":
                    result=lg_kitchen_launch()
                elif self.path=="/api/lg/pair":
                    started=lg_bulldog_pair_start()
                    result={"ok":started,"detail":"Pairing request starting; look at lounge LG." if started else "Already attempting pairing."}
                elif self.path=="/api/lg/control":
                    result=lg_lounge_control(payload.get("action"),payload.get("input_id"))
                elif self.path=="/api/lg/learn-mac":
                    result=lg_lounge_learn_mac()
                elif self.path=="/api/lg/wake":
                    result=lg_lounge_wake()
                else:
                    result=lg_bulldog_launch()
                self.send_bytes(json.dumps(result).encode())
            except Exception as exc:
                self.send_bytes(json.dumps({"ok":False,"detail":str(exc)[:180]}).encode())
            return
        if self.path == "/api/sky/app/launch":
            try:
                sky_launch_app(payload.get("appid"))
                self.send_bytes(json.dumps({"ok":True}).encode())
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        if self.path == "/api/sky/recording/play":
            try:
                sky_play_recording(payload.get("pvrid"))
                self.send_bytes(json.dumps({"ok":True}).encode())
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        if self.path == "/api/sky/channel":
            channel = str(payload.get("channel", ""))
            try:
                sky_send_channel(channel)
                self.send_bytes(json.dumps({"ok": True, "channel": channel}).encode())
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        if self.path == "/api/sky/key":
            key = payload.get("key")
            if key not in SKY_KEY_MAP:
                self.send_error(400); return
            try:
                sky_send_key(key)
                self.send_bytes(json.dumps({"ok": True, "key": key}).encode())
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        if self.path == "/api/hue/group":
            bridge_name, group = payload.get("bridge"), payload.get("group")
            if bridge_name not in BRIDGES or not group:
                self.send_error(400); return
            command = {}
            if "on" in payload: command["on"] = bool(payload["on"])
            if "brightness" in payload:
                pct = max(1, min(100, int(payload["brightness"])))
                command["bri"] = round(pct * 254 / 100); command["on"] = True
            if "colour" in payload:
                colours = {
                    "#ffb36b": {"ct": 370}, "#ffffff": {"ct": 250},
                    "#6bb8ff": {"xy": [0.153, 0.048]}, "#d77bff": {"xy": [0.33, 0.16]},
                    "#ff6f91": {"xy": [0.53, 0.24]}, "#70e0a0": {"xy": [0.17, 0.7]},
                }
                command.update(colours.get(payload["colour"], {})); command["on"] = True
            try:
                self.send_bytes(hue_put(bridge_name, f"groups/{group}/action", command))
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        if self.path == "/api/hue/scene":
            bridge_name, group, scene = payload.get("bridge"), payload.get("group"), payload.get("scene")
            if bridge_name not in BRIDGES or not group or not scene:
                self.send_error(400); return
            try:
                self.send_bytes(hue_put(bridge_name, f"groups/{group}/action", {"scene": scene}))
            except Exception as e:
                self.send_response(500); self.end_headers(); self.wfile.write(str(e).encode())
            return
        self.send_error(404)

    def log_message(self, format, *args):
        pass

if __name__ == '__main__':
    import sys
    if '--configure-unifi' in sys.argv:
        try:
            configure_unifi()
        except Exception:
            print('UniFi setup not saved. Check the controller is awake, address, local login, site and view permissions.')
            sys.exit(1)
        sys.exit(0)
    if '--configure-router-snmp' in sys.argv:
        try:
            configure_router_snmp()
        except (RuntimeError, ValueError, OSError) as exc:
            print('SNMP setup not saved:', str(exc))
            sys.exit(1)
        sys.exit(0)

threading.Thread(target=pioneer_monitor_loop, daemon=True).start()
threading.Thread(target=agent_loop, daemon=True).start()
threading.Thread(target=device_registry_loop, daemon=True).start()
threading.Thread(target=_bulldog_history_loop, daemon=True).start()
threading.Thread(target=_ps5_collector_loop, daemon=True).start()
threading.Thread(target=_hc_event_loop, daemon=True).start()
threading.Thread(target=remote_state_loop, daemon=True).start()
print("Eldoret live connector running")
print("House Hue bridge: ready")
print("Utility Hue bridge: ready")
print("Live state + scenes: ready")
print(f"Sky Q now-playing target: {sky_q_host()}:{SKY_Q_JSON_PORT}")
print("Open http://localhost:8765 in Chrome")
ThreadingHTTPServer(("0.0.0.0", 8765), Handler).serve_forever()





