"""LLM Step 3: build the prompt.

The prompt has two parts:
  1. Instructions (the same for every record): the task, what each field
     should contain, the error types, and worked examples from the TRAIN split.
  2. The record to check (changes every call), as JSON.

Keeping part 1 identical on every call lets the API cache it (cheaper).

Run it to save the full prompt to data/llm_prompt.txt so you can read it:
    .venv/bin/python party-test-data-v3/projectscript/03_llm_prompt.py
"""

import json
from pathlib import Path

import pandas as pd
import yaml

DATASET = Path(__file__).resolve().parent.parent   # the party-test-data-v3 folder
DATA = Path(__file__).resolve().parent / "data"    # projectscript/data


# --- Fields each entity type has, in order -----------------------------------

FIELDS = {
    "person": ["first_name", "middle_name", "last_name", "address_line_1", "address_line_2",
               "city", "postal_code", "state", "country", "country_iso",
               "email", "phone", "drivers_license_number"],
    "organization": ["organization_name", "address_line_1", "address_line_2",
                     "city", "postal_code", "state", "country", "country_iso",
                     "email", "phone", "tax_id", "duns_number"],
}

# What a clean value looks like in each field (from field_intent.yaml,
# clean_dataset_spec.md and the sponsor's Q&A).
FIELD_GUIDE = """\
- first_name: the person's given name only.
- middle_name: a second given name. Often empty, and empty is normal.
- last_name: the person's family name.
- organization_name: a legal or trade company name (e.g. "Johnson-Greene", "Kaupas, Poška and Narušis").
- address_line_1: a street line, usually with a house/building number. A street with no number can be clean, but a line that looks like its number was cut off (e.g. ends in "Dpto." or "Apt." with nothing after it) is not.
- address_line_2: extra address detail (apartment, floor, building). Often empty, and empty is normal.
- city: a city, town or village name.
- postal_code: the postal or ZIP code in the country's format.
- state: a state, province or region. May be empty in countries that don't use one.
- country / country_iso: the country name and its 2-letter code.
- email: an email address. Plus-addressing (user+tag@domain) and shared mailboxes (info@...) are clean.
- phone: a phone number in E.164 format (starts with +, then digits).
- drivers_license_number: a driver's license number in that country's format.
- tax_id: a tax or VAT number. Compact, hyphenated and spaced formats are all clean.
- duns_number: exactly 9 digits."""


# --- Error types (the labels the scorer expects) ---------------------------------

def load_error_types():
    """Return {error_type: description} for every type the sponsor's dirt can add."""
    mapping = yaml.safe_load(open(DATASET / "taxonomy" / "dirt_label_to_types.yaml"))
    descriptions = yaml.safe_load(open(DATASET / "taxonomy" / "semantic_types.yaml"))["types"]

    used = set()
    for fields in mapping["contaminants"].values():
        for types in fields.values():
            used.update(types)
    return {t: descriptions[t]["description"] for t in sorted(used)}


ERROR_TYPES = load_error_types()


# --- Instructions ---------------------------------------------------------------

INSTRUCTIONS = """\
You check customer master-data records for data-quality errors.

You will get one record (a person or an organization) as JSON. Decide, for each \
field, whether its value is wrong for that field. Most fields in a record are clean, \
so only flag a field when you can say what is wrong with it. Use the whole record: \
some errors only show when you compare fields (for example, a first and last name \
that were swapped).

## What each field should contain
{field_guide}

## Error types
Label a flagged field with every type that applies. Most labels name the kind of \
content that is wrongly in the field: a family name in first_name is "family_name"; \
an email in organization_name is "email". A few labels describe damage instead: \
"corrupt_phone", "corrupt_email", "corrupt_tax", "incomplete_premise", and \
"unknown_content" for a field that was emptied because its value was moved into \
another field.

{error_types}

## Output
Return JSON with one key, "flagged": a list with one entry per wrong field. Each \
entry has "field" (the field name), "error_types" (a list of types from the list \
above) and "reason" (one short sentence). Leave clean fields out. If every field \
is clean, return {{"flagged": []}}.

## Examples
{examples}"""


