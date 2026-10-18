"""FastAPI backend.  Run:  uvicorn app.main:app --reload"""
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.safety import is_emergency, EMERGENCY_MESSAGE
from app.classifier import predict
from app.places import find_doctors
from app.ranking import rank_places
from app.ratelimit import RateLimiter

app = FastAPI(title="CureConnect", version="0.1.0")

# Open CORS for local development. Restrict to your frontend domain in production.
# expose_headers: browsers hide non-standard response headers from JavaScript
# unless the server names them, so without this line the page cannot read
# Retry-After on a 429 and cannot say how long to wait.
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Retry-After"])

# One window per process; see app/ratelimit.py for the multi-worker note.
limiter = RateLimiter()

DISCLAIMER = ("CureConnect does not diagnose. It only suggests a type of doctor "
              "to consult. Please see a qualified medical professional.")


class Query(BaseModel):
    symptoms: str = Field(min_length=3, max_length=1000)
    lat: float
    lng: float


def rate_limit(request: Request):
    """Per-client limit on /recommend: every call runs the classifier and
    may trigger an Overpass query, so it is the only endpoint worth gating.
    Uses the forwarded IP when behind a proxy (Render), else the socket IP."""
    forwarded = request.headers.get("x-forwarded-for")
    client = forwarded.split(",")[0].strip() if forwarded else (
        request.client.host if request.client else "unknown")
    allowed, retry_after = limiter.check(client)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please wait and try again.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/recommend", dependencies=[Depends(rate_limit)])
def recommend(q: Query):
    if is_emergency(q.symptoms):
        return {"emergency": True, "message": EMERGENCY_MESSAGE, "disclaimer": DISCLAIMER}

    try:
        prediction = predict(q.symptoms)
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        places = find_doctors(prediction["specialist"], q.lat, q.lng)
    except ValueError as e:
        # Our own input validation, not Overpass: asking again with the same
        # numbers would fail identically, so no "try again" advice.
        raise HTTPException(status_code=502, detail=f"Doctor search failed: {e}")
    except Exception as e:
        # One transient failure is already retried inside places.fetch_raw;
        # what reaches here is a persistent outage or a genuine error in the
        # places layer. Say that in words a user can act on, not just 502.
        raise HTTPException(
            status_code=502,
            detail=(f"Doctor search failed: {e}. OpenStreetMap's Overpass "
                    "service did not answer - this is usually temporary, "
                    "please try again in about 30 seconds."),
        )

    return {
        "emergency": False,
        "prediction": prediction,
        "doctors": rank_places(places, q.lat, q.lng),
        "disclaimer": DISCLAIMER,
    }


# Stage 9: the frontend is served by this same app, so one process answers the
# page and the API and the browser sends no cross-origin request at all. The
# mount goes last - /health, /recommend, /docs and /openapi.json are already
# registered above and a route only loses to a Mount that comes after it.
# html=True is what makes a request for "/" answer with index.html.
app.mount("/", StaticFiles(directory=Path(__file__).resolve().parent.parent / "frontend",
                           html=True), name="frontend")
