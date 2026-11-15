# Test-data quality checks (v3)

Use this checklist before approving a benchmark dataset for experiments.

## Coverage checks
- [ ] All target problem slices are represented.
- [ ] All target semantic classes have enough examples.
- [ ] Edge cases are present, not only easy examples.
- [ ] Email dirt is placeholders/invalid syntax only (no EAI-as-dirt).
- [ ] Tax dirt is placeholders/malformed only (format aliases stay clean).

## Label checks
- [ ] Labels are internally consistent.
- [ ] Mismatch labels align with attribute intent.
- [ ] Placeholder labels cover known variants (lexicon, not one English literal).
- [ ] Every `dirt_label_id` in taxonomy maps to a **non-empty** contaminant type list.
- [ ] All `dirt_events_json` events use `application_mode: replace`.
- [ ] Every kept dirt event mutates at least one field (no-op events resampled).
- [ ] `dirt_distribution.csv` `dataset_version` is `v3`.
- [ ] `MIS_ADDR_STRIP_PREMISE` rows changed `address_line_1` and/or `address_line_2`.

## Split checks
- [ ] Train, validation, and test splits are defined at eval time (not in these CSVs).
- [ ] No duplicate leakage across splits.
- [ ] Class distribution drift across splits is acceptable.

## Realism checks
- [ ] Synthetic records reflect realistic party-data patterns.
- [ ] Dirt surface strings vary (pools / Faker), not v1 constants only.
- [ ] Phone uniqueness gate holds for all 35 ISOs in each phone file.
- [ ] Serbia name/address rows are documented as `hr_HR` proxy.

## Governance checks
- [ ] Dataset source and usage permissions are documented.
- [ ] Sensitive fields are protected or anonymized.
- [ ] This folder is the version freeze for the current drop; older drops stay in `v1/` and `v2/`.
