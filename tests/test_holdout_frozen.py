"""Guards the frozen 20-sentence holdout benchmark.

scripts/holdout20.py is only worth anything if its sentences were never used
while the pipeline was being fixed - and that is only true if they never
change. This test pins a SHA-256 fingerprint of the 20 sentences, so editing,
rewording, reordering, adding or removing even one fails the suite with a
message that explains why.

Nothing here loads app/model.joblib: it checks the benchmark's identity, not
its score, so a retrain can never break it and it stays fast.
"""
import csv
import importlib.util
from pathlib import Path

from app.mapping import DISEASE_TO_SPECIALIST

PROJECT_ROOT = Path(__file__).resolve().parents[1]
HOLDOUT_PATH = PROJECT_ROOT / "scripts" / "holdout20.py"
TEST_SENTENCES_PATH = PROJECT_ROOT / "data" / "test_sentences.csv"

# SHA-256 of the 20 sentences, lowercased with whitespace squeezed.
# Only ever recompute this by starting a deliberate new benchmark (see
# README.md) - never by "fixing" a sentence so that a score looks better.
FROZEN_FINGERPRINT = (
    "6f5f4dd64beb46535d9b9690252bab6944bf4be46cd2161724c70afcace9572a")
FROZEN_COUNT = 20


def load_holdout():
    """Import scripts/holdout20.py without running its report."""
    spec = importlib.util.spec_from_file_location("holdout20", HOLDOUT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_frozen_benchmark_still_exists():
    assert HOLDOUT_PATH.exists(), (
        "scripts/holdout20.py holds the only honest accuracy number we have "
        "(40.0% top-1 on wording the pipeline never saw). Do not delete it."
    )


def test_it_still_holds_exactly_twenty_sentences():
    assert len(load_holdout().HOLDOUT) == FROZEN_COUNT


def test_the_twenty_sentences_are_unchanged():
    module = load_holdout()
    assert module.fingerprint() == FROZEN_FINGERPRINT, (
        "The frozen holdout sentences changed. They are frozen on purpose: "
        "they were written AFTER the model, the normaliser and the gate were "
        "finished, so they measure realistic wording none of that work ever "
        "saw. Editing one - even rewording it, or fixing a typo in it - makes "
        "the set just another one the code was tuned against, and the honest "
        "number is gone. If a sentence does badly, fix app/normalize.py or the "
        "gate; if you want a new benchmark, add a new file and update the "
        "fingerprint deliberately (see README.md)."
    )


def test_none_of_them_was_recycled_from_the_evaluation_set():
    module = load_holdout()
    with TEST_SENTENCES_PATH.open(encoding="utf-8", newline="") as handle:
        known = {row["text"].strip().lower() for row in csv.DictReader(handle)}
    reused = [text for text, _ in module.HOLDOUT
              if text.strip().lower() in known]
    assert not reused, (
        f"these holdout sentences are copied from data/test_sentences.csv, so "
        f"they are not a holdout at all: {reused}")


def test_every_label_is_a_condition_the_mapping_table_knows():
    module = load_holdout()
    unknown = [label for _, label in module.HOLDOUT
               if label not in DISEASE_TO_SPECIALIST]
    assert not unknown, (
        f"holdout labels missing from DISEASE_TO_SPECIALIST, so the "
        f"specialist-level score would be measured against a fallback: "
        f"{unknown}")
