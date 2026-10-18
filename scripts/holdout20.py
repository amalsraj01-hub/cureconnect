"""Frozen holdout benchmark for CureConnect - DO NOT EDIT THE 20 SENTENCES.

These 20 sentences were written on 2026-09-29, AFTER the model, the normaliser
(app/normalize.py) and the confidence gate (app/classifier.py) were finished.
They exist to answer one question honestly:

    "how does the app behave on realistic wording that was never in front of
     us while the pipeline was being built?"

Why they must stay frozen
-------------------------
The 125 sentences in data/test_sentences.csv were read, quoted and reasoned
about *while fixing* the pipeline, so their top-1 is optimistic (49.6% as of the
2026-10-01 normaliser fix; 47.2% before it). These 20
were never used for that, so they are the honest number. The moment one of them
is edited, reworded, reordered or "fixed" so that a result looks better, that
honesty is gone and the set becomes just another one the code was tuned
against.

Rules
-----
  * never edit, reword, reorder, add to or remove from HOLDOUT below;
  * if a benchmark number gets worse, fix the pipeline - never the sentence;
  * tests/test_holdout_frozen.py pins a fingerprint of the 20 sentences and
    fails if any one of them changes.

Run from the project root (the folder that holds app/ and data/):
    python scripts/holdout20.py
"""
import sys
from pathlib import Path

# Running "python scripts/holdout20.py" puts scripts/ on sys.path, not the
# project root, so importing the app package needs this small nudge.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.classifier import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    MARGIN_THRESHOLD,
    predict,
)
from app.mapping import to_specialist  # noqa: E402

# === FROZEN HOLDOUT SENTENCES - NEVER EDIT =================================
# Each pair is (everyday symptom sentence, the condition it is describing).
HOLDOUT = [
    ("a hot burning feeling rises behind my breastbone after heavy meals and "
     "my mouth fills with sour liquid", "GERD"),
    ("a nagging ache high in my abdomen comes about two hours after meals and "
     "settles once i eat again", "Peptic ulcer diseae"),
    ("my breathing has become fast and painful with fever and a chesty cough "
     "bringing up rusty spit", "Pneumonia"),
    ("my skin and eyes have gone yellow and i feel exhausted, there was a "
     "waterborne outbreak in my locality", "Hepatitis E"),
    ("whenever i delay a meal my hands start shaking and i go pale until i "
     "eat something sweet", "Hypoglycemia"),
    ("right after my first dose of a new medicine my lips and tongue swelled "
     "and a rash spread over my back", "Drug Reaction"),
    ("my appetite is huge but i keep getting thinner and my neck looks a "
     "little swollen", "Hyperthyroidism"),
    ("the whites of my eyes have turned yellow and my stool looks clay "
     "coloured", "Jaundice"),
    ("my mouth stays dry and i finish two bottles of water a day, and i pass "
     "a lot of urine", "Diabetes"),
    ("my urine is cloudy with a strong smell and it hurts at the end of "
     "passing it", "Urinary tract infection"),
    ("sharp pain low in my belly with a little blood in my urine since this "
     "morning", "Urinary tract infection"),
    ("before my periods i get a severe one sided headache with nausea that no "
     "tablet helps", "Migraine"),
    ("cold air makes me wheeze and i have to sit up at night to catch my "
     "breath", "Bronchial Asthma"),
    ("i came back from a forest trip and now i get spikes of fever with "
     "shivering and drenching sweats", "Malaria"),
    ("when i wake up my fingers are swollen and stiff and it takes an hour to "
     "loosen them", "Arthritis"),
    ("thick silvery flaky patches on my elbows that bleed when i scratch "
     "them", "Psoriasis"),
    ("my fever has been climbing slowly all week with tummy pain and i feel "
     "very weak", "Typhoid"),
    ("i have been passing watery stool and vomiting since i ate at a wedding",
     "Gastroenteritis"),
    ("rope like blue veins stand out on my calf and my leg aches heavily by "
     "evening", "Varicose veins"),
    ("a cough that has lasted a month now with blood in it and night sweats",
     "Tuberculosis"),
]
# === END FROZEN HOLDOUT SENTENCES ==========================================

FROZEN_ON = "2026-09-29"


def fingerprint():
    """SHA-256 of the 20 sentences, lowercased with whitespace squeezed.

    tests/test_holdout_frozen.py compares this against a pinned value, so any
    edit to a sentence - even one space - fails the test suite.
    """
    import hashlib
    joined = "\n".join(" ".join(text.split()).lower() for text, _ in HOLDOUT)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def measure(items):
    """Run the real app path - predict(), gate and all - over `items`."""
    rows = []
    correct_top1 = correct_top3 = fallback = shown_correct = specialist = 0
    for text, truth in items:
        result = predict(text)
        conditions = [entry["condition"] for entry in result["top3"]]
        hit1 = conditions[0] == truth
        hit3 = truth in conditions
        correct_top1 += hit1
        correct_top3 += hit3
        fallback += result["low_confidence"]
        shown_correct += hit1 and not result["low_confidence"]
        specialist += to_specialist(conditions[0]) == to_specialist(truth)
        rows.append({
            "truth": truth,
            "top1": conditions[0],
            "rank": conditions.index(truth) + 1 if hit3 else None,
            "confidence": result["top3"][0]["confidence"],
            "margin": result["margin"],
            "fallback": result["low_confidence"],
        })
    return rows, correct_top1, correct_top3, fallback, shown_correct, specialist


def main():
    rows, top1, top3, fallback, shown, specialist = measure(HOLDOUT)
    total = len(HOLDOUT)
    print("=" * 74)
    print("CureConnect - FROZEN 20-sentence holdout (never used to build the")
    print(f"pipeline; frozen {FROZEN_ON}; fingerprint {fingerprint()[:16]})")
    print("=" * 74)
    print(f"{'truth':<26}{'top-1 answer':<26}{'rank':>5}{'conf':>7}{'gate':>6}")
    print("-" * 74)
    for row in rows:
        rank = str(row["rank"]) if row["rank"] else ">3"
        print(f"{row['truth'][:25]:<26}{row['top1'][:25]:<26}"
              f"{rank:>5}{row['confidence']:>7.3f}"
              f"{'yes' if row['fallback'] else 'no':>6}")
    print("-" * 74)
    print(f"Top-1 accuracy         : {top1}/{total} = {top1 / total:.1%}")
    print(f"Top-3 accuracy         : {top3}/{total} = {top3 / total:.1%}")
    print(f"Fallback (app gate)    : {fallback}/{total} = "
          f"{fallback / total:.1%}  -> 'Unclear' in the app")
    print(f"  gate: confidence < {CONFIDENCE_THRESHOLD:.2f} or margin < "
          f"{MARGIN_THRESHOLD:.2f}")
    print(f"Specialist-level top-1 : {specialist}/{total} = "
          f"{specialist / total:.1%}")
    print(f"Shown AND correct      : {shown}/{total} = {shown / total:.1%}"
          f"  <- what a real user actually gets right")
    print("-" * 74)
    print("This set is deliberately hard: it over-samples the 9 mutually")
    print("confusable conditions plus the urination-related ones, so it sits")
    print("closer to a lower bound than to an average. Never 'fix' a sentence")
    print("to raise these numbers - fix app/normalize.py or the gate.")


if __name__ == "__main__":
    main()
