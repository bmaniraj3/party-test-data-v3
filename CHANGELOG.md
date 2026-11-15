# Test-data changelog

Living log for dataset version folders. Student Q&A (stable IDs): [../../georgia-tech/questions_and_answers.md](../../georgia-tech/questions_and_answers.md).

## v1 (frozen folder)

Snapshot of the original student drop. Do **not** regenerate [`v1/`](v1/). Clean files keep names such as `clean_person_name_v1.csv`. Dirty CSVs may still say internal `dataset_version=dirty_v2` from that era.

**Known issues (do not “fix” in place):**

- **GT-01:** `MIS_NONASCII_IN_EMAIL_LOCAL` in dirt with empty gold contaminants (EAI still email).
- **GT-03:** AR/EE/IE phone uniqueness/example-number fallback. Phone metrics on those v1 slices are untrustworthy; omitting them on **v1 only** is a generation caveat, not a market exclusion.
- **GT-04:** Many dirt IDs used a single English literal.
- **GT-05:** RS names/addresses used `en_US` Faker.

## v2 (frozen folder)

Self-contained package in [`v2/`](v2/). Unversioned CSV names inside the folder. `dirt_distribution.csv` `dataset_version=v2`. Do **not** regenerate.

- Country lexicon + global pools; dirt IDs that were constants now `rng.choice` from lists / Faker.
- Dropped `MIS_NONASCII_IN_EMAIL_LOCAL` (GT-01). Email/tax placeholders and invalid syntax (`corrupt_email`, `corrupt_tax`).
- Job titles in person `first_name` / org name, not city. `MIS_ORG_TOKEN_IN_FIRST` = company name in a **person** given-name cell.
- Clean: tax format aliases, plus-addressing subset, unique E.164 phones (no example-number fallback; fake **substring** reject; uniqueness gate all 35 ISOs) (GT-02, GT-03).
- RS names/addresses: `hr_HR` proxy, documented; omit RS from name/address locale eval if it corrupts metrics (GT-05).
- Taxonomy and `build_eval_gold.py` live in the version folder.

**GT-06:** New versions land beside v1. Feedback loop is intentional. Some gaps remain (GT-05).

## v3 (current)

Self-contained package in [`v3/`](v3/). Clean CSVs match v2. `dirt_distribution.csv` `dataset_version=v3`.

- **`MIS_ADDR_STRIP_PREMISE`:** strip house/premise tokens from `address_line_1` and `address_line_2` when present (not ordinals, route numbers, or PT `S/N`). Gold adds `incomplete_premise` on mutated lines only. Street-only clean Faker lines stay clean.
- Dirt events are kept only if the row **changes**; no-ops resample, then placeholder fallback (**GT-07**).
- Eval: `--dataset-version v3`.

**GT-07:** Street-only vs missing premise; v2 dirty did not inject stripped numbers.
