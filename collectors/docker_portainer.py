"""Docker / Portainer collector."""
from .utils import jget


def collect(E, card_cfg=None):
    d = {"state": "ok", "running": 0, "total": 0, "envs": 0, "bad": []}
    base = E.get("PORTAINER_URL", "").strip().rstrip("/")
    user = E.get("PORTAINER_USERNAME", "").strip()
    pw = E.get("PORTAINER_PASSWORD", "").strip()
    if not base or not user or not pw or pw.startswith("<"):
        return {"state": "degraded", "note": "Portainer creds not set",
                "running": 0, "total": 0, "envs": 0, "bad": []}
    jwt = jget(f"{base}/api/auth", data={"Username": user, "Password": pw}, method="POST")["jwt"]
    auth = {"Authorization": f"Bearer {jwt}"}
    endpoints = jget(f"{base}/api/endpoints", auth)
    d["envs"] = len(endpoints)
    for ep in endpoints:
        epid = ep.get("Id")
        try:
            cs = jget(f"{base}/api/endpoints/{epid}/docker/containers/json?all=1", auth)
        except Exception as e:
            d["bad"].append(f"{ep.get('Name', epid)} unreachable: {type(e).__name__}")
            continue
        run = [c for c in cs if c.get("State") == "running"]
        d["running"] += len(run)
        d["total"] += len(cs)
        for c in cs:
            nm = c.get("Names", ["?"])[0].lstrip("/")
            if "unhealthy" in c.get("Status", "").lower():
                d["bad"].append(f"UNHEALTHY {nm}")
            elif c.get("State") != "running":
                d["bad"].append(f"down {nm}")
    if d["bad"]:
        d["state"] = "warn"
    return d
