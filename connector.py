import json
import os
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer

BRIDGES = {
    "house": {"ip": "10.0.0.2", "key": os.environ.get("HUE_KEY")},
    "utility": {"ip": "10.0.0.4", "key": os.environ.get("UTILITY_HUE_KEY")},
}
GITHUB_BASE = "https://raw.githubusercontent.com/nickabull/Eldoret-Home-Automation/main/"

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
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        if path in files:
            filename, ctype = files[path]
            self.send_bytes(fetch_github(filename), ctype)
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
print("Open http://localhost:8765 in Chrome")
HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
