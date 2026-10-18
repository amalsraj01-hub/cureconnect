"""OpenStreetMap / Overpass API - doctors and clinics near a location.

No API key, no billing account, no cost per search. This replaced a Google
Places API (New) Text Search call that billed a Text Search (Enterprise)
request every time, because app/ranking.py needs `rating` and
`userRatingCount` and the top-tier field sets the price of the whole request.

What that trade actually bought and cost, honestly:

  + free, keyless, nothing to leak, nothing to cap, nothing to be billed for
  + opening_hours, phone and website come back, which the Google Text Search
    fields we asked for did not include
  - OSM has no star ratings and no review counts. Those fields do not exist
    here, so app/ranking.py scores on distance + speciality + how complete the
    listing is instead (see the note in that file)
  - coverage of small Indian towns is thin, and speciality tagging is thinner
    still, which is why the name filter below matters as much as the tag filter

Overpass is a shared community service run on donations, with a usage policy:
send a real User-Agent, keep queries small, do not poll it in a loop. Details
and the attribution requirement are in docs/places_osm.md.

Data (c) OpenStreetMap contributors, licensed ODbL 1.0. Any screen showing
these results has to credit OpenStreetMap - see docs/places_osm.md.
"""
import re
import time

import requests

URL = "https://overpass-api.de/api/interpreter"

# Overpass asks callers to identify themselves, and a default python-requests
# User-Agent is a good way to get throttled or blocked. Put a real contact
# address here before this runs anywhere public: it is how the Overpass
# operators reach you if your queries become a problem for everyone else.
USER_AGENT = "CureConnect/0.2 (student health-navigation project; stage-5 demo)"

# The server-side ceiling asked for, and the client-side ceiling, which has to
# be larger. Overpass is shared and a busy window can take 20+ seconds to
# answer; too short a client timeout turns a slow answer into a failure and
# throws away work the server already did.
SERVER_TIMEOUT_S = 25
HTTP_TIMEOUT_S = SERVER_TIMEOUT_S + 10

# One polite retry for a shared community server: 429/5xx or a dropped
# connection usually means Overpass is having a bad moment, not that the
# query is wrong. One retry only - looping would go against its usage
# policy, and scripts/places_smoke.py already follows the same rule.
MAX_ATTEMPTS = 2
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_DELAY_S = 3

# The furthest one query may reach. Not an Overpass limit - a politeness limit,
# so a careless call cannot ask the server to walk half a state.
MAX_RADIUS_M = 50000

# A doctor's office or clinic is tagged under one of several keys in OSM, often
# under only one of them, so all five are queried. Note the value is "doctors"
# (plural): there is no amenity=doctor in the OSM schema.
#
# amenity=hospital is in the list on purpose. In a smaller town like Kannur a
# specialist usually practises *inside* the district or private hospital rather
# than at a standalone clinic, so leaving hospitals out would remove the place
# the specialist is most likely to be found - the same failure the name regex
# below exists to guard against. The cost is that general hospitals come back
# too; they are shown as what they are, nearby with no speciality claimed.
DOCTOR_FILTERS = (
    ("amenity", "doctors"),
    ("amenity", "clinic"),
    ("amenity", "hospital"),
    ("healthcare", "doctor"),
    ("healthcare", "clinic"),
)

