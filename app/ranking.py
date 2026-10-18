"""Doctor scoring: Bayesian rating + distance + review volume."""
from math import radians, sin, cos, asin, sqrt


def bayesian_rating(rating: float, n: int, global_avg: float = 4.2, m: int = 25) -> float:
    """Pulls ratings with few reviews toward the global average."""
    return (n / (n + m)) * rating + (m / (n + m)) * global_avg


def distance_km(lat1, lon1, lat2, lon2) -> float:
    dlat, dlon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 6371 * 2 * asin(sqrt(a))


def score_place(place: dict, user_lat: float, user_lng: float) -> dict:
    """Score one place out of 1, and report the fields that produced it.

    Two formulas, because the two data sources do not measure the same things:

    * unrated place (OpenStreetMap, which has no ratings at all): distance
      50%, whether the tags say it is the right kind of specialist 35%, how
      complete the listing is 15%. Distance alone would hand first place to
      whatever happens to be nearest - a physiotherapy clinic next door
      outranking the gastroenterologist 2 km away - so being the right kind of
      doctor is worth more than being marginally closer.
    * rated place: Bayesian rating 55%, distance 25%, review volume 20% - the
      original formula, unchanged, for whenever a source with ratings is used
      again.

    Weights are a product decision, not a fact: change them here, in one place.
    """
    n = place.get("userRatingCount") or 0
    rating = place.get("rating")
    loc = place["location"]
    d = distance_km(user_lat, user_lng, loc["latitude"], loc["longitude"])
    dist_norm = 1 / (1 + d)

    if rating is None or n <= 0:
        completeness = sum(bool(place.get(field)) for field in
                           ("phone", "website", "opening_hours")) / 3
        is_match = 1.0 if place.get("speciality_match") else 0.0
        total = 0.50 * dist_norm + 0.35 * is_match + 0.15 * completeness
    else:
        rating_norm = bayesian_rating(rating, n) / 5
        total = 0.55 * rating_norm + 0.25 * dist_norm + 0.20 * min(n / 200, 1)

    return {
        "id": place.get("id"),
        "name": place.get("displayName", {}).get("text", "Unknown"),
        "address": place.get("formattedAddress", ""),
        "rating": rating,
        "reviews": n,
        "distance_km": round(d, 1),
        "score": round(total, 3),
        # Only meaningful when there are reviews to be few of. On OSM data
        # every place would be flagged "limited reviews", which would say
        # nothing about any of them.
        "limited_reviews": rating is not None and n < 10,
        # Passed through so the UI can tell a real speciality match from a
        # nearby fallback instead of presenting the two as equally on-topic.
        "speciality": place.get("speciality", ""),
        "speciality_match": bool(place.get("speciality_match")),
        "kind": place.get("kind", ""),
        "phone": place.get("phone", ""),
        "website": place.get("website", ""),
        "opening_hours": place.get("opening_hours", ""),
        "osm_url": place.get("osm_url", ""),
        # Coordinates passed through so the frontend can put a marker on the
        # map (Stage 8). The distance above was computed from these same
        # values in app/places.py.
        "lat": loc["latitude"],
        "lng": loc["longitude"],
    }


def rank_places(places, user_lat, user_lng, top_n: int = 10):
    scored = [score_place(p, user_lat, user_lng) for p in places if "location" in p]
    return sorted(scored, key=lambda x: -x["score"])[:top_n]
