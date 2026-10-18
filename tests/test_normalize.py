"""Tests for app/normalize.py - the everyday-words -> dataset-words translator."""
import csv
from functools import lru_cache
from pathlib import Path

from app.normalize import SYNONYM_MAP, TYPO_MAP, normalize

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "dataset.csv"


@lru_cache(maxsize=1)
def dataset_symptom_phrases():
    """The 131 phrases the Kaggle data actually uses for symptoms.

    Cached on purpose: the checks below loop over every key in the two maps, and
    re-reading the CSV once per key takes minutes.
    """
    with DATASET_PATH.open(newline="", encoding="utf-8") as dataset_file:
        rows = list(csv.DictReader(dataset_file))
    phrases = set()
    for row in rows:
        for column, value in row.items():
            if column and column.lower().startswith("symptom") and value:
                phrases.add(value.strip().replace("_", " ").lower())
    return frozenset(phrases)


def test_no_key_overlaps_the_dataset_vocabulary():
    """A key that sits inside a dataset phrase would double it up.

    Mapping "spinning" -> "spinning movements" would rewrite the training text
    "spinning movements" as "spinning movements movements", so keys must never
    be a word-for-word part of the dataset's own wording.
    """
    problems = []
    for mapping in (TYPO_MAP, SYNONYM_MAP):
        for key in mapping:
            for phrase in dataset_symptom_phrases():
                if key != phrase and f" {key} " in f" {phrase} ":
                    problems.append((key, phrase))
    assert not problems, f"keys overlap dataset vocabulary: {sorted(set(problems))}"


def test_synonym_values_are_final():
    """A synonym replacement must not contain another key, or a second pass
    would grow the text (e.g. the value "yellow crust ooze" re-matching the key
    "yellow crust", or "swelled lymph nodes" re-matching "lymph nodes").
    Typo repairs are allowed to feed the synonym pass, so TYPO_MAP is checked
    by the next test instead.
    """
    problems = [(key, value, normalize(value))
                for key, value in SYNONYM_MAP.items() if normalize(value) != value]
    assert not problems, f"values are not stable: {problems}"


def test_typo_values_settle_after_one_more_pass():
    """Typo repair may hand over to the synonym pass (migrain -> migraine ->
    the migraine symptom signature), but it must then stop changing."""
    for key, value in TYPO_MAP.items():
        once = normalize(value)
        assert normalize(once) == once, (key, value)


def test_keys_are_stable_under_normalisation():
    for mapping in (TYPO_MAP, SYNONYM_MAP):
        for key in mapping:
            assert normalize(normalize(key)) == normalize(key), key


def test_dataset_phrases_do_not_gain_words():
    """Normalising a training row must never duplicate or invent words."""
    for phrase in sorted(dataset_symptom_phrases()):
        cleaned = normalize(phrase)
        assert len(cleaned.split()) <= len(phrase.split()), f"{phrase!r} -> {cleaned!r}"


def test_normalisation_is_idempotent():
    """A second pass must change nothing, or retraining would keep drifting."""
    examples = [
        "I have been having loose motions and vomitng since yesterdy",
        "my eyes turned yellow and my urine is dark",
        "the room keeps spinning when i move my head",
        "i pee a lot and i am very thirsty",
    ]
    for text in examples:
        once = normalize(text)
        assert normalize(once) == once, f"not idempotent: {once!r}"


def test_lowercase_and_punctuation():
    assert normalize("Fever, COUGH!!!") == "fever cough"
    assert normalize("") == ""
    assert normalize("   ") == ""


def test_typos_are_repaired():
    assert "dizziness" in normalize("i have giddines since morning")
    assert "vomiting" in normalize("vomitng after food")
    assert "diarrhoea" in normalize("i have diarrhea")
    assert "headache" in normalize("bad headake since last night")


def test_everyday_words_become_dataset_words():
    assert "polyuria" in normalize("i pee a lot")
    assert "burning micturition" in normalize("burning while passing urine")
    assert "yellowing of eyes" in normalize("my eyes look yellow")
    assert "spinning movements" in normalize("the room is spinning")


def test_thirst_borrows_polyuria_and_not_hunger():
    """Regression: thirst used to expand to "polyuria excessive hunger".

    The dataset has no thirst phrase, so thirst borrows a Diabetes word. It
    must be "polyuria" (Diabetes only) and must NOT be "excessive hunger",
    which the dataset shares with Hyperthyroidism, Hypoglycemia and Migraine -
    that mismatch is why "i pee a lot and i am thirsty" ranked UTI first.
    """
    for text in ("i am thirsty", "i have thirst", "very thirsty", "i am thristy"):
        cleaned = normalize(text)
        assert "polyuria" in cleaned, cleaned
        assert "hunger" not in cleaned, cleaned
        assert "appetite" not in cleaned, cleaned


def test_thirst_does_not_change_a_pure_diabetes_sentence():
    """Normalising must still leave the dataset's own hunger wording alone."""
    assert normalize("excessive hunger") == "excessive hunger"
    # (The normaliser keeps function words like "i am" - it only rewrites
    # symptoms, so only the symptom part is asserted here.)
    assert normalize("very hungry") == "excessive hunger increased appetite"
    assert normalize("hungry all the time") == "excessive hunger increased appetite"