# specialist (the wording app/mapping.py produces) -> (
#     OSM healthcare:speciality values meaning this specialist,
#     regex matching a facility name that names this specialist)
#
# The name regex is not decoration. In a town like Kannur a gastroenterology
# clinic is very often tagged amenity=clinic and nothing else, so a name like
# "Kannur Gastro Care" is frequently the only signal that it is not a GP.
SPECIALISTS = {
    "gastroenterologist": (
        {"gastroenterology", "hepatology", "proctology"},
        r"gastro|hepatolog|digestive|liver"),
    "cardiologist": (
        {"cardiology", "cardiovascular"},
        r"cardio|heart"),
    "dermatologist": (
        {"dermatology", "venereology"},
        r"derma|skin"),
    "neurologist": (
        {"neurology"},
        r"neuro|\bbrain\b"),
    "orthopedist": (
        {"orthopaedics", "orthopedics", "orthopaedic", "orthopedic",
         "rheumatology"},
        r"ortho|\bbone\b|joint|spine"),
    "pulmonologist": (
        {"pulmonology", "pneumology", "respiratory"},
        r"pulmo|respirat|\blung\b"),
    "endocrinologist": (
        {"endocrinology", "diabetology"},
        r"endocrin|diabet|thyroid"),
    "ent specialist": (
        {"otolaryngology", "otorhinolaryngology", "ent"},
        r"\bent\b|otolaryng"),
    "infectious disease specialist": (
        {"infectious_diseases", "infectirology"},
        r"infecti|tropical medicine"),
    "general surgeon": (
        {"surgery", "general_surgery"},
        r"surger|surgical"),
    "vascular surgeon": (
        {"vascular_surgery", "angiology"},
        r"vascular|varicose|\bvein"),
    # The fallback from app/mapping.py, and the one most towns actually have:
    # an ordinary GP, tagged healthcare:speciality=general or left untagged.
    "general physician": (
        {"general", "internal_medicine", "general_medicine", "family_medicine"},
        r"general physician|general practitioner|\bgp\b|family clinic|"
        r"internal medicine|polyclinic|poly clinic"),
}


def validate_query(lat: float, lng: float, radius: int) -> None:
    """Reject input that would make Overpass do silly work, and say why."""
    if not -90 <= lat <= 90 or not -180 <= lng <= 180:
        raise ValueError(f"coordinates out of range: lat={lat}, lng={lng}")
    if not 0 < radius <= MAX_RADIUS_M:
        raise ValueError(
            f"radius must be between 1 and {MAX_RADIUS_M} metres, got {radius}")


def build_query(lat: float, lng: float, radius: int) -> str:
    """The Overpass QL for one search.

    nwr means node, way or relation: a clinic can be mapped as any of the
    three, and only a node has lat/lon of its own, which is why `out center`
    is there - it gives ways and relations a coordinate to be scored by.
    """
    clauses = "\n".join(
        f'  nwr["{key}"="{value}"](around:{radius},{lat},{lng});'
        for key, value in DOCTOR_FILTERS)
    return (f"[out:json][timeout:{SERVER_TIMEOUT_S}];\n"
            f"(\n{clauses}\n);\n"
            f"out center;")


def osm_specialities(tags: dict) -> set:
    """healthcare:speciality is free text: "gastroenterology", "general", or a
    semicolon list like "general;diabetes". Normalised so it can be compared."""
    raw = tags.get("healthcare:speciality", "")
    return {part.strip().lower().replace(" ", "_")
            for part in raw.split(";") if part.strip()}


def matches_specialist(tags: dict, specialist: str) -> bool:
    """Does this facility's tagging - or failing that its name - mean the
    specialist asked for?

    Takes tags rather than a finished place so the smoke script can report how
    many nearby facilities matched on the OSM tag alone, which is the number
    that tells you whether speciality tagging exists in this town yet.
    """
    wanted, name_pattern = SPECIALISTS.get(specialist.strip().lower(),
                                           (frozenset(), None))
    if osm_specialities(tags) & wanted:
        return True
    return bool(name_pattern and re.search(name_pattern,
                                           tags.get("name", ""),
                                           re.IGNORECASE))


def _display_name(tags: dict) -> str:
    """OSM entries are often unnamed, and saying so beats inventing a name.

    app/ranking.py reads displayName.text, so the shape stays exactly as it was
    in the Google version this replaced and no caller has to care about the
    change of source.
    """
    if tags.get("name"):
        return tags["name"]
    kind = tags.get("amenity") or tags.get("healthcare") or "health facility"
    return f"Unnamed {kind} (no name in OpenStreetMap)"


def _address(tags: dict) -> str:
    parts = [tags.get(key) for key in ("addr:housenumber", "addr:street",
                                       "addr:suburb", "addr:city",
                                       "addr:postcode")]
    return ", ".join(part for part in parts if part)


