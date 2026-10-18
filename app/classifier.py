"""Symptom text -> condition + specialist, with confidence fallback."""
import os
import joblib
from app.mapping import to_specialist, DEFAULT_SPECIALIST
from app.normalize import normalize

MODEL_PATH = os.path.join(os.path.dirname(__file__), "model.joblib")

# Below this top-1 probability the app answers "Unclear" instead of guessing.
# Single source of truth: scripts/evaluate.py imports this same number, so the
# API and the evaluation can never disagree about the fallback rate.
#
# 0.15, not 0.30. The 0.30 was calibrated before app.normalize existed, when
# the median top-1 confidence on realistic sentences was 0.08; with the
# normaliser in place the median is 0.19, so 0.30 hid 69% of users behind
# "Unclear" while hiding answers that were mostly right. See docs/eval_stage5.txt.
CONFIDENCE_THRESHOLD = 0.15

# A second, independent reason to say "Unclear": a high score means little when
# the runner-up is almost as high. Hepatitis B/C/D/E score within a hair of each
# other, so 0.31 vs 0.30 is a coin flip wearing a confident face. This is a VETO
# used alongside the threshold, never a replacement for it: anything the
# threshold hides stays hidden, the margin can only add to it.
MARGIN_THRESHOLD = 0.05

_model = None


def _load():
    global _model
    if _model is None:
        if not os.path.exists(MODEL_PATH):
            raise RuntimeError("Model not found. Run: python -m app.train")
        _model = joblib.load(MODEL_PATH)
    return _model


def ranked_predictions(texts):
    """Return [(condition, probability), ...] best-first for each text.

    All text cleaning lives in app.normalize, which app.train also uses, so the
    API and scripts/evaluate.py can never drift apart about what the model is
    actually being asked.
    """
    model = _load()
    cleaned = [normalize(text) for text in texts]
    probabilities = model.predict_proba(cleaned)
    classes = model.classes_
    return [
        sorted(zip(classes, row), key=lambda pair: -pair[1])
        for row in probabilities
    ]


def top_two_margin(ranked) -> float:
    """How far the best condition is ahead of the runner-up.

    A ranking with a single class has no runner-up; there the whole
    probability counts as the margin rather than raising an error.
    """
    best = float(ranked[0][1])
    runner_up = float(ranked[1][1]) if len(ranked) > 1 else 0.0
    return best - runner_up


def is_low_confidence(ranked,
                      confidence_threshold: float = CONFIDENCE_THRESHOLD,
                      margin_threshold: float = MARGIN_THRESHOLD) -> bool:
    """Should the app answer "Unclear" for this ranking?

    Either signal is enough on its own:
      * the top-1 probability is below confidence_threshold, or
      * the winner is barely ahead of the runner-up (margin_threshold).
    Kept in one function so the API and scripts/evaluate.py always agree about
    what "low confidence" means.
    """
    return (float(ranked[0][1]) < confidence_threshold
            or top_two_margin(ranked) < margin_threshold)


def top_conditions(ranked, size: int = 3) -> list:
    """The best `size` conditions, each with its specialist, best-first.

    Each entry carries the specialist as well as the condition because the
    frontend shows the alternatives whenever the gate answers "Unclear", and
    the user should see which kind of doctor each possibility would mean.
    to_specialist is applied here so app/mapping.py stays the one place that
    knows the condition -> specialist table (the browser must not keep a
    second copy of it).
    """
    return [
        {"condition": condition,
         "specialist": to_specialist(condition),
         "confidence": round(float(probability), 3)}
        for condition, probability in ranked[:size]
    ]


def predict(text: str, threshold: float = CONFIDENCE_THRESHOLD,
            margin_threshold: float = MARGIN_THRESHOLD) -> dict:
    ranked = ranked_predictions([text])[0]
    top3 = top_conditions(ranked, 3)
    margin = round(top_two_margin(ranked), 3)

    if is_low_confidence(ranked, threshold, margin_threshold):
        return {"condition": "Unclear", "specialist": DEFAULT_SPECIALIST,
                "low_confidence": True, "top3": top3, "margin": margin}
    return {"condition": top3[0]["condition"],
            "specialist": to_specialist(top3[0]["condition"]),
            "low_confidence": False, "top3": top3, "margin": margin}
