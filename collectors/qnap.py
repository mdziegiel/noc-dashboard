"""QNAP NAS collector (all three units)."""
import re
import urllib.parse
import urllib.request
from .utils import CTX, TIMEOUT, b64


def _text(el):
    return (el.text or "").strip() if el is not None else ""


def collect_one(E, ip, label):
    import xml.etree.ElementTree as ET
    d = {"state": "ok", "label": label, "ip": ip, "host": "?", "model": "?",
         "cpu_temp": None, "sys_temp": None, "uptime_d": None, "fan_ok": True,
         "volumes": [], "disks": [], "problems": []}
    user = E.get("QNAP_USERNAME", "admin")
    pw = E.get("QNAP_PASSWORD", "")
    if not ip or not pw:
        return {"state": "degraded", "label": label, "ip": ip or "?",
                "note": "QNAP creds not set", "volumes": [], "disks": [], "problems": []}
    aurl = f"https://{ip}/cgi-bin/authLogin.cgi"
    adata = urllib.parse.urlencode({"user": user, "pwd": b64(pw)}).encode()
    abody = urllib.request.urlopen(urllib.request.Request(aurl, data=adata),
                                   timeout=TIMEOUT, context=CTX).read().decode("utf-8", "replace")
    m = re.search(r"<authSid><!\[CDATA\[(.*?)\]\]></authSid>", abody) or re.search(r"<authSid>(.*?)</authSid>", abody)
    sid = m.group(1) if m else ""
    if not sid:
        raise RuntimeError("QNAP auth failed")

    def get(path):
        return urllib.request.urlopen(f"https://{ip}{path}", timeout=TIMEOUT, context=CTX).read().decode("utf-8", "replace")

    si = ET.fromstring(get(f"/cgi-bin/management/manaRequest.cgi?subfunc=sysinfo&sid={sid}"))
    def sif(tag):
        e = si.find(".//" + tag)
        return _text(e)
    d["host"] = sif("hostname") or "?"
    d["model"] = sif("displayModelName") or "?"
    try: d["cpu_temp"] = int(sif("cpu_tempc"))
    except (ValueError, TypeError): pass
    try: d["sys_temp"] = int(sif("sys_tempc"))
    except (ValueError, TypeError): pass
    try: d["uptime_d"] = int(sif("uptime_day"))
    except (ValueError, TypeError): pass
    fan_ok = True
    for k in range(1, 6):
        st = si.find(f".//sysfan{k}_stat")
        fl = si.find(f".//sysfan_fail{k}")
        if st is not None and _text(st) not in ("0", ""): fan_ok = False
        if fl is not None and _text(fl) == "1": fan_ok = False
    d["fan_ok"] = fan_ok
    if not fan_ok:
        d["problems"].append("fan fault")
    try: sys_warn = int(sif("SysTempWarnT") or 60)
    except ValueError: sys_warn = 60
    if d["sys_temp"] is not None and d["sys_temp"] >= sys_warn:
        d["problems"].append(f"system temp {d['sys_temp']}C >= {sys_warn}C")
        d["state"] = "warn"
    vu = ET.fromstring(get(f"/cgi-bin/management/chartReq.cgi?chart_func=disk_usage&disk_select=all&include=all&sid={sid}"))
    labels = {}
    for vol in vu.findall(".//volumeList/volume"):
        vv = _text(vol.find("volumeValue"))
        labels[vv] = _text(vol.find("volumeLabel")) or ("Vol " + vv)
        vstat = _text(vol.find("volumeStatus"))
        if vstat not in ("0", "", "Ready"):
            d["problems"].append(f"volume {labels[vv]} status={vstat}")
    for vu_el in vu.findall(".//volumeUseList/volumeUse"):
        vv = _text(vu_el.find("volumeValue"))
        try:
            tot = int(_text(vu_el.find("total_size")) or 0)
            free = int(_text(vu_el.find("free_size")) or 0)
        except ValueError:
            continue
        if not tot: continue
        used = tot - free
        pct = round(100 * used / tot, 1)
        nm = labels.get(vv, "Vol " + vv)
        d["volumes"].append({"name": nm, "pct": pct,
                             "used_t": round(used / 1e12, 2), "total_t": round(tot / 1e12, 2)})
        if pct > 90: d["problems"].append(f"volume {nm} {pct:.0f}% full"); d["state"] = "crit"
        elif pct > 85 and d["state"] == "ok": d["state"] = "warn"
    d["volumes"].sort(key=lambda x: -x["pct"])
    dh = ET.fromstring(get(f"/cgi-bin/disk/qsmart.cgi?func=all_hd_data&sid={sid}"))
    for e in dh.findall(".//Disk_Info/entry"):
        alias = _text(e.find("Disk_Alias"))
        health = _text(e.find("Health"))
        dstat = _text(e.find("Disk_Status"))
        tc = _text(e.find("Temperature/oC"))
        try: tc = int(tc)
        except ValueError: tc = None
        if dstat == "-5" and tc is None: continue
        d["disks"].append({"alias": alias, "health": health or "?", "status": dstat, "temp": tc})
        if health and health.upper() not in ("OK", "GOOD", "NORMAL", ""):
            d["problems"].append(f"disk {alias} health={health}"); d["state"] = "crit"
        elif dstat not in ("0", "", "Ready", "ready"):
            d["problems"].append(f"disk {alias} status={dstat}")
            if d["state"] != "crit": d["state"] = "warn"
    return d


def collect(E, card_cfg=None):
    units = [("QNAP1", E.get("QNAP1_HOST")), ("QNAP2", E.get("QNAP2_HOST")),
             ("QNAP3", E.get("QNAP3_HOST"))]
    out = {"state": "ok", "units": []}
    order = ["ok", "degraded", "warn", "crit", "error"]
    worst = "ok"
    for label, ip in units:
        try:
            r = collect_one(E, ip, label)
        except Exception as e:
            r = {"state": "error", "label": label, "ip": ip or "?",
                 "error": f"{type(e).__name__}: {str(e)[:100]}",
                 "volumes": [], "disks": [], "problems": []}
        out["units"].append(r)
        if order.index(r.get("state", "error")) > order.index(worst):
            worst = r.get("state", "error")
    out["state"] = worst
    return out
