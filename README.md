# CureConnect

Symptom-to-specialist and local doctor recommendation app.
**Not a medical diagnosis tool.** It only suggests which type of doctor to consult.

## Pipeline
1. Safety check (red-flag symptoms -> emergency message)
2. Symptom text -> condition (TF-IDF + Logistic Regression)
3. Condition -> specialist (hand-written mapping table)
4. OpenStreetMap search for nearby doctors and clinics (Overpass API, no key)
5. Ranking (distance + speciality match + listing completeness; OSM has
   no ratings, so the old Bayesian-rating formula is only used when a source
   that does have ratings is plugged back in)

## Setup
```bash
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux
pip install -r requirements.txt
```

### No API key, no billing account, no card

Doctor search (step 4) runs on **OpenStreetMap via the Overpass API**: free,
keyless and unmetered. There is nothing to sign up for and nothing that can be
billed, so `.env.example` documents no secrets - but `python-dotenv` is not
dead weight: `app/ratelimit.py` loads it so optional settings like
`RATE_LIMIT_PER_MINUTE` can be overridden in `.env`.

What that trades away, honestly: OSM has **no star ratings and no review
counts**, and its coverage of small towns is volunteer work in progress. A real
search at Kannur town centre on 2026-10-01 found 54 mapped doctors, clinics and
hospitals within 5 km and 156 within 15 km, of which **zero** were a
gastroenterologist and only 8 carried any speciality tag at all. Details, the
query, the licence obligations and the live numbers:
[`docs/places_osm.md`](docs/places_osm.md).

**Known limitation - the one that decides whether this works in Kannur.** OSM
maps the buildings, not the specialisms. `amenity=doctors`, `amenity=clinic` and
`amenity=hospital` are present and usually named, so "is there a doctor near me"
gets a real answer. `healthcare:speciality` is almost never filled in, so "is
there a gastroenterologist near me" gets the truthful answer "not according to
OpenStreetMap", followed by nearby GPs that make no such claim. An empty
specialised result is **not** evidence that no such doctor exists: it means
nobody has mapped one yet, and the UI must never present it as a fact about the
town.

**Next up, once ranking, the backend and the frontend work end to end: a small
hand-checked seed list of Kannur and Kozhikode specialists** (name, speciality,
phone, source URL), kept *beside* the OpenStreetMap layer and never merged into
one ranked list with it - the two sources score on different scales, so mixing
them would compare numbers that do not mean the same thing (see
`docs/places_osm.md`). Parked deliberately, not forgotten.

Results come from OpenStreetMap, so anything user-facing has to credit it
(ODbL) - the frontend already prints the required line.

## Run order (build layer by layer)
1. `pytest`                                 -> safety, ranking, places + classifier tests should pass
2. Download the Kaggle "Disease Symptom Prediction" dataset,
   save it as `data/dataset.csv`
3. `python -m app.train`                    -> creates app/model.joblib
4. `uvicorn app.main:app --reload`          -> API at http://127.0.0.1:8000/docs
                                                (POST /recommend: 10 requests/min/IP)
5. Open http://127.0.0.1:8000/ in your browser: the API serves the page now,
   so there is no separate frontend to start (coordinates default to Kannur
   11.8745, 75.3704; the Leaflet map needs internet). Opening the file with
   file:// no longer works - the page calls /recommend on its own origin.

## Deploy on Render (Stage 9)

One process serves everything: the page at `/`, the API at `/recommend`,
docs at `/docs`. The exact settings live in `render.yaml` at the repository
root (build `pip install -r requirements.txt`, start
`uvicorn app.main:app --host 0.0.0.0 --port $PORT`, health check `/health`,
Python pinned to the version the model was built with).

1. Push the project to a GitHub repository. It must include
   `app/model.joblib`: a clean checkout cannot rebuild it without the Kaggle
   `data/dataset.csv`, and a missing model means every search answers 500.
   The file is deliberately no longer gitignored, for exactly that reason.
2. Render dashboard -> New -> Blueprint -> pick the repository; Render reads
   `render.yaml` and builds the service. (Or New -> Web Service and type the
   same build and start commands by hand.)
3. Open the `onrender.com` URL it hands back: `/` is the app.

What the free tier actually changes, plainly:

- **Cold start ~30 s.** The instance sleeps after about 15 minutes without
  visitors; the first request after that wakes it. Wait and reload once
  before concluding it is down - `GET /health` is the cheap check.
- **The rate limit is per process, in memory** (Known limitations below):
  every deploy or sleep hands everyone a fresh 10/min window.
- **The client IP is `X-Forwarded-For`** behind Render's proxy; the limiter
  already keys on it.
- **Overpass sees Render's IP, not yours.** The one polite retry in
  `app/places.py` covers the slow windows you would otherwise meet as a 502.
