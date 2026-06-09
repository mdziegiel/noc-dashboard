"""Home Assistant collector."""
from .utils import jget


def collect(E, card_cfg=None):
    d = {"state": "ok", "entities": 0, "alerts_on": 0, "notifications": 0,
         "unavailable": 0, "alert_names": [], "domains": 0}
    base = E.get("HASS_URL", "").rstrip("/")
    tok = E.get("HASS_TOKEN", "")
    if not base or not tok or tok.startswith("<"):
        return {"state": "degraded", "note": "HASS_URL/HASS_TOKEN not set",
                "entities": 0, "alerts_on": 0, "notifications": 0,
                "unavailable": 0, "alert_names": [], "domains": 0}
    states = jget(base + "/api/states", {"Authorization": "Bearer " + tok})
    d["entities"] = len(states)
    d["domains"] = len(set(e["entity_id"].split(".")[0] for e in states))
    on_alerts = [e for e in states if e["entity_id"].startswith("alert.") and e.get("state") == "on"]
    notes = [e for e in states if e["entity_id"].startswith("persistent_notification.")]
    unavail = [e for e in states if e.get("state") in ("unavailable", "unknown")]
    d["alerts_on"] = len(on_alerts)
    d["notifications"] = len(notes)
    d["unavailable"] = len(unavail)
    d["alert_names"] = sorted(
        (e.get("attributes", {}).get("friendly_name") or e["entity_id"]) for e in on_alerts)[:6]
    if on_alerts:
        d["state"] = "crit"
    elif notes:
        d["state"] = "warn"
    return d
