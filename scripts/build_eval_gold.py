#!/usr/bin/env python3
"""Build eval_gold.csv from this version folder's dirty CSVs plus taxonomy/ labels."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
DATASET_DIR = SCRIPT_DIR.parent
TAX_DIR = DATASET_DIR / "taxonomy"

PERSON_FIELDS = [
    "first_name",
    "middle_name",
    "last_name",
    "address_line_1",
    "address_line_2",
    "city",
    "postal_code",
    "country",
    "country_iso",
    "state",
    "email",
    "phone",
    "drivers_license_number",
]

ORG_FIELDS = [
    "organization_name",
    "address_line_1",
    "address_line_2",
    "city",
    "postal_code",
    "country",
    "country_iso",
    "state",
    "email",
    "phone",
    "tax_id",
    "duns_number",
]


def load_csv_index(path: Path, key_fields: Tuple[str, ...]) -> Dict[Tuple[str, str], Dict[str, str]]:
    out: Dict[Tuple[str, str], Dict[str, str]] = {}
    with path.open(encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            k = tuple(row[x] for x in key_fields)
            out[k] = row
    return out


def _address_row_for_key(
    key: Tuple[str, str],
    by_file: Dict[str, Dict[Tuple[str, str], Dict[str, str]]],
) -> Dict[str, str]:
    if key in by_file["pa"]:
        return by_file["pa"][key]
    return by_file["oa"].get(key, {})


def merge_clean_record(
    key: Tuple[str, str],
    by_file: Dict[str, Dict[Tuple[str, str], Dict[str, str]]],
) -> Dict[str, str]:
    r: Dict[str, str] = {"record_id": key[0], "country_iso": key[1]}
    field_order = [
        ("pn", ["first_name", "middle_name", "last_name"]),
        ("on", ["organization_name"]),
        ("dl", ["drivers_license_number"]),
        ("tx", ["tax_id"]),
        ("dn", ["duns_number"]),
    ]
    for tag, fields in field_order:
        row = by_file[tag].get(key, {})
        for fld in fields:
            r[fld] = row.get(fld, "").strip()
    r["email"] = (by_file["em_p"].get(key) or {}).get("email", "").strip() or (
        by_file["em_o"].get(key) or {}
    ).get("email", "").strip()
    r["phone"] = (by_file["ph_p"].get(key) or {}).get("phone", "").strip() or (
        by_file["ph_o"].get(key) or {}
    ).get("phone", "").strip()
    addr = _address_row_for_key(key, by_file)
    for fld in ["country", "address_line_1", "address_line_2", "city", "postal_code", "state"]:
        r[fld] = addr.get(fld, "").strip()
    return r


def load_merged_clean(test_data_dir: Path) -> Dict[Tuple[str, str], Dict[str, str]]:
    by_file = {
        "pn": load_csv_index(test_data_dir / "clean_person_name.csv", ("record_id", "country_iso")),
        "on": load_csv_index(test_data_dir / "clean_organization_name.csv", ("record_id", "country_iso")),
        "pa": load_csv_index(test_data_dir / "clean_person_address.csv", ("record_id", "country_iso")),
        "oa": load_csv_index(test_data_dir / "clean_organization_address.csv", ("record_id", "country_iso")),
        "em_p": load_csv_index(test_data_dir / "clean_person_email.csv", ("record_id", "country_iso")),
        "em_o": load_csv_index(test_data_dir / "clean_organization_email.csv", ("record_id", "country_iso")),
        "ph_p": load_csv_index(test_data_dir / "clean_person_phone.csv", ("record_id", "country_iso")),
        "ph_o": load_csv_index(test_data_dir / "clean_organization_phone.csv", ("record_id", "country_iso")),
        "dl": load_csv_index(test_data_dir / "clean_drivers_license_number.csv", ("record_id", "country_iso")),
        "tx": load_csv_index(test_data_dir / "clean_tax_id.csv", ("record_id", "country_iso")),
        "dn": load_csv_index(test_data_dir / "clean_duns_number.csv", ("record_id", "country_iso")),
    }
    keys: Set[Tuple[str, str]] = set()
    for d in by_file.values():
        keys |= set(d.keys())
    return {k: merge_clean_record(k, by_file) for k in sorted(keys)}


def assert_contaminants_nonempty(contaminants: Dict[str, Dict[str, List[str]]]) -> None:
    for lid, cmap in contaminants.items():
        for field, types in (cmap or {}).items():
            if not types:
                raise ValueError(f"empty contaminant types for {lid} field {field} (dirt must be flaggable)")


def load_taxonomy() -> Tuple[Dict[str, Dict[str, List[str]]], Dict[str, Dict[str, List[str]]]]:
    with (TAX_DIR / "field_intent.yaml").open(encoding="utf-8") as f:
        field_intent = yaml.safe_load(f)
    with (TAX_DIR / "dirt_label_to_types.yaml").open(encoding="utf-8") as f:
        dirt_doc = yaml.safe_load(f)
    contaminants: Dict[str, Dict[str, List[str]]] = dirt_doc.get("contaminants") or {}
    assert_contaminants_nonempty(contaminants)
    return field_intent, contaminants


def gold_for_field(
    entity: str,
    field: str,
    events: List[Dict[str, Any]],
    field_intent: Dict[str, Dict[str, List[str]]],
    contaminants: Dict[str, Dict[str, List[str]]],
    unknown_labels: Set[str],
) -> Tuple[List[str], List[str], List[str], List[str]]:
    intent = list(field_intent.get(entity, {}).get(field, []))
    extra: List[str] = []
    modes_seen: List[str] = []
    for ev in events:
        lid = ev.get("dirt_label_id") or ""
        affected = ev.get("fields_affected") or []
        if field not in affected:
            continue
        mode = ev.get("application_mode")
        if isinstance(mode, str) and mode.strip():
            modes_seen.append(mode.strip())
        cmap = contaminants.get(lid)
        if cmap is None:
            unknown_labels.add(lid)
            continue
        types_for_field = cmap.get(field)
        if types_for_field is None:
            continue
        extra.extend(types_for_field)
    gold = sorted(set(intent) | set(extra))
    application_modes = sorted(set(modes_seen))
    return gold, intent, sorted(set(extra)), application_modes


def iter_gold_rows(
    dirty_path: Path,
    entity: str,
    fields: List[str],
    field_intent: Dict[str, Dict[str, List[str]]],
    contaminants: Dict[str, Dict[str, List[str]]],
    clean_by_key: Dict[Tuple[str, str], Dict[str, str]],
    unknown_labels: Set[str],
) -> List[Dict[str, str]]:
    rows_out: List[Dict[str, str]] = []
    with dirty_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = (row["record_id"], row["country_iso"])
            clean_row = clean_by_key.get(key, {})
            try:
                events = json.loads(row["dirt_events_json"])
            except json.JSONDecodeError as e:
                raise ValueError(f"Bad JSON for {key}: {e}") from e
            for field in fields:
                if field not in row:
                    continue
                raw_value = row[field]
                gold, intent, contam, dirt_modes = gold_for_field(
                    entity, field, events, field_intent, contaminants, unknown_labels
                )
                rows_out.append(
                    {
                        "record_id": row["record_id"],
                        "country_iso": row["country_iso"],
                        "entity_type": entity,
                        "field": field,
                        "raw_value": raw_value,
                        "clean_value": clean_row.get(field, ""),
                        "intent_types": json.dumps(intent),
                        "contaminant_types": json.dumps(contam),
                        "dirt_application_modes": json.dumps(dirt_modes),
                    }
                )
    return rows_out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build eval_gold.csv from dirty data + taxonomy.")
    parser.add_argument(
        "--test-data-dir",
        type=Path,
        default=DATASET_DIR,
        help="Version folder containing dirty_*.csv and clean_*.csv",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DATASET_DIR / "eval_gold.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()
    test_data: Path = args.test_data_dir.resolve()
    out_path: Path = args.output.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    field_intent, contaminants = load_taxonomy()
    unknown_labels: Set[str] = set()
    clean_by_key = load_merged_clean(test_data)

    person_dirty = test_data / "dirty_person.csv"
    org_dirty = test_data / "dirty_organization.csv"
    if not person_dirty.is_file() or not org_dirty.is_file():
        print("Missing dirty_person.csv or dirty_organization.csv under test-data-dir", file=sys.stderr)
        sys.exit(1)

    all_rows: List[Dict[str, str]] = []
    all_rows.extend(
        iter_gold_rows(
            person_dirty, "person", PERSON_FIELDS, field_intent, contaminants, clean_by_key, unknown_labels
        )
    )
    all_rows.extend(
        iter_gold_rows(
            org_dirty, "organization", ORG_FIELDS, field_intent, contaminants, clean_by_key, unknown_labels
        )
    )

    fieldnames = [
        "record_id",
        "country_iso",
        "entity_type",
        "field",
        "raw_value",
        "clean_value",
        "intent_types",
        "contaminant_types",
        "dirt_application_modes",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    print(f"Wrote {len(all_rows)} rows to {out_path}")
    if unknown_labels:
        print("WARN: dirt_label_ids missing from dirt_label_to_types.yaml:", ", ".join(sorted(unknown_labels)))
        sys.exit(1)


if __name__ == "__main__":
    main()
