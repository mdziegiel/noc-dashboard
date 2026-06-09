"""Custom URL collector — user-defined REST endpoints with JSONPath extraction."""
import json
import re
from .utils import jget


def _jsonpath_simple(obj, path):
    """Very simple JSONPath subset: $.key.key[0].key"""
    parts = re.split(r'[.\[\]]+', path.lstrip("$").lstrip("."))
    cur = obj
    for part in parts:
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def collect(E, card_cfg=None):
    cfg = card_cfg or {}
    url = cfg.get("url", "")
    if not url:
        return {"state": "degraded", "note": "custom_url: no url configured"}
    headers = cfg.get("headers", {}) or {}
    fields = cfg.get("fields", []) or []
    d = {"state": "ok", "values": {}}
    try:
        data = jget(url, headers)
    except Exception as e:
        return {"state": "error", "note": f"fetch failed: {type(e).__name__}: {e}", "values": {}}
    for field in fields:
        name = field.get("name", "value")
        path = field.get("path", "")
        val = _jsonpath_simple(data, path) if path else data
        d["values"][name] = val
    # state from a designated field
    state_field = cfg.get("state_field")
    if state_field:
        raw_state = str(d["values"].get(state_field, "ok")).lower()
        ok_values = cfg.get("ok_values", ["ok", "up", "true", "1", "online"])
        d["state"] = "ok" if raw_state in [str(v).lower() for v in ok_values] else "warn"
    return d
