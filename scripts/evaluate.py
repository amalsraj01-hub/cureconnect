"""Evaluate the saved CureConnect model on my own realistic symptom sentences.

Important: this measures the CLASSIFIER only. In the real app, app/safety.py
runs first, so a sentence like "severe chest pain" would trigger the emergency
message and the classifier would never be asked at all.

Run from the project root (the folder that contains app/ and data/):
    python scripts/evaluate.py

Optional:
    python scripts/evaluate.py --show-misses 40
"""
import argparse
from pathlib import Path
import sys

import pandas as pd

# Running "python scripts/evaluate.py" puts the scripts/ folder on sys.path,
# not the project root, so importing the app package needs this small nudge.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# app.classifier owns the text cleaning and the threshold, so this script can
# never report numbers that differ from what the API actually does.
from app.classifier import (  # noqa: E402
    CONFIDENCE_THRESHOLD,
    MARGIN_THRESHOLD,
    MODEL_PATH,
    is_low_confidence,
    ranked_predictions,
    top_two_margin,
)
from app.mapping import to_specialist  # noqa: E402

DATASET_PATH = PROJECT_ROOT / "data" / "dataset.csv"
SENTENCES_PATH = PROJECT_ROOT / "data" / "test_sentences.csv"

# Thresholds to compare when deciding how strict the "Unclear" gate should be.
SWEEP_THRESHOLDS = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50]
CONFIDENCE_BUCKETS = [(0.0, 0.05), (0.05, 0.10), (0.10, 0.20),
                      (0.20, 0.30), (0.30, 0.50), (0.50, 1.01)]

# The gate CureConnect shipped while the text was still raw, kept only so the
# report can show what moving away from it bought.
OLD_CONFIDENCE_THRESHOLD = 0.30

# Margins to compare when deciding how close two conditions may be before the
# app refuses to choose between them. 0.00 is the confidence-only baseline,
# because every margin is at least zero.
MARGIN_SWEEP = [0.00, 0.01, 0.02, 0.05, 0.10, 0.15, 0.20]
MARGIN_BUCKETS = [(0.0, 0.02), (0.02, 0.05), (0.05, 0.10),
                  (0.10, 0.20), (0.20, 0.40), (0.40, 1.01)]


def _rate(flags, indexes):
    """Share of True among the given positions (NaN when nothing to measure)."""
    if not indexes:
        return float("nan")
    return sum(flags[i] for i in indexes) / len(indexes)


def describe_confidence(confidences):
    """Min / quartiles / max and a text histogram of the top-1 confidence."""
    series = pd.Series(confidences)
    print("-" * 74)
    print("Top-1 confidence spread (how sure the model is on realistic text)")
    print(f"  min {series.min():.3f}   25% {series.quantile(0.25):.3f}   "
          f"median {series.median():.3f}   75% {series.quantile(0.75):.3f}   "
          f"max {series.max():.3f}   mean {series.mean():.3f}")
    print("  histogram (one # per sentence):")
    for low, high in CONFIDENCE_BUCKETS:
        count = int(((series >= low) & (series < high)).sum())
        print(f"    {low:.2f}-{high:.2f} : {count:>3}  {'#' * count}")


def show_threshold_sweep(confidences, top1_flags, top3_flags):
    """What the user would see at different 'Unclear' thresholds."""
    print("-" * 74)
    print("Threshold sweep: 'shown' = user gets a specialist answer,")
    print("'fallback' = user gets 'Unclear, see a General Physician'")
    print(f"{'thresh':>7}{'shown':>8}{'fallback':>10}{'top-1|shown':>13}"
          f"{'top-3|shown':>13}{'top-1|hidden':>14}")
    for threshold in SWEEP_THRESHOLDS:
        shown = [i for i, c in enumerate(confidences) if c >= threshold]
        hidden = [i for i, c in enumerate(confidences) if c < threshold]
        print(f"{threshold:>7.2f}{len(shown) / len(confidences):>8.0%}"
              f"{len(hidden) / len(confidences):>10.0%}"
              f"{_rate(top1_flags, shown):>13.1%}{_rate(top3_flags, shown):>13.1%}"
              f"{_rate(top1_flags, hidden):>14.1%}")
    print("  'top-1|hidden' tells you whether the answers we hid were actually")
    print("  worse than the ones we showed. If it is close, the gate is")
    print("  throwing away correct answers for nothing.")


def describe_margins(margins):
    """Min / quartiles / max and a text histogram of (top-1 minus top-2)."""
    series = pd.Series(margins)
    print("-" * 74)
    print("Top-1 minus top-2 margin spread (how far ahead the winner is)")
    print(f"  min {series.min():.3f}   25% {series.quantile(0.25):.3f}   "
          f"median {series.median():.3f}   75% {series.quantile(0.75):.3f}   "
          f"max {series.max():.3f}   mean {series.mean():.3f}")
    print("  histogram (one # per sentence):")
    for low, high in MARGIN_BUCKETS:
        count = int(((series >= low) & (series < high)).sum())
        print(f"    {low:.2f}-{high:.2f} : {count:>3}  {'#' * count}")


