"""UniFi UDM collector."""
import json
import time
import urllib.request
import http.cookiejar
from collections import Counter
from .utils import CTX, TIMEOUT


def collect(E, card_cfg=None):
    d = {"state": "ok", "wan": "?", "wan_ip": "?", "clients": 0, "ips_24h": 0,
         "latency": None, "down_mbps": None, "up_mbps": None, "devices": [],
         "ssids": [], "month_rx": None, "month_tx": None, "month_total": None,
         "pia": None}
    GW = E.get("UNIFI_URL", "https://10.10.10.1").rstrip("/")
    NET = GW + "/proxy/network/api/s/default"
    cj = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(
        urllib.request.HTTPSHandler(context=CTX),
        urllib.request.HTTPCookieProcessor(cj))
    op.open(urllib.request.Request(
        f"{GW}/api/auth/login",
        data=json.dumps({"username": E.get("UNIFI_USERNAME", ""),
                         "password": E.get("UNIFI_PASSWORD", "")}).encode(),
        headers={"Content-Type": "application/json"}, method="POST"), timeout=TIMEOUT)
    import base64 as _b64
    csrf = None
    tok = next((c.value for c in cj if c.name == "TOKEN"), None)
    if tok:
        try:
            p = tok.split(".")[1]; p += "=" * (-len(p) % 4)
            csrf = json.loads(_b64.urlsafe_b64decode(p)).get("csrfToken")
        except Exception:
            pass
    hdr = {"Content-Type": "application/json"}
    if csrf:
        hdr["X-CSRF-Token"] = csrf

    def call(path, data=None, method="GET"):
        body = json.dumps(data).encode() if data is not None else None
        r = urllib.request.Request(NET + path, data=body, headers=hdr,
                                   method=("POST" if data is not None else method))
        return json.loads(op.open(r, timeout=TIMEOUT).read())

    health = call("/stat/health").get("data", [])
    wan = next((h for h in health if h.get("subsystem") == "wan"), {})
    www = next((h for h in health if h.get("subsystem") == "www"), {})
    d["wan"] = wan.get("status", "?")
    d["wan_ip"] = wan.get("wan_ip", "?")
    d["latency"] = www.get("latency")
    d["down_mbps"] = www.get("xput_down")
    d["up_mbps"] = www.get("xput_up")
    clients = 0
    for h in health:
        if h.get("subsystem") in ("lan", "wlan"):
            clients += int(h.get("num_user", 0) or 0)
    d["clients"] = clients
    if d["wan"] != "ok":
        d["state"] = "crit"
    try:
        alarms = call("/list/alarm").get("data", [])
        cutoff = (time.time() - 86400) * 1000
        ips = [a for a in alarms
               if (a.get("time") or a.get("timestamp") or 0) >= cutoff
               and (a.get("key") == "EVT_IPS_IpsAlert" or a.get("inner_alert_signature"))]
        d["ips_24h"] = len(ips)
        if len(ips) > 0 and d["state"] == "ok":
            d["state"] = "warn"
    except Exception:
        d["ips_24h"] = 0
    try:
        devs = call("/stat/device").get("data", [])
        TMAP = {"udm": "Gateway", "ugw": "Gateway", "usw": "Switch",
                "uap": "Access Point", "usg": "Gateway"}
        def fmt_uptime(s):
            s = int(s or 0)
            dd, hh = s // 86400, (s % 86400) // 3600
            if dd: return f"{dd}d {hh}h"
            mm = (s % 3600) // 60
            return f"{hh}h {mm}m"
        torder = {"udm": 0, "ugw": 0, "usg": 0, "usw": 1, "uap": 2}
        for dev in sorted(devs, key=lambda x: (torder.get(x.get("type"), 9), x.get("name", ""))):
            up = int(dev.get("uptime", 0) or 0)
            online = dev.get("state") == 1
            d["devices"].append({
                "name": dev.get("name", dev.get("model", "?")),
                "kind": TMAP.get(dev.get("type"), dev.get("type", "?")),
                "uptime": fmt_uptime(up) if online else "offline",
                "online": online})
            if not online and d["state"] == "ok":
                d["state"] = "warn"
    except Exception:
        pass
    try:
        sta = call("/stat/sta").get("data", [])
        ssid_ct = Counter()
        for c in sta:
            e = c.get("essid")
            if e: ssid_ct[e] += 1
        WANTED = ["ZOMBIELAND5G", "ZOMBIELAND2G", "IOTNetwork"]
        seen = set()
        for name in WANTED:
            d["ssids"].append({"name": name, "clients": int(ssid_ct.get(name, 0))})
            seen.add(name)
        for name, ct in ssid_ct.most_common():
            if name not in seen:
                d["ssids"].append({"name": name, "clients": int(ct)})
    except Exception:
        pass
    try:
        rows = call("/stat/report/monthly.site",
                    {"attrs": ["wan-tx_bytes", "wan-rx_bytes", "time"], "n": 2},
                    "POST").get("data", [])
        if rows:
            cur = rows[-1]
            d["month_tx"] = cur.get("wan-tx_bytes")
            d["month_rx"] = cur.get("wan-rx_bytes")
            d["month_total"] = (cur.get("wan-tx_bytes", 0) or 0) + (cur.get("wan-rx_bytes", 0) or 0)
    except Exception:
        pass
    try:
        ncs = call("/rest/networkconf").get("data", [])
        pia = next((n for n in ncs if n.get("purpose") == "vpn-client"
                    and "pia" in (n.get("name", "").lower())), None)
        if pia is None:
            pia = next((n for n in ncs if n.get("purpose") == "vpn-client"), None)
        if pia:
            status = pia.get("openvpn_configuration_status", "?")
            enabled = bool(pia.get("enabled"))
            connected = (str(status).upper() == "VALID") and enabled
            d["pia"] = {"name": pia.get("name", "PIAVPN"), "status": str(status),
                        "enabled": enabled, "connected": connected}
            if not connected and d["state"] == "ok":
                d["state"] = "warn"
    except Exception:
        pass
    return d