def place_from_element(element: dict, specialist: str):
    """One Overpass element -> one place, in the shape app/ranking.py expects.

    Returns None when the element has no usable coordinate: a way can carry a
    `center`, but a way without one, or a relation, cannot be scored by
    distance at all and is dropped rather than crashed over.
    """
    tags = element.get("tags", {})
    center = element.get("center") or {}
    lat = element.get("lat", center.get("lat"))
    lng = element.get("lon", center.get("lon"))
    if lat is None or lng is None:
        return None
    osm_type, osm_id = element.get("type"), element.get("id")
    return {
        "id": f"osm:{osm_type}/{osm_id}",
        "displayName": {"text": _display_name(tags)},
        "formattedAddress": _address(tags),
        # "rating" and "userRatingCount" are deliberately absent. OpenStreetMap
        # has no such data, and a 0 would read as "rated zero", which is a
        # different and much worse claim than "not rated anywhere".
        "location": {"latitude": lat, "longitude": lng},
        "speciality": tags.get("healthcare:speciality", ""),
        "speciality_match": matches_specialist(tags, specialist),
        "kind": tags.get("amenity") or tags.get("healthcare", ""),
        "phone": tags.get("contact:phone") or tags.get("phone", ""),
        "website": tags.get("contact:website") or tags.get("website", ""),
        "opening_hours": tags.get("opening_hours", ""),
        # Kept so any screen showing this can credit the source, and so you can
        # open the very same object on openstreetmap.org and check it by eye.
        "osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}",
    }


def parse_elements(payload: dict, specialist: str) -> list:
    """Every usable place in an Overpass response, unmatched ones included.

    Unmatched facilities are kept on purpose: in a small town the real choice is
    often "the GP next door" or "nothing at all", and app/ranking.py can only
    rank what it is handed. Each place carries speciality_match, so the caller
    can tell a real match from a fallback instead of guessing from the order.
    """
    places = []
    for element in payload.get("elements", []):
        place = place_from_element(element, specialist)
        if place:
            places.append(place)
    return places


def fetch_raw(lat: float, lng: float, radius: int) -> dict:
    """The untouched Overpass JSON for one search.

    find_doctors is this plus parsing, split out so scripts/places_smoke.py can
    show you the real response - every tag, every coordinate - when you want to
    check by eye whether the data or the parsing is the problem.
    """
    validate_query(lat, lng, radius)
    request_args = {
        "data": {"data": build_query(lat, lng, radius)},
        "headers": {"User-Agent": USER_AGENT, "Accept": "application/json"},
        "timeout": HTTP_TIMEOUT_S,
    }
    # One retry for transient failures only (RETRY_STATUSES, timeout,
    # connection drop). Anything else - and a second failure of the same
    # kind - is raised for app/main.py to turn into a 502 with the reason.
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(URL, **request_args)
            response.raise_for_status()
            break
        except requests.HTTPError as e:
            status = getattr(e.response, "status_code", None)
            if status not in RETRY_STATUSES or attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_DELAY_S)
        except (requests.Timeout, requests.ConnectionError):
            if attempt == MAX_ATTEMPTS:
                raise
            time.sleep(RETRY_DELAY_S)
    payload = response.json()
    # Overpass reports some failures inside an HTTP 200, in "remark" - for
    # example "runtime error: Query timed out". Without this check a timeout
    # would reach the caller as the cheerful empty answer "no doctors here".
    remark = payload.get("remark")
    if remark:
        raise RuntimeError(f"Overpass returned no usable answer: {remark}")
    return payload


def find_doctors(specialist: str, lat: float, lng: float, radius: int = 5000):
    """Map doctors and clinics within `radius` metres of (lat, lng).

    Raises ValueError on impossible input, requests.HTTPError when Overpass
    refuses or is overloaded, RuntimeError when it answers without usable data,
    and requests.RequestException when it cannot be reached. app/main.py turns
    every one of those into a 502 with the reason attached.
    """
    return parse_elements(fetch_raw(lat, lng, radius), specialist)