def show_margin_sweep(confidences, margins, top1_flags, top3_flags):
    """What the margin veto costs and buys, with the threshold held fixed."""
    print("-" * 74)
    print(f"Margin sweep (confidence threshold held at {CONFIDENCE_THRESHOLD:.2f}):")
    print("  shown  = confidence >= threshold AND margin >= the value below")
    print("  vetoed = confidence alone would have shown it, the margin hid it")
    print(f"{'margin':>7}{'shown':>8}{'fallback':>10}{'top-1|shown':>13}"
          f"{'top-3|shown':>13}{'top-1|hidden':>14}{'vetoed':>8}")
    for margin in MARGIN_SWEEP:
        shown = [i for i in range(len(confidences))
                 if confidences[i] >= CONFIDENCE_THRESHOLD and margins[i] >= margin]
        shown_lookup = set(shown)
        hidden = [i for i in range(len(confidences)) if i not in shown_lookup]
        vetoed = [i for i in range(len(confidences))
                  if confidences[i] >= CONFIDENCE_THRESHOLD and margins[i] < margin]
        print(f"{margin:>7.2f}{len(shown) / len(confidences):>8.0%}"
              f"{len(hidden) / len(confidences):>10.0%}"
              f"{_rate(top1_flags, shown):>13.1%}{_rate(top3_flags, shown):>13.1%}"
              f"{_rate(top1_flags, hidden):>14.1%}{len(vetoed):>8}")
    print("  As the veto starts biting, 'top-1|hidden' should fall well below")
    print("  'top-1|shown'. If it does not, the margin is hiding correct answers")
    print("  and should stay small.")


def show_gate_comparison(ranked_rows, confidences, top1_flags, top3_flags):
    """The old gate and the new ones side by side, on one identical run."""
    rules = [
        (f"confidence < {OLD_CONFIDENCE_THRESHOLD:.2f} (the old gate)",
         lambda index: confidences[index] < OLD_CONFIDENCE_THRESHOLD),
        (f"confidence < {CONFIDENCE_THRESHOLD:.2f} (new)",
         lambda index: confidences[index] < CONFIDENCE_THRESHOLD),
        (f"confidence < {CONFIDENCE_THRESHOLD:.2f} or margin < {MARGIN_THRESHOLD:.2f}",
         lambda index: is_low_confidence(ranked_rows[index])),
    ]
    print("-" * 74)
    print("The old gate vs the new ones, same model and same sentences:")
    print(f"{'gate':<47}{'fallback':>10}{'top-1|shown':>13}{'top-3|shown':>13}")
    for label, hides in rules:
        hidden = [index for index in range(len(ranked_rows)) if hides(index)]
        hidden_lookup = set(hidden)
        shown = [index for index in range(len(ranked_rows))
                 if index not in hidden_lookup]
        print(f"{label:<47}{len(hidden) / len(ranked_rows):>10.0%}"
              f"{_rate(top1_flags, shown):>13.1%}{_rate(top3_flags, shown):>13.1%}")
    print("  'top-1|shown' / 'top-3|shown' are the accuracy a user actually")
    print("  experiences, because hidden sentences never show an answer at all.")


def show_vetoed_examples(ranked_rows, df, confidences, margins, limit=6):
    """The sentences confidence alone would have shown but the margin hid."""
    vetoed = [index for index in range(len(ranked_rows))
              if confidences[index] >= CONFIDENCE_THRESHOLD
              and margins[index] < MARGIN_THRESHOLD]
    print("-" * 74)
    print(f"What the margin veto caught (confidence >= {CONFIDENCE_THRESHOLD:.2f} "
          f"but margin < {MARGIN_THRESHOLD:.2f}): {len(vetoed)} sentences")
    for index in vetoed[:limit]:
        top1_condition, top1_probability = ranked_rows[index][0]
        runner_up = (ranked_rows[index][1] if len(ranked_rows[index]) > 1
                     else ("-", 0.0))
        print(f"  truth {df['disease'].iloc[index]!r} vs "
              f"{top1_condition!r} + {runner_up[0]!r}: "
              f"confidence {top1_probability:.2f}, margin {margins[index]:.2f}")
        print(f"      '{df['text'].iloc[index][:100]}'")
    if len(vetoed) > limit:
        print(f"  ...and {len(vetoed) - limit} more")
    print("  These are near-ties: the top-2 gap is smaller than the margin, so")
    print("  the honest answer is 'a General Physician', not a coin flip.")