- **No secrets to configure.** There are no API keys anywhere in this app;
  `RATE_LIMIT_PER_MINUTE` is the only optional environment variable.
- The ODbL credit stays where it is: on the public page, next to the results,
  because the licence requires it there (see `docs/places_osm.md`).

## Folder guide
- app/safety.py      red-flag emergency checker
- app/mapping.py     condition -> specialist table (extend this!)
- app/train.py       trains and saves the classifier
- app/classifier.py  loads model, returns top-3 with confidence
- app/places.py      OpenStreetMap / Overpass queries (no key, no cost)
- app/ratelimit.py   per-IP sliding window on /recommend (10/min default)
- frontend/index.html the page: symptoms form, coordinate boxes (Kannur
                      default), top-3 alternatives, Leaflet map, disclaimers
- app/ranking.py     scoring formula
- app/main.py        FastAPI endpoints
- frontend/          simple HTML page
- scripts/           evaluation + the frozen holdout benchmark
  - scripts/evaluate.py    scores the model on data/test_sentences.csv
  - scripts/holdout20.py   the frozen 20 sentences (do not edit, see below)
  - scripts/places_smoke.py  one real Overpass call near Kannur (free, no key;
                             `--raw 5` prints the raw response)
- tests/             pytest tests
- notebooks/         experiments (Jupyter)
- data/              datasets (not committed)

## Known limitations
- **"burning micturition" belongs to two conditions at once.** The training
  data gives that phrase to Drug Reaction and Urinary tract infection in equal
  numbers (108 rows each), so a UTI sentence that mentions burning can be
  answered as Drug Reaction. Left alone on purpose until it is measured with
  its own script instead of a guess - see the caveats in
  `docs/eval_stage6.txt`.
- **Top-1 accuracy on realistic free text is 49.6%** across 41 conditions, and
  10 conditions are never the model's first guess even when they are the truth
  (GERD was the eleventh until the 2026-10-01 normaliser fix below; the list is
  in `docs/eval_stage6.txt`). What the app actually shows is the specialist,
  where the same run scores 74.4%. **Treat both numbers as optimistic:** they come
  from `data/test_sentences.csv`, which was read and quoted while the pipeline
  was being fixed. On the frozen 20 sentences in `scripts/holdout20.py`, which
  were written after that work and never used during it, top-1 is 40.0% and the
  specialist figure is 45.0%.
- **The `/recommend` rate limit lives in memory, per process.** Each client gets
  10 requests per minute by default (`RATE_LIMIT_PER_MINUTE` overrides it),
  counted in `app/ratelimit.py`. Several workers would multiply the effective
  limit and a restart clears it - revisit before scaling.

## Frozen holdout benchmark (do not edit)
`scripts/holdout20.py` holds 20 sentences written *after* the model, the
normaliser and the confidence gate were finished. They are the honest
counterweight to the 49.6% above: wording no part of the build ever saw.

They are frozen on purpose. The moment one is reworded, or a phrase in it is
"fixed" to raise a score, the set becomes just another one the code was tuned
against and the only honest number we have is gone.

**Never edit, reword, reorder, add to or remove from the `HOLDOUT` list in that
file.** `tests/test_holdout_frozen.py` pins a fingerprint of the 20 sentences
and fails if any one of them changes - including a typo fix. If a number gets
worse, fix `app/normalize.py` or the confidence gate, never the sentence.

Run it from the project root (the folder holding `app/` and `data/`):

```bash
python scripts/holdout20.py
```

As of 2026-10-01 (same 20 sentences; the fingerprint below is unchanged):

- Top-1 40.0% (8/20), Top-3 60.0% (12/20)
- Fallback "Unclear" 85.0% (17/20), Specialist-level top-1 45.0% (9/20)
- Shown *and* correct 15.0% (3/20) - what a real user actually gets right

These numbers moved exactly once, on 2026-10-01, and only because a bug in
`app/normalize.py` was fixed - no sentence was touched. The reflux keys used to
borrow the word "indigestion", which the dataset gives to Migraine and Peptic
ulcer but never to GERD, so two sentences passed the gate with a confident wrong
answer (GERD as Migraine 0.156, Diabetes as Urinary tract infection 0.181), each
carrying a symptom the patient never described. Both are now below the gate.
Read the higher fallback rate as the point rather than the cost: the app now says
"Unclear" on two sentences it used to be confidently wrong about. See
`docs/eval_stage6.txt` for the before/after detail.

The set deliberately over-samples the 9 mutually confusable conditions and the
urination-related ones, so read it as a hard-case lower bound, not an average of
real users. Replacing it is allowed, but only deliberately: add a new file,
note the change in `docs/`, and treat every earlier number as void.

## Later upgrades
Redis caching, review sentiment, Docker, GitHub Actions CI, MLflow, RAG, Malayalam.
