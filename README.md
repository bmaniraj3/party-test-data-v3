# Dataset package v3 (current)

Self-contained generation: specs, scripts, `placeholder_lexicon.yaml`, `taxonomy/`, and CSVs.

Do not mix with [../v1/](../v1/) or [../v2/](../v2/). Regenerate **only** with scripts in this folder. Clean CSVs match v2; dirty generation adds `MIS_ADDR_STRIP_PREMISE` and keeps a dirt event only when the row actually changes.

## Generate

```powershell
cd initiatives/party-data-classification/self-research/test-data/v3
pip install -r requirements-test-data.txt
python scripts/validate_country_profiles.py
python scripts/generate_clean_country_party_data.py
python scripts/generate_dirty_party_data.py
python scripts/build_eval_gold.py
```

`eval_gold.csv` is gitignored; rebuild after dirt or taxonomy changes.

## Eval harness

From `ml-semantic-eval`: `--dataset-version v3`. Gold path: `eval_gold.csv` in this folder.

Changelog and student Q&A: [../CHANGELOG.md](../CHANGELOG.md), [../../../georgia-tech/questions_and_answers.md](../../../georgia-tech/questions_and_answers.md).
