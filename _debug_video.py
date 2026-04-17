from core.extractor import _get_visitor_data, _innertube_player, _CLIENT_ORDER

vd = _get_visitor_data()
print("visitorData:", (vd[:40] + "...") if len(vd) > 40 else (vd or "EMPTY"))
print()

vid = "E8IYhwg3iKA"
for client in _CLIENT_ORDER:
    try:
        r  = _innertube_player(vid, client)
        ps = r.get("playabilityStatus", {})
        sd = r.get("streamingData", {})
        n  = len(sd.get("formats", []) + sd.get("adaptiveFormats", []))
        reason = ps.get("reason", "")[:70]
        print(f"[{client}] {ps.get('status')} streams={n} reason={reason}")
    except Exception as e:
        print(f"[{client}] ERROR: {e}")
