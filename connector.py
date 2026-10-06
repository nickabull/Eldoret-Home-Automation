import json
import os
import socket
import ssl
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
STATIC_CACHE = {}
STATIC_CACHE_TTL = 30
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

def _tcp_open(ip, port, timeout=0.25):
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            return True
    except Exception:
        return False

def printer_status():
    host = "10.0.0.3"
    result = {"ip": host, "online": False, "ports": [], "model": None, "title": None,
              "http": False, "https": False, "ipp": False, "raw_print": False,
              "detail": None, "ink": [], "probe": []}
    ports = [p for p in (80,443,631,9100) if _tcp_open(host,p,timeout=0.4)]
    result.update({"ports":ports,"online":bool(ports),"http":80 in ports,"https":443 in ports,
                   "ipp":631 in ports,"raw_print":9100 in ports})
    if 80 in ports or 443 in ports:
        # Epson models expose consumables differently. Probe common read-only WebConfig/status URLs.
        paths = ["/", "/PRESENTATION/HTML/TOP/INDEX.HTML", "/PRESENTATION/HTML/TOP/PRTINFO.HTML",
                 "/PRESENTATION/HTML/TOP/PRTINFO.JS", "/PRESENTATION/HTML/TOP/INK.HTML",
                 "/PRESENTATION/HTML/TOP/STATUS.HTML", "/cgi-bin/PrinterStatus.cgi",
                 "/cgi-bin/Status.cgi", "/cgi-bin/InkLevel.cgi"]
        ctx = ssl._create_unverified_context()
        for path in paths:
            try:
                req=urllib.request.Request("https://"+host+path,headers={"User-Agent":"Eldoret/1.0"})
                with urllib.request.urlopen(req,timeout=2,context=ctx) as response:
                    body=response.read(180000).decode("utf-8",errors="replace")
                low=body.lower()
                hits=[k for k in ("ink","black","cyan","magenta","yellow","cartridge","consumable","model") if k in low]
                result["probe"].append({"path":path,"ok":True,"hits":hits,"length":len(body)})
                if path == "/":
                    import re
                    m=re.search(r"<title[^>]*>(.*?)</title>",body,re.I|re.S)
                    if m:
                        title=" ".join(re.sub(r"<[^>]+>"," ",m.group(1)).split())
                        result["title"]=title[:160]
                        if "epson" in title.lower(): result["model"]=title
                # Capture small text fragments around consumable terms for the next parser step.
                for key in ("black","cyan","magenta","yellow","ink level","inklevel"):
                    pos=low.find(key)
                    if pos >= 0:
                        frag=" ".join(re.sub(r"<[^>]+>"," ",body[max(0,pos-120):pos+260]).split())
                        if frag and not any(x.get("text")==frag[:300] for x in result["ink"]):
                            result["ink"].append({"source":path,"key":key,"text":frag[:300]})
            except Exception as exc:
                result["probe"].append({"path":path,"ok":False,"error":str(exc)[:120]})
        result["detail"] = "Epson online; consumables probe complete."
    if not result["detail"]:
        result["detail"]="No printer web service answered."
    return result

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
    now = time.time()
    cached = STATIC_CACHE.get(path)
    if cached and (now - cached["time"] < STATIC_CACHE_TTL):
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
            url = f"http://{SKY_Q_HOST}:{SKY_Q_JSON_PORT}{path}"
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
                result["logo"] = sky_channel_logo_url(service)
                result["is_radio"] = str(service.get("sf", "")).lower() == "au"
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
            "/styles.css": ("styles.css", "text/css; charset=utf-8"),
            "/app.js": ("app.js", "application/javascript; charset=utf-8"),
        }
        if path in files:
            filename, ctype = files[path]
            self.send_bytes(fetch_github(filename), ctype)
            return
        if path == "/api/radio/stations":
            try: self.send_bytes(json.dumps(radio_stations()).encode())
            except Exception as e: self.send_bytes(json.dumps({"stations":[],"error":str(e)}).encode())
            return
        if path == "/api/network/status":
            try:
                self.send_bytes(json.dumps(network_status()).encode())
            except Exception as e:
                self.send_bytes(json.dumps({"devices": [], "error": str(e)}).encode())
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

print("Eldoret live connector running")
print("House Hue bridge: ready")
print("Utility Hue bridge: ready")
print("Live state + scenes: ready")
print(f"Sky Q now-playing target: {SKY_Q_HOST}:{SKY_Q_JSON_PORT}")
print("Open http://localhost:8765 in Chrome")
HTTPServer(("0.0.0.0", 8765), Handler).serve_forever()
