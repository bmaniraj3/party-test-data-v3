"""Step 3: score a detector's predictions against the answer key.

Works for any detector that saves a predictions file with these columns:
record_id, entity_type, field, predicted_types, is_flagged
(e.g. rules_predictions.parquet, or llm_predictions.parquet later).
Only the cells in the predictions file are scored, so a detector that
ran on a sample of records is scored on that sample.

Reports precision and recall for finding dirty cells:
  - overall
  - by field          (which fields the detector handles well)
  - by error type     (which injected errors it catches; recall only)
  - by label          (does it name the problem correctly, e.g. "status_token")
  - by country

Run from the Class folder, e.g.:
  .venv/bin/python party-test-data-v3/projectscript/03_score_predictions.py rules_predictions.parquet --split test
"""

import argparse
import json
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent  # the party-test-data-v3 folder
DATA = HERE / "data"
RESULTS = HERE / "results"

KEY = ["record_id", "entity_type", "field"]


def precision_recall(flagged, dirty):
    """Precision, recall and F1 for 'is this cell dirty?'."""
    tp = (flagged & dirty).sum()    # dirty and flagged
    fp = (flagged & ~dirty).sum()   # clean but flagged (false alarm)
    fn = (~flagged & dirty).sum()   # dirty but missed
    precision = tp / (tp + fp) if tp + fp else float("nan")
    recall = tp / (tp + fn) if tp + fn else float("nan")
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else float("nan")
    return {
        "dirty_cells": int(dirty.sum()), "flagged": int(flagged.sum()),
        "caught": int(tp), "false_alarms": int(fp), "missed": int(fn),
        "precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
    }


def scores_by(cells, column):
    """precision_recall() for each value of a column, e.g. each field."""
    rows = [{column: name, **precision_recall(g["is_flagged"], g["is_dirty"])}
            for name, g in cells.groupby(column)]
    return pd.DataFrame(rows)


def error_types_per_cell():
    """Which injected error type(s) hit each dirty cell, from the dirty files' event log."""
    rows = []
    for entity in ["person", "organization"]:
        dirty = pd.read_csv(DATASET / f"dirty_{entity}.csv", dtype=str, keep_default_na=False)
        for record_id, events in zip(dirty["record_id"], dirty["dirt_events_json"]):
            for event in json.loads(events):
                for field in event["fields_affected"]:
                    rows.append((record_id, entity, field, event["dirt_label_id"]))
    return pd.DataFrame(rows, columns=KEY + ["error_type"])


def recall_by_error_type(cells):
    """Share of cells hit by each error type that the detector flagged."""
    hits = error_types_per_cell().merge(cells[cells["is_dirty"]], on=KEY)
    table = hits.groupby("error_type").agg(dirty_cells=("is_flagged", "size"), caught=("is_flagged", "sum"))
    table["recall"] = (table["caught"] / table["dirty_cells"]).round(3)
    return table.sort_values("recall").reset_index()


def scores_by_label(cells):
    """For each label (e.g. corrupt_phone): did the detector name it on the right cells?"""
    rows = []
    labels = sorted(set().union(*cells["gold_types"], *cells["predicted_set"]))
    for label in labels:
        in_gold = cells["gold_types"].map(lambda s: label in s)
        in_pred = cells["predicted_set"].map(lambda s: label in s)
        rows.append({"label": label, **precision_recall(in_pred, in_gold)})
    return pd.DataFrame(rows).rename(columns={"dirty_cells": "gold_cells"})


def main():
    parser = argparse.ArgumentParser(description="Score a detector against the answer key.")
    parser.add_argument("predictions", help="file name in data/, e.g. rules_predictions.parquet")
    parser.add_argument("--split", default="test", choices=["train", "val", "test", "all"])
    args = parser.parse_args()

    # Join predictions with the answer key, cell by cell.
    predictions = pd.read_parquet(DATA / args.predictions)
    gold = pd.read_parquet(DATA / "gold.parquet")
    cells = predictions.merge(gold, on=KEY, how="inner", suffixes=("_pred", ""))
    if args.split != "all":
        cells = cells[cells["split"] == args.split]

    # Label sets: what the answer key says vs. what the detector said.
    cells["gold_types"] = cells["contaminant_types"].map(lambda s: set(json.loads(s)))
    cells["predicted_set"] = cells["predicted_types"].map(set)

    overall = precision_recall(cells["is_flagged"], cells["is_dirty"])
    by_field = scores_by(cells, "field")
    by_country = scores_by(cells, "country_iso")
    by_error = recall_by_error_type(cells)
    by_label = scores_by_label(cells)

    # Save each table as a CSV, named after the detector and split.
    name = Path(args.predictions).stem.replace("_predictions", "")
    out = RESULTS / f"{name}_{args.split}"
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([overall]).to_csv(out / "overall.csv", index=False)
    by_field.to_csv(out / "by_field.csv", index=False)
    by_country.to_csv(out / "by_country.csv", index=False)
    by_error.to_csv(out / "by_error_type.csv", index=False)
    by_label.to_csv(out / "by_label.csv", index=False)

    # Print a short summary.
    records = cells["record_id"].nunique()
    print(f"\n{args.predictions}, split={args.split}: {records:,} records, {len(cells):,} cells\n")
    print(f"Finding dirty cells: precision {overall['precision']:.3f}, recall {overall['recall']:.3f}, "
          f"F1 {overall['f1']:.3f}  ({overall['false_alarms']} false alarms, {overall['missed']} missed)\n")
    print("By field:")
    print(by_field[["field", "dirty_cells", "precision", "recall"]].to_string(index=False))
    print("\nHardest error types (lowest recall):")
    print(by_error.head(10).to_string(index=False))
    print(f"\nFull tables saved to {out}")


if __name__ == "__main__":
    main()
