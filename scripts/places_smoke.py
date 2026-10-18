"""One real Overpass (OpenStreetMap) call at a real location - the Stage 5 check.

Free: Overpass needs no key, no account and no billing, so unlike the Google
Places version this replaced, running it costs nothing and it is safe to repeat.
It is still a shared community service, so do not put it in a loop.

It follows the same path app/main.py uses - safety check, classifier, condition
-> specialist, app/places.py, app/ranking.py - and prints what a user standing
at the given coordinates would actually be shown.

Why Kannur: it is the town this app is being built for, small enough that "a
doctor near me" can be judged by eye, and far enough from a metro that a broken
query shows up as an empty list instead of hiding behind dozens of plausible
results.

Run from the project root (the folder holding app/ and data/):

    python scripts/places_smoke.py
    python scripts/places_smoke.py --specialist Gastroenterologist
    python scripts/places_smoke.py --radius 15000 --raw 5

--raw N prints the first N elements of the untouched Overpass response, tags and
all, which is how you tell a data problem from a parsing problem. --show-query
prints the exact Overpass QL that was sent.

Overpass is a free, donated, shared service and it does get busy: this script
waits 20s and makes one more attempt when Overpass answers 429 or 504
(--retry-wait 0 turns that off). A retry loop would be abuse; one patient retry
is just good manners.

Exit codes: 0 printed a report, 1 Overpass refused or was unreachable,
3 the safety check stopped it. No exit code 2 any more: there is no key to miss.

Doctor data (c) OpenStreetMap contributors, licensed ODbL 1.0 - see
docs/places_osm.md for what that requires of anything user-facing.
"""
import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

import requests

# Running "python scripts/places_smoke.py" puts scripts/ on sys.path, not the
# project root, so importing the app package needs this small nudge.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.classifier import predict  # noqa: E402
from app import places  # noqa: E402
from app.ranking import rank_places  # noqa: E402
from app.safety import EMERGENCY_MESSAGE, is_emergency  # noqa: E402

# Kannur town centre, Kerala (11.8745 N, 75.3704 E). Town centre, not a clinic.
KANNUR_LAT, KANNUR_LNG = 11.8745, 75.3704

DEFAULT_SYMPTOMS = ("sour liquid keeps coming up into my throat and my chest "
                    "burns after every heavy meal")


