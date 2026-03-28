import math

def haversine_m(lat1, lng1, lat2, lng2):
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)

    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def normalize_name(value):
    return str(value or "").strip().lower()


def coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def merge_live_with_db(db_lots, live_lots):
    live_by_name = {normalize_name(x.get("name")): x for x in live_lots}
    merged = []

    for db in db_lots:
        live = live_by_name.get(normalize_name(db.get("name")), {})

        merged.append({
            "id": db["id"],
            "name": db["name"],
            "lat": coerce_float(db.get("lat")),
            "lng": coerce_float(db.get("lng")),
            "capacity": live.get("total_spots", db.get("capacity")),
            "available": live.get("available", db.get("available")),
            "last_updated": live.get("last_updated", db.get("last_updated")),
        })

    return merged


def _scale(value, min_value, max_value):
    if max_value <= min_value:
        return 1.0
    return (value - min_value) / (max_value - min_value)


def recommend_lots(user_lat, user_lng, lots, limit=3, distance_weight=0.7, available_weight=0.3):
    candidates = []

    for lot in lots:
        lat = coerce_float(lot.get("lat"))
        lng = coerce_float(lot.get("lng"))
        available = lot.get("available")

        if lat is None or lng is None:
            continue
        if not isinstance(available, int) or available <= 0:
            continue

        distance_m = haversine_m(user_lat, user_lng, lat, lng)
        candidates.append({
            **lot,
            "distance_m": round(distance_m, 1),
        })

    if not candidates:
        return []

    min_distance = min(x["distance_m"] for x in candidates)
    max_distance = max(x["distance_m"] for x in candidates)
    min_available = min(x["available"] for x in candidates)
    max_available = max(x["available"] for x in candidates)

    total_weight = distance_weight + available_weight
    if total_weight <= 0:
        total_weight = 1.0

    for lot in candidates:
        distance_score = 1 - _scale(lot["distance_m"], min_distance, max_distance)
        available_score = _scale(lot["available"], min_available, max_available)

        lot["score"] = round(
            ((distance_weight * distance_score) + (available_weight * available_score)) / total_weight,
            4,
        )

    candidates.sort(key=lambda x: (-x["score"], x["distance_m"], -x["available"], x["name"]))
    return candidates[:max(1, int(limit))]
