import json
import os
import socket
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import datetime, timezone

BRIDGES = {
    "house": {"ip": "10.0.0.2", "key": os.environ.get("HUE_KEY")},
    "utility": {"ip": "10.0.0.4", "key": os.environ.get("UTILITY_HUE_KEY")},
}
GITHUB_BASE = "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/"
SKY_Q_HOST = os.environ.get("SKY_Q_HOST", "10.0.0.18")
SKY_Q_JSON_PORT = int(os.environ.get("SKY_Q_JSON_PORT", "9006"))
SKY_Q_REMOTE_PORT = int(os.environ.get("SKY_Q_REMOTE_PORT", "49160"))
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
 {"ip":"10.0.0.33","name":"LG webOS TV","ports":[3000,3001,80]},
 {"ip":"10.0.0.43","name":"LG device","ports":[3000,3001,80]},
 {"ip":"10.0.0.47","name":"LG device","ports":[3000,3001,80]}
]
GUIDE_GROUPS = {"news":["Sky News","BBC News","CNN","GB News","Bloomberg","BBC Parliament","CNBC"],"entertainment":["BBC One","BBC Two","ITV1","Channel 4","Channel 5","Sky Atlantic","Sky Max","Sky Witness","Gold","Dave","Comedy Central","Discovery"]}
SPORT_CHANNEL_NUMBERS = ["401","402","403","404","405","406","407","408","409","410","411","412","413","414","419"]
SKY_KEY_MAP = {
    "power":0,"select":1,"backup":2,"channelup":6,"channeldown":7,
    "search":10,"home":11,"up":16,"down":17,"left":18,"right":19,"red":32,
    "0":48,"1":49,"2":50,"3":51,"4":52,"5":53,"6":54,"7":55,"8":56,"9":57,
    "play":64,"pause":65,"stop":66,"record":67,"fastforward":69,"rewind":71
}

def _tcp_open(ip, port, timeout=0.25):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def network_status():
    devices = []
    for d in NETWORK_PROBES:
        open_ports = [p for p in d["ports"] if _tcp_open(d["ip"], p)]
        devices.append({"ip": d["ip"], "name": d["name"], "online": bool(open_ports), "ports": open_ports,
                        "detail": ("Open ports: " + ", ".join(map(str, open_ports))) if open_ports else "No configured service answered"})
    return {"devices": devices, "checked_at": datetime.now(timezone.utc).isoformat()}

def sky_send_key(key):
    if key not in SKY_KEY_MAP:
        raise ValueError("Unsupported Sky key")
    code = SKY_KEY_MAP[key]
    command = [4,1,0,0,0,0,224 + (code // 16),code % 16]
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(4)
    try:
        client.connect((SKY_Q_HOST, SKY_Q_REMOTE_PORT))
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

for name, config in BRIDGES.items():
    if not config["key"]:
        raise SystemExit(f"{name} Hue key is not set")

def fetch_github(path):
    with urllib.request.urlopen(GITHUB_BASE + path, timeout=10) as response:
        return response.read()

def hue_get(bridge_name, path):
    bridge = BRIDGES[bridge_name]
    url = f"http://{bridge['ip']}/api/{bridge['key']}/{path}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.read()

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
    for digit in digits:
        sky_send_key(digit)
        time.sleep(0.08)

def _localname(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag.split(":", 1)[-1]

def sky_soap_control_url():
    headers = {"User-Agent": "SKYPLUS_skyplus"}
    for idx in range(50):
        url = f"http://{SKY_Q_HOST}:49153/description{idx}.xml"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=2) as response:
                root = ET.fromstring(response.read())
            device_type = next((el.text or "" for el in root.iter() if _localname(el.tag) == "deviceType"), "")
            if "SkyControl" not in device_type:
                continue
            for service in root.iter():
                if _localname(service.tag) != "service":
                    continue
                values = {_localname(child.tag): (child.text or "") for child in list(service)}
                if values.get("serviceId") == "urn:nds-com:serviceId:SkyPlay":
                    control = values.get("controlURL")
                    if control:
                        return f"http://{SKY_Q_HOST}:49153{control}"
        except Exception:
            continue
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

def sky_search_channels(query):
    q = (query or "").strip().lower()
    if not q:
        return {"results": []}
    services = sky_channel_list()
    results = []
    for service in services:
        name = str(service.get("t", ""))
        number = str(service.get("c", ""))
        if q in name.lower() or q == number:
            item = {
                "channel": name,
                "channelno": number,
                "sid": service.get("sid"),
                "logo": sky_channel_logo_url(service),
                "programme": None,
            }
            if service.get("sid"):
                item.update(sky_epg_now(service.get("sid")))
            results.append(item)
    results.sort(key=lambda x: (0 if x["channel"].lower().startswith(q) else 1, x.get("channelno") or "9999", x["channel"].lower()))
    return {"results": results[:20]}

def sky_named_guide(group):
    wanted = GUIDE_GROUPS.get(group, [])
    services = sky_channel_list()
    channels = []
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

def sky_channel_list():
    candidates = ["/as/services/4/1", "/as/services/1/1", "/as/services/5/1"]
    for path in candidates:
        try:
            url = f"http://{SKY_Q_HOST}:{SKY_Q_JSON_PORT}{path}"
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

def sky_epg_now_next(sid):
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
    result = {"available": False, "live": False, "host": SKY_Q_HOST}
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
            result.update(sky_epg_now(sid))
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
        "host": SKY_Q_HOST,
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

class Handler(BaseHTTPRequestHandler):
    def send_bytes(self, data, content_type="application/json"):
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        files = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/house.html": ("house.html", "text/html; charset=utf-8"),
            "/utility.html": ("utility.html", "text/html; charset=utf-8"),
            "/sky.html": ("sky.html", "text/html; charset=utf-8"),
            "/sport.html": ("sport.html", "text/html; charset=utf-8"),
            "/sport.js": ("sport.js", "application/javascript; charset=utf-8"),
            "/devices.js": ("devices.js", "application/javascript; charset=utf-8"),
            "/network.html": ("network.html", "text/html; charset=utf-8"),
            "/av.html": ("av.html", "text/html; charset=utf-8"),
            "/appliances.html": ("appliances.html", "text/html; charset=utf-8"),
            "/office.html": ("office.html", "text/html; charset=utf-8"),
            "/news.html": ("news.html", "text/html; charset=utf-8"),
            "/entertainment.html": ("entertainment.html", "text/html; charset=utf-8"),
            "/guide.js": ("guide.js", "application/javascript; charset=utf-8"),
            "/sky.js": ("sky.js", "application/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        if path in files:
            filename, ctype = files[path]
            self.send_bytes(fetch_github(filename), ctype)
            return
        if path == "/api/network/status":
            try:
                self.send_bytes(json.dumps(network_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"devices": [], "error": str(e)}).encode())
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
        length = int(self.headers.get("Content-Length", 0))
        payload = json.loads(self.rfile.read(length))
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

print("Eldoret live connector running")
print("House Hue bridge: ready")
print("Utility Hue bridge: ready")
print("Live state + scenes: ready")
print(f"Sky Q now-playing target: {SKY_Q_HOST}:{SKY_Q_JSON_PORT}")
print("Open http://localhost:8765 in Chrome")
HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
