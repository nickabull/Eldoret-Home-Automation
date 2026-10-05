import json
import os
import socket
import time
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BRIDGES = {
    "house": {"ip": "10.0.0.2", "key": os.environ.get("HUE_KEY")},
    "utility": {"ip": "10.0.0.4", "key": os.environ.get("UTILITY_HUE_KEY")},
}
GITHUB_BASE = "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/"
SKY_Q_HOST = os.environ.get("SKY_Q_HOST", "10.0.0.18")
SKY_Q_JSON_PORT = int(os.environ.get("SKY_Q_JSON_PORT", "9006"))
SKY_Q_REMOTE_PORT = int(os.environ.get("SKY_Q_REMOTE_PORT", "49160"))
SKY_KEY_MAP = {
    "power":0,"select":1,"backup":2,"channelup":6,"channeldown":7,
    "search":10,"home":11,"up":16,"down":17,"left":18,"right":19,
    "0":48,"1":49,"2":50,"3":51,"4":52,"5":53,"6":54,"7":55,"8":56,"9":57,
    "play":64,"pause":65,"stop":66,"record":67,"fastforward":69,"rewind":71
}

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
            "/sky.js": ("sky.js", "application/javascript; charset=utf-8"),
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        if path in files:
            filename, ctype = files[path]
            self.send_bytes(fetch_github(filename), ctype)
            return
        if path == "/api/sky/now":
            try:
                payload = json.dumps(sky_now_playing()).encode()
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
