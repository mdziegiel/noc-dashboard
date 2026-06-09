"""Cloudflare analytics collector."""
import datetime
from .utils import jget


def collect(E, card_cfg=None):
    token = E.get("CLOUDFLARE_TOKEN", "").strip()
    zone = E.get("CLOUDFLARE_ZONE_ID", "").strip()
    if not token or not zone or token.startswith("<"):
        return {"state": "degraded", "note": "Cloudflare token/zone not set",
                "requests": 0, "threats": 0, "bytes": 0, "waf_events": None}
    d = {"state": "ok", "requests": 0, "threats": 0, "bytes": 0,
         "waf_events": None, "waf_blocked": None, "waf_note": None}
    api = "https://api.cloudflare.com/client/v4/graphql"
    auth = {"Authorization": f"Bearer {token}"}
    today = datetime.date.today().isoformat()
    dt24 = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    q1 = ("query($z:String!,$d:String!){viewer{zones(filter:{zoneTag:$z}){"
          "httpRequests1dGroups(limit:1,filter:{date_geq:$d}){"
          "sum{requests bytes threats}}}}}")
    r1 = jget(api, auth, {"query": q1, "variables": {"z": zone, "d": today}}, "POST")
    if r1.get("errors"):
        raise RuntimeError("CF http analytics: " + str(r1["errors"][0].get("message", ""))[:120])
    grp = r1["data"]["viewer"]["zones"][0]["httpRequests1dGroups"]
    if grp:
        s = grp[0]["sum"]
        d["requests"] = s.get("requests", 0)
        d["threats"] = s.get("threats", 0)
        d["bytes"] = s.get("bytes", 0)
    if d["threats"]:
        d["state"] = "warn"
    q2 = ("query($z:String!,$d:Time!){viewer{zones(filter:{zoneTag:$z}){"
          'all:firewallEventsAdaptiveGroups(limit:1,filter:{datetime_geq:$d}){count}'
          'blk:firewallEventsAdaptiveGroups(limit:1,filter:{datetime_geq:$d,action:"block"}){count}'
          "}}}}")
    try:
        r2 = jget(api, auth, {"query": q2, "variables": {"z": zone, "d": dt24}}, "POST")
        if r2.get("errors"):
            msg = str(r2["errors"][0].get("message", ""))
            if "does not have access" in msg or "authz" in msg.lower():
                d["waf_note"] = "WAF analytics needs Pro plan"
            else:
                d["waf_note"] = msg[:60]
        else:
            z = r2["data"]["viewer"]["zones"][0]
            d["waf_events"] = (z.get("all") or [{}])[0].get("count", 0)
            d["waf_blocked"] = (z.get("blk") or [{}])[0].get("count", 0)
            if d["waf_blocked"] and d["state"] == "ok":
                d["state"] = "warn"
    except Exception as e:
        d["waf_note"] = f"WAF query failed: {type(e).__name__}"
    return d
