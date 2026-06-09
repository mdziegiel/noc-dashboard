"""URBackup collector."""
import hashlib
import time
import urllib.parse
import urllib.request
import ssl
from .utils import CTX, TIMEOUT


def collect(E, card_cfg=None):
    d = {"state": "ok", "total": 0, "online": 0, "clients": [], "problems": []}
    base = E.get("URBACKUP_URL", "http://10.10.10.76:55414").rstrip("/")
    user = E.get("URBACKUP_USERNAME", "michaeld")
    pw = E.get("URBACKUP_PASSWORD", "")
    if not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "URBACKUP_PASSWORD not set",
                "total": 0, "online": 0, "clients": [], "problems": []}

    def api(action, body=""):
        url = base + "/x?a=" + action
        r = urllib.request.Request(url, data=body.encode(), method="POST",
                                   headers={"Content-Type": "application/json; charset=utf-8"})
        import json as _json
        return _json.loads(urllib.request.urlopen(r, timeout=TIMEOUT, context=CTX).read().decode("utf-8", "replace"))

    s = api("salt", "username=" + urllib.parse.quote(user))
    if s.get("error") == 1 or not s.get("salt"):
        raise RuntimeError("URBackup user not found")
    salt, rnd = s.get("salt", ""), s.get("rnd", "")
    rounds = int(s.get("pbkdf2_rounds", 0) or 0)
    ses = s.get("ses")
    pwmd5 = hashlib.md5((salt + pw).encode()).hexdigest()
    if rounds > 0:
        pwmd5 = hashlib.pbkdf2_hmac("sha256", bytes.fromhex(pwmd5), salt.encode(), rounds, dklen=32).hex()
    final = hashlib.md5((rnd + pwmd5).encode()).hexdigest()
    body = "username=" + urllib.parse.quote(user) + "&password=" + final
    if ses:
        body += "&ses=" + ses
    r3 = api("login", body)
    if not r3.get("success"):
        raise RuntimeError("URBackup login failed")
    ses = r3.get("session") or ses
    st = api("status", "ses=" + ses if ses else "")
    clients = st.get("status", [])
    d["total"] = len(clients)
    d["online"] = sum(1 for c in clients if c.get("online"))
    now = time.time()
    for c in sorted(clients, key=lambda x: x.get("name", "")):
        name = c.get("name", "?")
        lf = c.get("lastbackup", 0) or 0
        issues = c.get("last_filebackup_issues", 0) or 0
        on = bool(c.get("online"))
        lf_h = (now - lf) / 3600.0 if lf else 1e9
        ago = ("never" if not lf else
               f"{lf_h*60:.0f}m" if lf_h < 1 else
               f"{lf_h:.1f}h" if lf_h < 48 else f"{lf_h/24:.1f}d")
        cstate = "ok"
        if lf == 0:
            d["problems"].append(f"{name}: no file backup on record"); cstate = "crit"
        elif lf_h > 26:
            d["problems"].append(f"{name}: last backup {ago} ago"); cstate = "warn"
        if issues:
            d["problems"].append(f"{name}: {issues} issue(s)")
            cstate = "warn" if cstate == "ok" else cstate
        if not on:
            d["problems"].append(f"{name}: OFFLINE")
            cstate = "warn" if cstate == "ok" else cstate
        d["clients"].append({"name": name, "ago": ago, "online": on, "issues": issues, "state": cstate})
    if any(c["state"] == "crit" for c in d["clients"]):
        d["state"] = "crit"
    elif d["problems"]:
        d["state"] = "warn"
    return d
