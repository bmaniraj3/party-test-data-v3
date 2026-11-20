"""Step 1: prepare the data.

Loads the dirty person and organization files, splits the records into
train / val / test, and saves everything to the data/ folder.

Detector inputs and the answer key are saved in separate files, so a
detector can't see the answers by accident.

Run from the Class folder:  .venv/bin/python party-test-data-v3/projectscript/01_prepare_data.py
"""

from pathlib import Path

import pandas as pd
from sklearn.model_selection import train_test_split

DATASET = Path(__file__).resolve().parent.parent   # the party-test-data-v3 folder
OUTPUT = Path(__file__).resolve().parent / "data"  # projectscript/data

# Columns in the dirty files that describe the injected errors (the answers).
ANSWER_COLUMNS = ["dirt_label_ids", "dirt_events_json"]


def read_csv(path):
    # dtype=str: keep values as text (postal code "01126" keeps its zero).
    # keep_default_na=False: keep placeholders like "NULL" and "N/A" as text
    # instead of turning them into empty cells.
    return pd.read_csv(path, dtype=str, keep_default_na=False)


# --- Load the dirty records -------------------------------------------------

person = read_csv(DATASET / "dirty_person.csv")
person["entity_type"] = "person"

organization = read_csv(DATASET / "dirty_organization.csv")
organization["entity_type"] = "organization"


# --- Split records into train (70%), val (15%), test (15%) -----------------
# We split whole records, so all cells of one record land in the same split.
# "stratify" keeps every country and entity type evenly spread across splits.

all_records = pd.concat([person, organization], ignore_index=True)
group = all_records["entity_type"] + "_" + all_records["country_iso"]

train, rest = train_test_split(all_records, train_size=0.70, stratify=group, random_state=42)
val, test = train_test_split(rest, train_size=0.50, stratify=group[rest.index], random_state=42)

splits = pd.concat([
    pd.DataFrame({"record_id": train["record_id"], "split": "train"}),
    pd.DataFrame({"record_id": val["record_id"], "split": "val"}),
    pd.DataFrame({"record_id": test["record_id"], "split": "test"}),
])


# --- Reshape to one row per cell -------------------------------------------
# e.g. record AR-014001 becomes 13 rows: first_name, middle_name, last_name, ...
# This matches the layout of the answer key (eval_gold.csv).

cell_tables = []
for records in [person, organization]:
    fields = [c for c in records.columns if c not in ["record_id", "entity_type", *ANSWER_COLUMNS]]
    cells = records.melt(
        id_vars=["record_id", "entity_type"],
        value_vars=fields,
        var_name="field",
        value_name="raw_value",
    )
    cell_tables.append(cells)

cells = pd.concat(cell_tables, ignore_index=True)
cells = cells.merge(all_records[["record_id", "country_iso"]], on="record_id")
cells = cells.merge(splits, on="record_id")


# --- Load the answer key -----------------------------------------------------
# eval_gold.csv is built by party-test-data-v3/scripts/build_eval_gold.py.
# A cell is dirty when its contaminant_types list is not empty ("[]").

gold = read_csv(DATASET / "eval_gold.csv")
gold["is_dirty"] = gold["contaminant_types"] != "[]"
gold = gold.merge(splits, on="record_id")


# --- Detector inputs: records without the answer columns -------------------

records = all_records.drop(columns=ANSWER_COLUMNS).merge(splits, on="record_id")


# --- Sanity checks (the script stops here if any fail) ---------------------

assert len(records) == 35_000, "expected 17,500 persons + 17,500 organizations"
assert records["record_id"].is_unique, "duplicate record IDs"
assert len(cells) == len(gold) == 437_500, "expected 437,500 cells"

# Every cell must match its answer-key row exactly.
key = ["record_id", "entity_type", "field", "raw_value"]
assert len(cells.merge(gold[key], on=key)) == len(cells), "cells don't match eval_gold.csv"

# Every split must contain all 35 countries.
assert (records.groupby("split")["country_iso"].nunique() == 35).all(), "a split is missing countries"


# --- Save --------------------------------------------------------------------
# Parquet keeps every value as text, so "NULL" stays "NULL" when reloaded.

OUTPUT.mkdir(exist_ok=True)
records.to_parquet(OUTPUT / "records.parquet", index=False)  # inputs, one row per record
cells.to_parquet(OUTPUT / "cells.parquet", index=False)      # inputs, one row per cell
gold.to_parquet(OUTPUT / "gold.parquet", index=False)        # answer key, one row per cell
splits.to_csv(OUTPUT / "splits.csv", index=False)            # record_id -> split

print(f"Saved {len(records):,} records and {len(cells):,} cells to {OUTPUT}")
for name in ["train", "val", "test"]:
    part = gold[gold["split"] == name]
    print(f"  {name:<5} {len(part):>7,} cells, {part['is_dirty'].mean():.1%} dirty")