def main():
    parser = argparse.ArgumentParser(description="Evaluate the classifier.")
    parser.add_argument("--show-misses", type=int, default=25,
                        help="how many misclassified sentences to print")
    args = parser.parse_args()

    if not Path(MODEL_PATH).exists():
        sys.exit("Model not found. Run: python -m app.train")
    if not SENTENCES_PATH.exists():
        sys.exit(f"Not found: {SENTENCES_PATH}")

    df = pd.read_csv(SENTENCES_PATH)
    df["text"] = df["text"].fillna("").astype(str).str.strip()
    df["disease"] = df["disease"].fillna("").astype(str).str.strip()
    df = df[(df["text"] != "") & (df["disease"] != "")].reset_index(drop=True)

    # app.classifier owns the text cleaning, so this cannot drift from the API.
    ranked_rows = ranked_predictions(df["text"].tolist())

    top1_flags, top3_flags, specialist_flags, confidences = [], [], [], []
    margins = []
    per_disease = {}
    misses = []

    for text, truth, ranked in zip(df["text"], df["disease"], ranked_rows):
        top1_condition, top1_probability = ranked[0]
        in_top3 = truth in [condition for condition, _ in ranked[:3]]
        # The app only ever promises a SPECIALIST, and several diseases share
        # one (Hepatitis B/C/D/E are all Gastroenterology), so score that too.
        right_specialist = to_specialist(top1_condition) == to_specialist(truth)

        top1_flags.append(top1_condition == truth)
        top3_flags.append(in_top3)
        specialist_flags.append(right_specialist)
        confidences.append(top1_probability)
        margins.append(top_two_margin(ranked))

        stats = per_disease.setdefault(truth, {"n": 0, "top1": 0, "top3": 0})
        stats["n"] += 1
        stats["top1"] += top1_condition == truth
        stats["top3"] += in_top3

        if top1_condition != truth:
            misses.append((truth, top1_condition, top1_probability, text))

    total = len(df)
    # Ask the app's own gate, so this report can never drift from predict().
    fallback = [i for i, ranked in enumerate(ranked_rows) if is_low_confidence(ranked)]
    print("=" * 74)
    print("CureConnect - model evaluation on realistic free-text sentences")
    print("=" * 74)
    print(f"Sentences evaluated      : {total}")
    print(f"Distinct diseases        : {df['disease'].nunique()}")
    print(f"Top-1 accuracy           : {sum(top1_flags) / total:.1%}  "
          f"({sum(top1_flags)}/{total})")
    print(f"Top-3 accuracy           : {sum(top3_flags) / total:.1%}  "
          f"({sum(top3_flags)}/{total})")
    print(f"Specialist-level top-1   : {sum(specialist_flags) / total:.1%}  "
          f"({sum(specialist_flags)}/{total})  <- what the user actually sees")
    print(f"Fallback (app gate)      : {len(fallback)}/{total} "
          f"({len(fallback) / total:.1%}) -> 'Unclear' in the app")
    print(f"  gate: confidence < {CONFIDENCE_THRESHOLD:.2f} "
          f"or margin < {MARGIN_THRESHOLD:.2f}")

    describe_confidence(confidences)
    describe_margins(margins)
    show_threshold_sweep(confidences, top1_flags, top3_flags)
    show_margin_sweep(confidences, margins, top1_flags, top3_flags)
    show_vetoed_examples(ranked_rows, df, confidences, margins)
    show_gate_comparison(ranked_rows, confidences, top1_flags, top3_flags)

    if DATASET_PATH.exists():
        dataset_diseases = set(
            pd.read_csv(DATASET_PATH)["Disease"].astype(str).str.strip()
        )
        uncovered = sorted(dataset_diseases - set(df["disease"]))
        print("Coverage check           : "
              + ("every dataset disease has test sentences"
                 if not uncovered else f"NOT covered: {uncovered}"))

    print("-" * 74)
    print(f"{'disease':<40}{'n':>4}{'top-1':>9}{'top-3':>9}")
    print("-" * 74)
    for disease, stats in sorted(
            per_disease.items(),
            key=lambda item: (item[1]["top1"] / item[1]["n"], item[0])):
        print(f"{disease[:39]:<40}{stats['n']:>4}"
              f"{stats['top1'] / stats['n']:>8.0%}{stats['top3'] / stats['n']:>9.0%}")

    print("-" * 74)
    print(f"Example misses (up to {args.show_misses} of {len(misses)}):")
    for truth, predicted, probability, text in misses[:max(args.show_misses, 0)]:
        print(f"  truth={truth!r}  predicted={predicted!r} "
              f"(confidence {probability:.2f})")
        print(f"      '{text[:110]}'")

    print("-" * 74)
    print("Reminder: top-1 counts only the model's first guess. Top-3 counts the")
    print("truth appearing anywhere in the first three guesses, which is what the")
    print("app actually shows the user. Specialist-level top-1 is the honest score")
    print("for this app, since patients are sent to a specialist, not a diagnosis.")
    print("'Unclear' needs confidence < the threshold OR a margin under the margin")
    print("threshold; predict() makes that call in one function, so the API and this")
    print("report always agree.")
    print("This run does NOT test app/safety.py, which runs before the classifier.")


if __name__ == "__main__":
    main()
