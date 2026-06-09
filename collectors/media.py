"""Media stack collectors: Plex, Tautulli, Sonarr, Radarr, Prowlarr, SABnzbd, Overseerr."""
from .utils import jget


UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def _arr_base(E, prefix):
    base = E.get(prefix + "_URL", "").strip().rstrip("/")
    key = E.get(prefix + "_API_KEY", "").strip()
    return base, key


def collect_plex(E, card_cfg=None):
    base = E.get("PLEX_URL", "").strip().rstrip("/")
    tok = E.get("PLEX_TOKEN", "").strip()
    if not base or not tok:
        return {"state": "degraded", "note": "PLEX not configured"}
    h = {"X-Plex-Token": tok, "Accept": "application/json"}
    sess = jget(f"{base}/status/sessions", h).get("MediaContainer", {})
    streams = int(sess.get("size", 0) or 0)
    libs = jget(f"{base}/library/sections", h).get("MediaContainer", {}).get("Directory", [])
    movies = shows = 0
    for lib in libs:
        k, t = lib.get("key"), lib.get("type")
        try:
            mc = jget(f"{base}/library/sections/{k}/all?X-Plex-Container-Start=0&X-Plex-Container-Size=0", h).get("MediaContainer", {})
            sz = int(mc.get("totalSize", mc.get("size", 0)) or 0)
        except Exception:
            sz = 0
        if t == "movie": movies += sz
        elif t == "show": shows += sz
    return {"state": "ok", "streams": streams, "movies": movies, "shows": shows}


def collect_tautulli(E, card_cfg=None):
    base = E.get("TAUTULLI_URL", "").strip().rstrip("/")
    key = E.get("TAUTULLI_API_KEY", "").strip()
    if not base or not key:
        return {"state": "degraded", "note": "TAUTULLI not configured"}
    act = jget(f"{base}/api/v2?apikey={key}&cmd=get_activity").get("response", {}).get("data", {})
    streams = int(act.get("stream_count", 0) or 0)
    pbd = jget(f"{base}/api/v2?apikey={key}&cmd=get_plays_by_date&time_range=1").get("response", {}).get("data", {})
    plays_today = 0
    for s in pbd.get("series", []):
        if s.get("name") == "Total":
            plays_today = sum(int(x or 0) for x in (s.get("data") or []))
    top_user, top_plays = None, 0
    try:
        hs = jget(f"{base}/api/v2?apikey={key}&cmd=get_home_stats&time_range=1&stats_count=5").get("response", {}).get("data", [])
        for sec in hs:
            if sec.get("stat_id") == "top_users":
                rows = sec.get("rows", [])
                if rows:
                    top_user = rows[0].get("friendly_name") or rows[0].get("user")
                    top_plays = rows[0].get("total_plays", 0)
                break
    except Exception:
        pass
    return {"state": "ok", "streams": streams, "plays_today": plays_today,
            "top_user": top_user, "top_plays": top_plays}


def collect_sonarr(E, card_cfg=None):
    base, key = _arr_base(E, "SONARR")
    if not base or not key:
        return {"state": "degraded", "note": "SONARR not configured"}
    h = {"X-Api-Key": key}
    series = jget(f"{base}/api/v3/series", h)
    monitored = sum(1 for s in series if s.get("monitored"))
    queue = jget(f"{base}/api/v3/queue?page=1&pageSize=1", h).get("totalRecords", 0)
    missing = jget(f"{base}/api/v3/wanted/missing?page=1&pageSize=1", h).get("totalRecords", 0)
    return {"state": "warn" if (queue or missing) else "ok",
            "total": len(series), "monitored": monitored, "queue": queue, "missing": missing}


def collect_radarr(E, card_cfg=None):
    base, key = _arr_base(E, "RADARR")
    if not base or not key:
        return {"state": "degraded", "note": "RADARR not configured"}
    h = {"X-Api-Key": key}
    movies = jget(f"{base}/api/v3/movie", h)
    monitored = sum(1 for m in movies if m.get("monitored"))
    queue = jget(f"{base}/api/v3/queue?page=1&pageSize=1", h).get("totalRecords", 0)
    missing = jget(f"{base}/api/v3/wanted/missing?page=1&pageSize=1", h).get("totalRecords", 0)
    return {"state": "warn" if (queue or missing) else "ok",
            "total": len(movies), "monitored": monitored, "queue": queue, "missing": missing}


def collect_prowlarr(E, card_cfg=None):
    base, key = _arr_base(E, "PROWLARR")
    if not base or not key:
        return {"state": "degraded", "note": "PROWLARR not configured"}
    h = {"X-Api-Key": key}
    idx = jget(f"{base}/api/v1/indexer", h)
    enabled = sum(1 for i in idx if i.get("enable"))
    try:
        failing = len(jget(f"{base}/api/v1/indexerstatus", h))
    except Exception:
        failing = 0
    return {"state": "warn" if failing else "ok", "total": len(idx),
            "enabled": enabled, "healthy": max(enabled - failing, 0), "failing": failing}


def collect_sabnzbd(E, card_cfg=None):
    base = E.get("SABNZBD_URL", "").strip().rstrip("/")
    key = E.get("SABNZBD_API_KEY", "").strip()
    if not base or not key:
        return {"state": "degraded", "note": "SABNZBD not configured"}
    q = jget(f"{base}/api?mode=queue&output=json&apikey={key}").get("queue", {})
    slots = int(q.get("noofslots", 0) or 0)
    kbps = float(q.get("kbpersec", 0) or 0)
    speed_mbps = round(kbps / 1024, 1)
    status = q.get("status", "Idle")
    mbleft = q.get("mbleft", "0")
    timeleft = q.get("timeleft", "0:00:00")
    day_gb = 0.0
    try:
        srv = jget(f"{base}/api?mode=server_stats&output=json&apikey={key}")
        day_gb = round(int(srv.get("day", 0) or 0) / (1024 ** 3), 2)
    except Exception:
        pass
    return {"state": "warn" if status.lower() == "paused" else "ok",
            "slots": slots, "speed_mbps": speed_mbps, "status": status,
            "mbleft": mbleft, "timeleft": timeleft, "day_gb": day_gb}


def collect_overseerr(E, card_cfg=None):
    base = E.get("OVERSEERR_URL", "").strip().rstrip("/")
    key = E.get("OVERSEERR_API_KEY", "").strip()
    if not base or not key:
        return {"state": "degraded", "note": "OVERSEERR not configured"}
    h = {"X-Api-Key": key, "User-Agent": UA, "Accept": "application/json"}
    candidates = [base]
    dom = "https://overseerr.mrdtech.me"
    if dom != base:
        candidates.append(dom)
    last_err = None
    for url in candidates:
        try:
            c = jget(f"{url}/api/v1/request/count", h)
            pending = c.get("pending", 0)
            return {"state": "warn" if pending else "ok", "pending": pending,
                    "approved": c.get("approved", 0), "available": c.get("available", 0),
                    "processing": c.get("processing", 0), "total": c.get("total", 0)}
        except Exception as e:
            last_err = e
    raise last_err