# --- Worked examples ---------------------------------------------------------------
# Real records from the TRAIN split. The labels match gold.parquet; the
# reasons are written by hand. Never use val or test records here.

EXAMPLES = [
    ("CH-010264", [  # first and last name swapped
        ("first_name", ["family_name"], "'Bianchi' is a family name; it was swapped with the last name."),
        ("last_name", ["given_name"], "'Angelika' is a given name; it was swapped with the first name."),
        ("email", ["corrupt_email"], "Two @ signs, so not a valid email address."),
    ]),
    ("IE-017056", [  # middle name merged into first name
        ("first_name", ["additional_given_name"], "Contains two given names; 'Joanna' is the middle name."),
        ("middle_name", ["unknown_content"], "Empty because the middle name was moved into first_name."),
        ("phone", ["corrupt_phone", "locality"], "A city label, not a phone number."),
    ]),
    ("SE-012163", [  # placeholder
        ("first_name", ["placeholder_token"], "A single symbol, not a name."),
    ]),
    ("AT-015628", [  # house number missing
        ("address_line_1", ["incomplete_premise"], "Street name only; Austrian street lines normally carry a house number."),
        ("duns_number", ["placeholder_token"], "A single character, not a 9-digit DUNS number."),
    ]),
    ("DE-001781", [  # a person's name used as the company name
        ("organization_name", ["family_name", "given_name"], "A person's full name, not a company name."),
    ]),
    ("SI-030648", [
        ("organization_name", ["email"], "An email address, not a company name."),
        ("tax_id", ["corrupt_tax"], "Too short to be a Slovenian VAT number."),
    ]),
    ("HR-028379", [
        ("first_name", ["job_title"], "'Direktor' is a job title, not a name."),
        ("phone", ["url"], "A LinkedIn URL, not a phone number."),
    ]),
    ("CA-004647", [  # status word
        ("organization_name", ["status_token"], "'Customer' is a CRM status word, not a company name."),
    ]),
]


def record_to_json(row):
    """Turn one row of records.parquet into the JSON the LLM sees."""
    entity = row["entity_type"]
    record = {"entity_type": entity, "country_iso": row["country_iso"]}
    record["fields"] = {field: row[field] for field in FIELDS[entity]}
    return json.dumps(record, ensure_ascii=False)


def build_examples(records):
    """Format the worked examples as 'Record' / 'Answer' pairs."""
    blocks = []
    for record_id, flagged in EXAMPLES:
        row = records.loc[records["record_id"] == record_id].iloc[0]
        assert row["split"] == "train", f"{record_id} is not a train record"
        answer = {"flagged": [{"field": f, "error_types": t, "reason": r} for f, t, r in flagged]}
        blocks.append(f"Record:\n{record_to_json(row)}\nAnswer:\n{json.dumps(answer, ensure_ascii=False)}")
    return "\n\n".join(blocks)


def build_instructions(records):
    """The fixed part of the prompt, identical for every record."""
    error_types = "\n".join(f"- {name}: {desc}" for name, desc in ERROR_TYPES.items())
    return INSTRUCTIONS.format(
        field_guide=FIELD_GUIDE,
        error_types=error_types,
        examples=build_examples(records),
    )


if __name__ == "__main__":
    records = pd.read_parquet(DATA / "records.parquet")
    instructions = build_instructions(records)

    # Show what one real request looks like: the instructions + one val record.
    sample = records[records["split"] == "val"].iloc[0]
    full = f"{instructions}\n\n=== RECORD TO CHECK ===\n{record_to_json(sample)}"

    (DATA / "llm_prompt.txt").write_text(full)
    print(f"{len(ERROR_TYPES)} error types, {len(EXAMPLES)} examples")
    print(f"Instructions: {len(instructions):,} characters (~{len(instructions) // 4:,} tokens)")
    print(f"Saved a full sample prompt to {DATA / 'llm_prompt.txt'}")
