import csv
from pathlib import Path

from app.mapping import DISEASE_TO_SPECIALIST


def test_every_dataset_disease_has_a_specialist_mapping():
    dataset_path = Path(__file__).resolve().parents[1] / "data" / "dataset.csv"
    with dataset_path.open(newline="", encoding="utf-8") as dataset_file:
        diseases = {
            row["Disease"].strip()
            for row in csv.DictReader(dataset_file)
            if row.get("Disease")
        }

    missing = diseases - DISEASE_TO_SPECIALIST.keys()
    assert not missing, f"Missing specialist mappings: {sorted(missing)}"