def explain_failure(exc: Exception) -> str:
    """Turn an Overpass failure into the thing to try next.

    Overpass is donated capacity, so "it is busy" is a normal answer rather than
    a bug: 429 means too many requests from this address, 504 means the gateway
    gave up before the query finished. Both are answered by waiting or asking
    for less, not by retrying harder.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return (f"no answer from Overpass: {exc}\n"
                f"  either the machine has no internet access, or the request "
                f"was cut off at {places.HTTP_TIMEOUT_S}s")
    hints = {
        400: "the query was rejected - the body below names the bad part of "
             "it, and --show-query prints the query itself",
        403: "blocked. Overpass blocks clients that ignore its usage policy - "
             "most often a missing or generic User-Agent",
        429: "too many requests from this machine. Wait a minute; if it keeps "
             "happening, this app needs caching before it needs retrying",
        504: "Overpass's gateway timed out - the server was busy. Try again, "
             "or ask for a smaller --radius",
    }
    hint = hints.get(response.status_code, "unexpected status")
    body = " ".join((response.text or "").split())[:400]
    return (f"HTTP {response.status_code} from Overpass: {hint}\n"
            f"  {body or '(empty body)'}")



def tag_says_specialist(tags: dict, specialist: str) -> bool:
    """True only when the OSM speciality tag means this specialist.

    Separate from places.matches_specialist, which also accepts a name match -
    the difference between the two counts is the honest measure of how much
    real speciality tagging exists in this town versus how much of the match is
    inferred from what somebody typed into the name field.
    """
    wanted = places.SPECIALISTS.get(specialist.strip().lower(),
                                    (frozenset(), None))[0]
    return bool(places.osm_specialities(tags) & wanted)


def print_coverage(raw: dict, found: list, specialist: str, radius: int) -> None:
    """What the map actually holds near this point - the honest inventory.

    Coverage is what decides whether this app is useful in Kannur, and it is
    invisible in a ranked table: three results out of three looks exactly like
    three out of three hundred. So count everything that came back, including
    the facilities that did not match the specialist and never reach the screen.
    """
    elements = raw.get("elements", [])
    kinds = Counter(
        (element.get("tags", {}).get("amenity")
         or element.get("tags", {}).get("healthcare")
         or "neither key") for element in elements)
    named = sum(1 for element in elements
                if element.get("tags", {}).get("name"))
    tagged = sum(1 for element in elements
                 if element.get("tags", {}).get("healthcare:speciality"))
    by_tag = sum(1 for element in elements
                 if tag_says_specialist(element.get("tags", {}), specialist))
    matched = sum(1 for place in found if place["speciality_match"])

    print(f"coverage: Overpass returned {len(elements)} mapped element(s) "
          f"within {radius} m")
    print("  by OSM tag  : " + ", ".join(f"{kind}={count}"
                                          for kind, count in kinds.most_common()))
    print(f"  named       : {named}/{len(elements)}"
          + ("" if named == len(elements)
             else "   (the rest are shown as 'Unnamed ...')"))
    print(f"  speciality  : {tagged} tagged healthcare:speciality, "
          f"{by_tag} of those mean '{specialist}'")
    print(f"  match total : {matched}/{len(found)} match '{specialist}' "
          f"by tag or name ({matched - by_tag} only by name)")


def print_raw(raw: dict, count: int) -> None:
    """The untouched response, for when the table looks wrong.

    The generator and timestamp lines matter as much as the elements: they say
    which Overpass server answered and how fresh the underlying OSM data was,
    which is the difference between "the data is not there" and "the data was
    not there when this snapshot was cut".
    """
    elements = raw.get("elements", [])
    print()
    print(f"server        : {raw.get('generator', 'unknown')}")
    print("OSM data as of: "
          f"{raw.get('osm3s', {}).get('timestamp_osm_base', 'unknown')}")
    if count <= 0 or not elements:
        return
    shown = elements[:count]
    print()
    print(f"raw response: first {len(shown)} of {len(elements)} element(s), "
          f"verbatim:")
    for element in shown:
        print(json.dumps(element, indent=2, ensure_ascii=False))
        print("-" * 60)


def print_table(shown: list) -> None:
    """The ranked results, with the OSM tag that got each one into the list.

    The kind column is not decoration: since amenity=hospital joined the query,
    a "hospital" row can be a 900-bed teaching hospital or a two-room nursing
    home, and the OSM tag is the only thing in the data that hints which.
    """
    print()
    print(f"{'#':>3}  {'match':<5} {'name':<40} {'kind':<10} {'km':>5} "
          f"{'score':>6}  contact")
    print("-" * 110)
    for index, place in enumerate(shown, 1):
        name = place["name"]
        if len(name) > 40:
            name = name[:37] + "..."
        contact = place["phone"] or place["speciality"] or ""
        print(f"{index:>3}  {'yes' if place['speciality_match'] else '-':<5} "
              f"{name:<40} {place['kind']:<10} {place['distance_km']:>5} "
              f"{place['score']:>6}  {contact}")
    print()
    print("match = OSM's own tagging (or its name) says it is the right kind of")
    print("specialist; '-' means it is nearby but nothing in the data says so.")
    print("kind = the OSM tag that put it in range (amenity=doctors, clinic or")
    print("hospital, or healthcare=doctor/clinic) - it is not a statement of size.")
    print("score is distance + speciality + how complete the listing is, because")
    print("OpenStreetMap has no star ratings - see app/ranking.py.")


def fetch_with_one_retry(lat: float, lng: float, radius: int, wait: int) -> dict:
    """Ask Overpass once; if it answers "busy", wait, then ask exactly once more.

    Overpass is donated capacity and it does go down under load - a real run for
    this project got an HTTP 504 mid-demo. 504 and 429 both mean "not now", and
    the correct response to a free shared service is to wait, not to retry in a
    loop. One retry turns "the demo failed" into "the demo took 20s longer".
    `wait` of 0 disables the retry entirely.
    """
    for attempt in (1, 2):
        try:
            return places.fetch_raw(lat, lng, radius)
        except requests.HTTPError as exc:
            status = getattr(exc.response, "status_code", None)
            if attempt == 2 or wait <= 0 or status not in (429, 504):
                raise
            print(f"Overpass is busy (HTTP {status}). Waiting {wait}s and "
                  f"asking once more.")
            print("  (that is the honest move on a shared service: wait, do "
                  "not hammer it)")
            time.sleep(wait)


def report(specialist: str, lat: float, lng: float, args) -> int:
    """Make the one request, then report coverage, raw data and the table."""
    if args.show_query:
        print("Overpass QL this run sends:")
        print(places.build_query(lat, lng, args.radius))
        print()

    try:
        raw = fetch_with_one_retry(lat, lng, args.radius, args.retry_wait)
    except requests.HTTPError as exc:
        print(f"Overpass refused the call.\n  {explain_failure(exc)}")
        return 1
    except requests.RequestException as exc:
        print(f"Overpass could not be reached.\n  {explain_failure(exc)}")
        return 1
    except (RuntimeError, ValueError) as exc:
        # ValueError: impossible coordinates or radius.
        # RuntimeError: HTTP 200 carrying a "remark" instead of usable data.
        print(f"Nothing usable came back: {exc}")
        return 1

    # parse_elements(fetch_raw(...)) is exactly what app.places.find_doctors
    # does internally. Splitting the two here means the raw response and the
    # parsed table on screen both come from ONE request, not two.
    found = places.parse_elements(raw, specialist)
    shown = rank_places(found, lat, lng, top_n=args.top)

    print(f"searching for : {specialist}")
    print(f"location      : {lat}, {lng}   (hard radius {args.radius} m)")
    print()
    print_coverage(raw, found, specialist, args.radius)
    print_raw(raw, args.raw)

    if not found:
        print()
        print(f"Nothing to show: OpenStreetMap has no doctor or clinic mapped "
              f"within {args.radius} m of")
        print(f"{lat}, {lng}. That is a coverage fact about this town, not an "
              f"error in the query -")
        print("raise --radius to find where the nearest mapped one starts.")
        return 0

    print_table(shown)

    # Note the difference from the Google version this replaced: Overpass
    # `around:` is a hard limit, so every result is inside the radius by
    # construction. There is no locationBias caveat to warn about any more.
    if not any(place["speciality_match"] for place in shown):
        print()
        print(f"NOTE: none of the {len(found)} mapped facilities in range is "
              f"tagged or named as a")
        print(f"{specialist}. Everything above is a nearby clinic or GP, "
              f"listed because")
        print("nearby-and-unverified still beats an empty page - but it is not "
              "what the classifier asked for.")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--symptoms", default=DEFAULT_SYMPTOMS,
                        help="plain-language symptoms (the classifier's input)")
    parser.add_argument("--specialist", default=None,
                        help="skip the classifier and look for this specialist")
    parser.add_argument("--lat", type=float, default=KANNUR_LAT)
    parser.add_argument("--lng", type=float, default=KANNUR_LNG)
    parser.add_argument("--radius", type=int, default=5000,
                        help="search radius in metres, up to "
                             f"{places.MAX_RADIUS_M}")
    parser.add_argument("--top", type=int, default=10,
                        help="how many ranked results to print")
    parser.add_argument("--raw", type=int, default=0,
                        help="print this many raw Overpass elements, tags and "
                             "all")
    parser.add_argument("--retry-wait", type=int, default=20, metavar="SECONDS",
                        help="when Overpass answers 429/504 (busy), wait this "
                             "long and ask once more; 0 disables the retry")
    parser.add_argument("--show-query", action="store_true",
                        help="print the Overpass QL being sent")
    args = parser.parse_args(argv)

    print("CureConnect - live Overpass / OpenStreetMap smoke test")
    print("=" * 78)
    print("no key, no account, no card: this run cannot cost anything")

    if args.specialist:
        specialist = args.specialist
        print(f"specialist: {specialist}  (given on the command line, so the "
              f"classifier was skipped)")
    else:
        print(f"symptoms: {args.symptoms!r}")
        if is_emergency(args.symptoms):
            # app/main.py returns here and never searches at all.
            print(f"safety check: EMERGENCY -> {EMERGENCY_MESSAGE}")
            print("The API would not search for doctors for this input.")
            return 3
        print("safety check: nothing red-flagged")

        prediction = predict(args.symptoms)
        specialist = prediction["specialist"]
        top3 = ", ".join(f"{entry['condition']} {entry['confidence']:.3f}"
                         for entry in prediction["top3"])
        print(f"classifier: {prediction['condition']} "
              f"(low_confidence={prediction['low_confidence']}, "
              f"margin {prediction['margin']:.3f})")
        print(f"            top-3: {top3}")
        print(f"specialist: {specialist}  (from app/mapping.py)")
        if prediction["low_confidence"]:
            print("            (the app would answer 'we are not sure' and "
                  "show those top-3 as possibilities)")
    print()

    status = report(specialist, args.lat, args.lng, args)

    print()
    print("Data from OpenStreetMap, (c) OpenStreetMap contributors, ODbL. Any "
          "screen showing these")
    print("results must credit OpenStreetMap - see docs/places_osm.md.")
    if status == 0:
        print("Free and keyless: no account, no quota, nothing billed.")
    print("Run uvicorn app.main:app --reload and open frontend/index.html to "
          "see the same answer in the real UI.")
    return status


if __name__ == "__main__":
    sys.exit(main())
