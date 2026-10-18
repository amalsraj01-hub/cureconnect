# Doctor search: OpenStreetMap + Overpass (free, no key, no card)

Stage 5's doctor search used to call **Google Places API (New) Text Search**.
It now uses **OpenStreetMap through the Overpass API** instead. This file
replaces the old `docs/places_api_setup.md`, which was a walkthrough for the
Google Cloud console (API keys, billing, quota caps) and no longer applies.

## Why it changed

The Google version worked, but every search cost money the moment it ran, and
the reason was not the search itself: `app/ranking.py` scores on `rating` and
`userRatingCount`, and asking for a top-tier field makes the whole request
**Text Search (Enterprise)** rather than a cheaper SKU. That is a permanent
bill for a student project, plus a key to create, restrict, cap and leak.

| | Google Places (New) | OpenStreetMap + Overpass |
|---|---|---|
| key / account | required | none |
| cost per search | billed (Text Search Enterprise) | free |
| ratings | `rating` + `userRatingCount` | **none exist** - see below |
| radius behaviour | `locationBias` - a *preference*, results can fall outside it | `around:` - a **hard limit** |
| extra fields | extra cost tier | `phone`, `website`, `opening_hours` come free |
| bulk/coverage | commercial index | volunteer-mapped, thin outside cities |
| obligation | Google's terms | **ODbL: you must credit OpenStreetMap** |

## The exact query

`app/places.py` builds this and posts it to
`https://overpass-api.de/api/interpreter`. Shown exactly as a real run printed
it (`--show-query`):

```
[out:json][timeout:25];
(
  nwr["amenity"="doctors"](around:5000,11.8745,75.3704);
  nwr["amenity"="clinic"](around:5000,11.8745,75.3704);
  nwr["amenity"="hospital"](around:5000,11.8745,75.3704);
  nwr["healthcare"="doctor"](around:5000,11.8745,75.3704);
  nwr["healthcare"="clinic"](around:5000,11.8745,75.3704);
);
out center;
```

Five things worth knowing about it:

- **`nwr`** covers node, way *and* relation, because a clinic may be mapped as
  any of the three. A note in the task said `amenity=doctor`; there is no such
  value in the OSM schema - it is **`amenity=doctors`**, plural.
- **`out center`** is what makes ways and relations usable at all. Only a node
  carries `lat`/`lon`; without this, a clinic drawn as a building outline
  arrives with no coordinates and cannot be scored by distance.
- **Five filters, not one**, because a facility in OSM very often carries only
  one of these tags and nothing else. Part of the order in the query follows
  `DOCTOR_FILTERS` - `doctors`, `clinic`, `hospital`, then the `healthcare=*`
  pair - which is also the order the results arrive in before ranking.
- **`amenity=hospital` is the least obvious filter.** In a smaller town like
  Kannur the specialist usually practices *inside* the district or private
  hospital rather than at a standalone clinic, so leaving hospitals out removed
  the place a gastroenterologist is most likely to be. The cost is that general
  hospitals come back too, and they are shown as what they are: nearby, with no
  speciality claimed. `kind` reports `hospital` so a caller can tell.
- **`[timeout:25]`** is a declaration, not just a limit: the Overpass commons
  page states that small declared requests are admitted ahead of large ones
  when a server is under load. The client-side HTTP timeout is **35 s**
  (`HTTP_TIMEOUT_S` = the 25 s server budget + 10 s), so a slow answer is not
  thrown away by us first. When the server is refusing outright (HTTP 504) or
  outlasts even that, no timeout setting helps: both the smoke script (20 s
  wait) and `app/places.py` (3 s wait) ask **once more**, then give up - see
  the failure table. The app's retry was added on 2026-10-06, after two real
  502s in a live Swagger test turned out to be one transient Overpass 504.

## What "a specialist" means in OSM tags

There is no speciality field that must be filled in. The layer tries two things
per facility, in this order:

1. **`healthcare:speciality`** - free text, e.g. `gastroenterology`, or a
   semicolon list like `general;diabetes`. Normalised to lowercase, spaces to
   underscores, so tags can be compared.
