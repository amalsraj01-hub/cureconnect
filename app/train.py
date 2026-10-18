"""Train the baseline classifier.  Run:  python -m app.train"""
import pandas as pd
import joblib
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.model_selection import train_test_split

from app.normalize import normalize

DATA_PATH = "data/dataset.csv"
MODEL_PATH = "app/model.joblib"


def build_text(row, symptom_cols):
    parts = [str(row[c]).strip().replace("_", " ") for c in symptom_cols
             if pd.notna(row[c]) and str(row[c]).strip()]
    # Exactly the cleaning app/classifier.py applies at request time, so the
    # model is trained on the same wording it will be asked about later.
    return normalize(" ".join(parts))


def main():
    df = pd.read_csv(DATA_PATH)
    symptom_cols = [c for c in df.columns if c.lower().startswith("symptom")]
    df["text"] = df.apply(lambda r: build_text(r, symptom_cols), axis=1)
    df["Disease"] = df["Disease"].str.strip()

    X_train, X_test, y_train, y_test = train_test_split(
        df["text"], df["Disease"], test_size=0.2, random_state=42)

    model = make_pipeline(
        TfidfVectorizer(ngram_range=(1, 2)),
        LogisticRegression(max_iter=1000),
    )
    model.fit(X_train, y_train)
    print(f"Accuracy on clean test split: {model.score(X_test, y_test):.3f}")
    print("NOTE: this is optimistic. Evaluate on your own realistic sentences too.")

    joblib.dump(model, MODEL_PATH)
    print(f"Saved model to {MODEL_PATH}")


if __name__ == "__main__":
    main()