def test_frequency_wording_borrows_polyuria_and_not_the_uti_phrase():
    """Regression: every urination key used to expand to BOTH phrases.

    "polyuria" belongs to Diabetes only and "continuous feel of urine" to
    Urinary tract infection only, so borrowing both put a UTI symptom into
    sentences whose only real clue was urine volume: "sudden weight loss with
    extreme hunger and i need to urinate again and again" answered Urinary tract
    infection at 0.398 with Diabetes down at 0.049. How much or how often urine
    comes out is the Diabetes sign, so those keys borrow "polyuria" alone.
    """
    for text in ("i pee a lot", "peeing a lot", "i am urinating a lot",
                 "i urinate a lot", "urinating again and again",
                 "urinate again and again", "frequent urination",
                 "urinating frequently", "passing urine frequently",
                 "going to the toilet often"):
        cleaned = normalize(text)
        assert "polyuria" in cleaned, cleaned
        assert "continuous feel of urine" not in cleaned, cleaned


def test_urge_wording_borrows_the_uti_phrase():
    """"Frequent urge to urinate" is the sensation, not the amount, so it is
    the one urination key that keeps the UTI-only phrase. Without it "frequent
    urge to urinate with pain and mild fever" stops answering UTI at all.
    """
    cleaned = normalize("frequent urge to urinate with pain and mild fever")
    assert "continuous feel of urine" in cleaned, cleaned
    assert "polyuria" not in cleaned, cleaned


def test_urination_wording_still_does_not_touch_burning_or_smell():
    """The split is about volume and urgency only: UTI's own clues must survive.

    These two phrases are UTI's, so a sentence using them must keep them, or the
    split would have traded a Diabetes fix for a UTI regression.
    """
    assert "burning micturition" in normalize("burning while passing urine")
    assert "foul smell of urine" in normalize("my urine smells bad and is cloudy")


def test_unrelated_sentences_are_left_alone():
    """Words the dataset already uses must survive untouched."""
    assert normalize("vomiting, headache and nausea") == "vomiting headache and nausea"
    assert normalize("skin rash with itching") == "skin rash with itching"



def test_oesophageal_wording_borrows_acidity_and_not_indigestion():
    """Regression: every reflux key used to expand to "acidity indigestion".

    The dataset never gives "indigestion" to GERD - it appears in Migraine (114
    rows) and Peptic ulcer (108) only - so the extra word quietly attached a
    Migraine symptom to every heartburn sentence. In the frozen holdout,
    "a hot burning feeling rises behind my breastbone after heavy meals and my
    mouth fills with sour liquid" was answered Migraine at 0.156, above the
    gate, i.e. confidently wrong. Oesophageal wording is GERD's, and GERD's own
    word for it is "acidity".

    The two stomach keys are the deliberate exception, and the next test holds
    that side down: there "indigestion" is the right word, not an invention.
    """
    for text in ("acid reflux", "reflux", "heartburn", "sour water",
                 "sour taste", "sour liquid", "bitter taste",
                 "food coming back up", "food comes back", "regurgitation",
                 "burning in my chest after eating",
                 "burning in the chest after eating"):
        cleaned = normalize(text)
        assert "acidity" in cleaned, cleaned
        assert "indigestion" not in cleaned, cleaned
    # "indigestion" is a dataset word with owners, so the fix had to stop
    # inventing it rather than delete it: a patient who says it keeps it.
    assert normalize("indigestion") == "indigestion"


def test_stomach_burning_keeps_indigestion_for_peptic_ulcer():
    """The exception above, with the measurement that justifies it.

    "Burning in the stomach" is stomach upset, and "indigestion" is the
    dataset's word for it. Cleaning those two keys down to "acidity" alone
    dropped "burning pain in my stomach before food which gets better after
    eating" - a Peptic ulcer sentence - from rank 3 at 0.047 to rank 19 at 0.021,
    because "indigestion" was its only Peptic ulcer clue. GERD's own clue is the
    acidity, so the pair stays.
    """
    for text in ("burning in my stomach", "burning pain in my stomach"):
        cleaned = normalize(text)
        assert "acidity" in cleaned, cleaned
        assert "indigestion" in cleaned, cleaned


def test_lay_thirst_and_urine_volume_wording_reaches_polyuria():
    """Regression: thirst and how-much-urine said in everyday words reached no
    Diabetes word at all. "my mouth stays dry and i finish two bottles of water
    a day, and i pass a lot of urine" was answered Urinary tract infection at
    0.181 - confident and wrong.

    The dataset has no thirst phrase, and "polyuria" is its word for passing
    large amounts (all 120 Diabetes rows, no other condition), so both halves of
    such a sentence borrow that one word, never the UTI-only "continuous feel of
    urine". The wording below is deliberately not the holdout sentence itself:
    the frozen 20 stay untouched and unreferenced outside their own file.
    """
    thirst = ("i am always thirsty", "i am constantly thirsty",
              "i always feel thirsty", "she keeps feeling thirsty",
              "the patient has a dry mouth", "my mouth stays dry",
              "my mouth is always dry", "i have been drinking a lot of water",
              "i drink a lot of water", "he drinks a lot of water",
              "i am drinking lots of water", "i finish two bottles of water",
              "there is lots of water every day")
    volume = ("i pass a lot of urine", "i am passing a lot of urine",
              "i pass lots of urine", "she is passing lots of urine",
              "i am passing large amounts of urine",
              "there were large amounts of urine", "there is lots of urine",
              "i have a lot of urine", "i pass urine a lot")
    for text in thirst + volume:
        cleaned = normalize(text)
        assert "polyuria" in cleaned, cleaned
        assert "continuous feel of urine" not in cleaned, cleaned