2. **The facility's name** - a regex per specialist, e.g. `gastro|hepatolog|
   digestive|liver` for a Gastroenterologist. This is not decoration: in a town
   like Kannur a gastroenterology clinic is very often tagged `amenity=clinic`
   and nothing else, which makes its *name* the only evidence there is.

`SPECIALISTS` in `app/places.py` maps the twelve specialist names that
`app/mapping.py` produces onto those OSM values and regexes. `speciality_match`
is set per place, so a caller can always tell a verified match from a nearby
GP that merely happened to be closest.

## Real Kannur results (2026-10-01)

Four live runs from Kannur town centre (11.8745, 75.3704), answered by
`Overpass API 0.7.62.11`, OSM data as of 06:47Z, 06:48Z, 06:50Z and 06:55Z that
morning. These are the untouched numbers the smoke script printed. They are
**not** comparable with earlier revisions of this page: `amenity=hospital` has
since joined the query, and in Kannur that one tag is most of the growth - 38 of
the 54 elements inside 5 km, 121 of the 156 inside 15 km. Nothing was added to
OSM for this; the query got wider, not the map.

| radius | mapped elements | hospital / clinic / doctors | with a name | with any `healthcare:speciality` | matched "Gastroenterologist" | matched "General Physician" |
|---|---|---|---|---|---|---|
| 5 km | 54 | 38 / 13 / 3 | 47 | 1 | **0** | (not run) |
| 15 km | 156 | 121 / 28 / 7 | 138 | 8 | (not run) | **3** |

The 5 km search for a Gastroenterologist, ranked by `app/ranking.py` - verbatim,
with the `kind` column the script now prints:

```
  #  match name                                     kind          km  score  contact
