"""Step 4: machine-learning detector.

Trains one small model per field on the train split. Each model looks at a
cell's value (and a few facts about its record) and predicts which problem
the cell has, or "clean". For example, it can learn that "Ramos" looks like
a family name, so it's wrong in first_name.

Saves two prediction files (same columns as rules_predictions.parquet):
  ml_predictions.parquet      the ML model on its own
  hybrid_predictions.parquet  rules + ML: a cell is flagged if either flags it

Only the train split's answers are used for training.

Run from the Class folder:  .venv/bin/python party-test-data-v3/projectscript/04_ml_detector.py
"""

import json
from pathlib import Path

import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"

KEY = ["record_id", "entity_type", "field"]
CLEAN = "clean"


# --- Features ------------------------------------------------------------------

def add_features(cells, records):
    """Simple numeric facts about each cell and its record."""
    v = cells["raw_value"]
    cells["length"] = v.str.len()
    cells["words"] = v.str.split().str.len()
    cells["digits"] = v.str.count(r"\d")
    cells["symbols"] = v.str.count(r"[^\w\s]")

    # Record facts that reveal name mix-ups, e.g. all names merged into first_name
    # leaves a long first_name with a blank middle and last name.
    names = records[["record_id", "first_name", "middle_name", "last_name"]].fillna("")
    facts = pd.DataFrame({
        "record_id": names["record_id"],
        "first_name_words": names["first_name"].str.split().str.len(),
        "middle_blank": (names["middle_name"].str.strip() == "").astype(int),
        "last_blank": (names["last_name"].str.strip() == "").astype(int),
    })
    return cells.merge(facts, on="record_id")


NUMERIC = ["length", "words", "digits", "symbols", "first_name_words", "middle_blank", "last_blank"]


def make_model():
    """Character patterns of the value + the numeric facts -> logistic regression."""
    features = ColumnTransformer([
        # Character snippets of 1-4 letters, e.g. "ez", "son", "@", "http".
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(1, 4), min_df=2, sublinear_tf=True), "raw_value"),
        ("facts", StandardScaler(), NUMERIC),
    ])
    return make_pipeline(features, LogisticRegression(max_iter=2000, C=5))


# --- Train and predict ---------------------------------------------------------

def main():
    cells = pd.read_parquet(DATA / "cells.parquet")
    records = pd.read_parquet(DATA / "records.parquet")
    gold = pd.read_parquet(DATA / "gold.parquet")

    cells = add_features(cells, records)

    # The answer for each cell, as one label: e.g. "status_token", or "clean".
    labels = gold[KEY].copy()
    labels["target"] = gold["contaminant_types"].map(lambda s: "+".join(sorted(json.loads(s))) or CLEAN)
    cells = cells.merge(labels, on=KEY)

    predictions = []
    for (entity, field), part in cells.groupby(["entity_type", "field"]):
        train = part[part["split"] == "train"]

        # Fields that are never dirty in training (e.g. country) are always predicted clean.
        if train["target"].nunique() < 2:
            predicted = pd.Series(CLEAN, index=part.index)
        else:
            model = make_model().fit(train[["raw_value", *NUMERIC]], train["target"])
            predicted = pd.Series(model.predict(part[["raw_value", *NUMERIC]]), index=part.index)
            print(f"  trained {entity:<12} {field:<22} on {len(train):,} cells")

        predictions.append(part[KEY + ["split"]].assign(label=predicted))

    ml = pd.concat(predictions, ignore_index=True)
    ml["predicted_types"] = ml["label"].map(lambda s: [] if s == CLEAN else s.split("+"))
    ml["is_flagged"] = ml["label"] != CLEAN
    ml = ml.drop(columns="label")
    ml.to_parquet(DATA / "ml_predictions.parquet", index=False)

    # Hybrid: combine rules and ML. A cell is flagged if either flags it.
    rules = pd.read_parquet(DATA / "rules_predictions.parquet")
    both = ml.merge(rules[KEY + ["predicted_types"]], on=KEY, suffixes=("_ml", "_rules"))
    both["predicted_types"] = [
        sorted(set(a) | set(b)) for a, b in zip(both["predicted_types_ml"], both["predicted_types_rules"])
    ]
    both["is_flagged"] = both["predicted_types"].map(len) > 0
    hybrid = both[KEY + ["split", "predicted_types", "is_flagged"]]
    hybrid.to_parquet(DATA / "hybrid_predictions.parquet", index=False)

    print(f"\nML flagged {ml['is_flagged'].sum():,} cells, hybrid flagged {hybrid['is_flagged'].sum():,}.")
    print(f"Saved ml_predictions.parquet and hybrid_predictions.parquet to {DATA}")


if __name__ == "__main__":
    main()