--------------------------------------------------------------------------------------------------------------
  1  -     Ashirvad Hospital                        hospital     0.3  0.387
  2  -     Fathima Hospital                         hospital     0.4   0.35
  3  -     Raslock Hospital                         hospital     0.4  0.349
  4  -     Railway Station Health Unit              clinic       0.5  0.333
  5  -     Madhavrao Scindia Hospital               hospital     0.8  0.321
  6  -     Kurumathur Arya Vaidya Sala and Nursi... clinic       0.6  0.318
  7  -     Mother and Child Hospital                hospital     0.7  0.296
  8  -     JJS Hospital                             hospital     0.8  0.275
  9  -     AKG Hospital                             hospital     1.2  0.275  +91-4972762500
 10  -     Kasyapa Ayurveda Health Care             clinic       0.8  0.272
 11  -     Ncare IVF Hospital                       hospital     0.9  0.269
 12  -     Vasan Eye Care Hospital, Kannur          hospital     0.9  0.258
 13  -     Kripa Nursing Home                       clinic       0.9  0.257
 14  -     Priya ENT Care                           clinic       1.0  0.253
 15  -     Unnamed clinic (no name in OpenStreet... clinic       1.0  0.253
```

Read honestly, that says:

- **Doctor's offices are mapped in Kannur; specialities are not.** 54 facilities
  in 5 km now, but only 1 of the 54 carries a `healthcare:speciality` tag at all,
  and it is not gastroenterology.
- **There is no gastroenterologist in Kannur's OSM data at either radius.** Not
  one of the 54 within 5 km, nor any of the 156 within 15 km, is tagged or named
  as one. The nearest thing OSM does admit to is a GP: three facilities carry
  `healthcare:speciality=general` - the *unnamed* clinic 4.8 km out, a community
  health centre 8.3 km out and a primary health centre 14.7 km out.
- **Going wider tripled the count and changed nothing at the top.** 54 -> 156
  elements, and the same 15 facilities in the same order head both lists, because
  the order is decided by distance and the nearest named facility in Kannur is
  `Ashirvad Hospital` at 300 m from the town centre.
- **`kind` is not a judgement about size.** 38 rows say `hospital`; that covers a
  district hospital and a two-room nursing home alike. `amenity=hospital` is
  applied generously in Kerala, which is why the tag is printed next to the name
  instead of the results being summarised as "hospitals near you".
- So the truthful answer for a GERD-type question here is "nearest doctors and
  clinics, none of which is confirmed to be the specialist you need" - which is
  what `speciality_match` and the smoke script's NOTE say, instead of dressing
  a GP up as a specialist.
- The results are checkable, not just plausible: every place carries `osm_url`,
  so `Priya ENT Care` or `G's psychology clinic` can be opened on
  openstreetmap.org and judged by eye.
- OSM's medical tagging is wider than "doctor": a psychology clinic, an ayurveda
  clinic and a nursing home all appear under `amenity=clinic`. The match column
  is what stops them being presented as the specialist that was asked for.

## Ratings: what was lost, and what replaces them

OpenStreetMap has no star ratings and no review counts, anywhere. That is not a
gap this layer can fill, so `app/ranking.py` now holds **two formulas**:

- **unrated (what OSM gives us):** distance 50%, `speciality_match` 35%, how
  complete the listing is (phone + website + opening_hours) 15%
- **rated:** the original Bayesian rating 55% / distance 25% / review volume
  20%, unchanged, for whenever a source that does have ratings is used again

Two consequences, both visible in the real data:

- **"Highly rated near you" had to go.** With no ratings that heading was a
  claim the data cannot support, so `frontend/index.html` now reads "Doctors and
  clinics near you" and prints a rating line only when a rating exists
  ("Rating null" is what it would have shown before).
- **The 35% speciality weight reorders results, on purpose.** In the 15 km run
  for a General Physician, the unnamed `speciality=general` clinic 4.8 km away
  came *first* (0.436), ahead of `Ashirvad Hospital` 300 m away (0.387) - and the
  two GP-tagged rural health centres at 8.3 km and 14.7 km also outranked it.
  Distance is 50% of the score and completeness 15%, but "does this address the
  question that was asked" is worth beating a nearer door for. That is a product
  decision, not a fact. Prefer "nearest door
  wins"? Lower that weight in `score_place`. Prefer "never show a non-match"?
  Filter on `speciality_match` before ranking. Both are one-line changes, and
  you should make them rather than inherit my default.

One trap worth naming: the two formulas live on different scales, so putting
google-shaped and OSM-shaped places in one list would compare numbers that do
not mean the same thing. Use one source per search.

## Being a good guest on a donated server

Overpass is not a company's API, it is donated capacity. The commons page says
around 30,000 daily users share two servers behind `overpass-api.de`, each good
for about a million requests a day, and it names four kinds of behaviour that
cause trouble. All four apply to this project:

1. sending the same request tens of thousands of times a day from one address,
2. asking for elements one by one, millions of times,
3. stitching bounding boxes together to scrape the world,
4. **building an app for non-mappers that treats the public instances as its
   backend** - for that, the page is blunt: only your own instance sustainably
   serves the mission.

The stated safety margins are roughly **10,000 requests/day and under 1 GB/day**.
A student demo is nowhere near that. A deployed CureConnect would be, and would
need its own instance or a cache first. What this code does today:

- sends a real `User-Agent` (`CureConnect/0.2 ...`) - put a contact address in
  before deploying, because anonymous clients get throttled,
- declares `[timeout:25]` so it is admitted as a small request,
- **does not poll, or loop in the background**,
- retries **exactly once**, after a 3 s wait, and only for 429/5xx, a timeout
  or a dropped connection (`MAX_ATTEMPTS`, `RETRY_STATUSES` in
  `app/places.py`). Until 2026-10-06 the app deliberately did not retry at
  all - "a web request must not sleep" - but a live test then produced two
  back-to-back 502s from one transient Overpass 504, which is exactly what a
  single bounded retry is for. A loop would still be abuse.
  `scripts/places_smoke.py` keeps its own 20 s one-retry (`--retry-wait 0`
  switches that off) for manual runs.

The two failing status codes mean specific things: **429** is the rate limit
(too many requests from this address), and **504** is the resource admission
check refusing the request because it declared more run time or memory than was
free at that moment - not a network fault. A real run for this project got a 504
on the first 15 km attempt, which is exactly that: the right answer is to wait
and ask once more, or to ask for less.

**The obvious next upgrade is a cache**, keyed by rounded lat/lng + radius.
Doctors do not move; the answer changes only when somebody edits OSM; and every
hit removes load from a donated server. Not built yet on purpose - a cache
changes what "fresh" means and deserves its own decision.

## Licence: ODbL, and what it obliges you to do

OpenStreetMap data is licensed **ODbL**. The OSMF attribution guidelines state
plainly that if you use OSM data in something you distribute, *you must
attribute OpenStreetMap*, and the credit has to be visible to anyone who sees
the results, without them having to interact with them first. Any deployed or
public use of this app is covered, so:

- `frontend/index.html` prints "Doctor data from OpenStreetMap, © OpenStreetMap
  contributors (ODbL)" with a link to `openstreetmap.org/copyright`, next to the
  results. That is the licence condition, not decoration - do not drop it when
  restyling the page.
- `scripts/places_smoke.py` prints the credit with its output, because that
  output is a display of OSM-derived data too.
- Every parsed place carries `osm_url`, which is both attribution-friendly and
  the way to check any single result by hand.
- Internal use (running the tests, reading the JSON yourself) does not trigger
  the requirement. Showing the results to other people does.

## When it fails, and who says what

| what happened | raised as | what the user gets |
|---|---|---|
| lat/lng/radius impossible | `ValueError` | 502, "radius must be between 1 and 50000 metres, got 0" |
| key-less abuse blocked (403) or a malformed query (400) | `requests.HTTPError` | 502 with Overpass's own message |
| rate-limited, or no free slot (429 / 504) | `requests.HTTPError` | retried once in the app (3 s); 502 with the reason only if that fails too |
| HTTP 200 but unusable data (`"remark"`: timed out) | `RuntimeError` | 502 - **never** a cheerful empty list |
| unreachable, or the 35 s client timeout (after the one retry) | `requests.RequestException` | 502 with the reason |
| one element with no coordinates | nothing - dropped | it simply is not in the list |

`app/main.py` catches everything around `find_doctors` and turns it into a 502
with the reason attached, so a failure is a visible error, never a silent empty
result that reads as "you live nowhere near a doctor".

## What this layer still does not do

- **No ratings and no reviews.** Nothing here can rank quality, only distance,
  speciality and how complete a listing is.
- **Doctors, clinics and hospitals** (`amenity=doctors|clinic|hospital`,
  `healthcare=doctor|clinic`). No pharmacies, dentists or labs. Hospitals are in
  the query on purpose: in a town like Kannur a specialist usually practices
  inside the district or private hospital rather than at a standalone clinic, so
  excluding hospitals excluded the place a gastroenterologist is most likely to
  be. The honest limit of the claim is that a hospital is one big building with
  many departments and OSM does not record who is on duty there today, so the
  most it can support is "nearest place that may have a gastroenterologist".
  A facility carrying only `healthcare=hospital` and not `amenity=hospital`
  would still be missed; that combination is unusual, but it is one more line in
  `DOCTOR_FILTERS` if the data ever shows it.
- **Silence is not evidence.** The single most important limitation: no clinic
  found in OSM does *not* mean no clinic exists. It means nobody mapped one.
  The app must never let an empty result sound like a fact about the world.
- **Nothing is verified.** A facility may have closed, a phone number may be
  dead, the data may be years old. The smoke script prints the OSM data
  timestamp for exactly this reason.
- **Most contact details are blank.** In the 5 km run 7 of 54 facilities had no
  name and every single one had an empty `addr:*` address: Indian addresses are
  rarely entered tag by tag in OSM. `phone` and `website` are bonuses when they
  exist.
- **`opening_hours` is printed raw.** OSM's syntax is rich and is not parsed.
- **English only.** The name regexes are English, so a Malayalam-named clinic is
  not matched by name; nothing is translated.
- **No caching, no in-app rate limiting.** See the commons section above.
- **Speciality values are compared literally.** `internal_medicine` counts as a
  GP; a facility tagged just `internal` does not. That is deliberate - guessing
  that "internal" means Internal Medicine is how a dermatologist ends up being
  recommended for reflux. If the real data turns up values like that, add them
  to `SPECIALISTS` *after seeing them*, with the same evidence-first care as the
  rest of this repo.

## How to check all of this yourself

```bash
pytest -q                                     # offline; nothing in tests/ touches the network
python scripts/places_smoke.py --specialist Gastroenterologist --raw 3 --show-query
python scripts/places_smoke.py --radius 15000 # the full chain: safety, classifier, places, ranking
```

Read the coverage block for whether the data exists at all, the match column for
whether any of it is the right kind of doctor, and `osm_url` for anything
surprising. Exit codes: 0 reported, 1 Overpass refused or was unreachable,
3 the safety check stopped the run.

## Sources (all read 2026-10-01)

- Overpass API commons - quotas, the four abusive patterns, 429 vs 504:
  <https://dev.overpass-api.de/overpass-doc/en/preface/commons.html>
- Overpass API wiki - what it is, public instances:
  <https://wiki.openstreetmap.org/wiki/Overpass_API>
- Overpass QL reference - `nwr`, `around:`, `out center`:
  <https://wiki.openstreetmap.org/wiki/Overpass_API/OverpassQL>
- OSMF attribution guidelines - "you must attribute OpenStreetMap":
  <https://osmfoundation.org/wiki/Licence/Attribution_Guidelines>
- The URL the credit has to link to: <https://www.openstreetmap.org/copyright>
- Tag documentation for the keys this layer reads:
  <https://wiki.openstreetmap.org/wiki/Tag:amenity%3Ddoctors>,
  <https://wiki.openstreetmap.org/wiki/Tag:healthcare%3Ddoctor>,
  <https://wiki.openstreetmap.org/wiki/Key:healthcare:speciality>



