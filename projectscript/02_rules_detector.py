"""Step 2: rules-based detector.

Looks at every cell and predicts which semantic types (from
taxonomy/semantic_types.yaml) don't belong in that field. For example,
"Pendiente" in first_name -> status_token, "city:Santa Fe" in phone -> corrupt_phone.
An empty prediction means the rules think the cell is fine.

Only uses detector inputs (data/cells.parquet), never the answer key.

Run from the Class folder:  .venv/bin/python party-test-data-v3/projectscript/02_rules_detector.py
"""

import re
from pathlib import Path

import pandas as pd
import phonenumbers
import yaml

HERE = Path(__file__).resolve().parent
DATASET = HERE.parent  # the party-test-data-v3 folder
DATA = HERE / "data"

# Turn off to see how the rules do without the sponsor's word lists
# (the same lists their generator used to create the dirt).
USE_SPONSOR_WORD_LISTS = True


# --- Word lists --------------------------------------------------------------

def load_word_lists():
    """Group the sponsor's placeholder lexicon words by what they mean."""
    lexicon = yaml.safe_load((DATASET / "placeholder_lexicon.yaml").read_text())
    groups = {
        "placeholder_token": ["unknown", "na", "no_name", "no_address", "tba", "no_vat"],
        "not_an_email": ["not_email"],
        "not_a_tax_id": ["not_tax"],
        "status_token": ["status"],
        "job_title": ["job", "honorific"],
        "organization_name_fragment": ["dept", "team"],
        "free_text_note": ["note"],
    }
    words = {label: set() for label in groups}
    for language in lexicon["languages"].values():
        for label, keys in groups.items():
            for key in keys:
                words[label].update(w.casefold() for w in language.get(key, []))
    return words


# Generic placeholders any data team would check for.
COMMON_PLACEHOLDERS = {"null", "none", "n/a", "na", "tbd", "tba", "unknown", "test", "phone-test"}

WORDS = load_word_lists() if USE_SPONSOR_WORD_LISTS else {}
PLACEHOLDERS = COMMON_PLACEHOLDERS | WORDS.get("placeholder_token", set())

COUNTRY_NAMES = {
    name.casefold() for name in pd.read_csv(DATASET / "countries.csv")["Country Name"]
}


# --- Patterns ------------------------------------------------------------------

EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_START = re.compile(r"\+\d{7,}")            # "+3861234567..." at the start
URL = re.compile(r"https?://|www\.", re.IGNORECASE)
HANDLE = re.compile(r"@\w+")                     # "@sales1234"
DATE = re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{4}")
TAX_LIKE = re.compile(r"[A-Z]{2}[\s-]?\d[\d\s-]{5,}[A-Za-z]?")  # "PT191965750", "BE0 026 441 210"
STREET = re.compile(r"\w+.*\s\d+|\d+\s\w+")     # a word and a house number
PUNCTUATION_ONLY = re.compile(r"[\W_]*")         # ".", "-", "?", "*", ""

NAME_FIELDS = {"first_name", "middle_name", "last_name"}
TEXT_FIELDS = NAME_FIELDS | {"organization_name", "city"}


def is_valid_phone(value, country):
    try:
        return phonenumbers.is_valid_number(phonenumbers.parse(value, country))
    except phonenumbers.NumberParseException:
        return False


# --- The detector ----------------------------------------------------------------

def detect(value, field, country):
    """Return the set of types in this cell that don't belong in its field."""
    v = value.strip()
    low = v.casefold()
    found = set()

    # Blanks. Middle name and address line 2 are optional, so blanks there are fine.
    if v == "":
        if field == "last_name":
            found.add("unknown_content")     # names merged into first_name
        elif field in {"first_name", "organization_name", "email", "phone", "tax_id"}:
            found.add("placeholder_token")
        return found

    # Placeholders: known words, punctuation only, or a single character.
    if low in PLACEHOLDERS or PUNCTUATION_ONLY.fullmatch(v) or (len(v) == 1 and field != "country_iso"):
        found.add("placeholder_token")

    # Values that belong in a different field.
    if field != "email" and EMAIL.fullmatch(v):
        found.add("email")
    if field != "phone" and PHONE_START.match(v):
        found.add("phone_e164")
    if URL.search(v):
        found.add("url")
    if HANDLE.fullmatch(v.split()[0]) and field != "email":
        found.add("social_handle")
    if DATE.fullmatch(v):
        found.add("date_like")
    if field in {"city", "address_line_1", "address_line_2"} and re.fullmatch(r"\d{9}", v):
        found.add("identifier_duns")
    if field == "address_line_1" and TAX_LIKE.fullmatch(v):
        found.add("identifier_tax")
    if field in NAME_FIELDS | {"organization_name"} and low in COUNTRY_NAMES:
        found.add("country_name")

    # Words from the sponsor's lists (status words, job titles, departments, notes).
    # Only in free-text fields: "HR" is a country code but also "Hr" (German "Mr").
    if field in TEXT_FIELDS | {"address_line_1", "address_line_2"}:
        for label in ["status_token", "job_title", "organization_name_fragment", "free_text_note"]:
            if low in WORDS.get(label, set()):
                found.add(label)

    # Person name fields: names never contain digits or "/".
    if field in NAME_FIELDS and not found:
        digits_only = re.fullmatch(r"[\d\s-]+", v)
        if digits_only and len(re.sub(r"\D", "", v)) <= 3 or re.fullmatch(r"(\d)\1+", v):
            found.add("numeric_token")       # "42", "999", "0000"
        elif digits_only or re.fullmatch(r"[A-Z]{0,2}[\d\s-]{4,}", v):
            found.add("postal_code")         # "49872", "337 06", "H-9556"
        elif STREET.search(v) and any(c.isdigit() for c in v):
            found.add("street_address")      # "Kellnerstraße 07"
        if "/" in v:
            found.add("mixed_delimiter_name")

    # Field-specific checks: is the value valid for its own field?
    if field == "email":
        if v.endswith(".invalid") or "@invalid." in v:
            found.add("placeholder_token")   # reserved test domains
        elif not EMAIL.fullmatch(v) and "placeholder_token" not in found:
            found.add("corrupt_email")
    if field == "phone" and not is_valid_phone(v, country):
        found.add("corrupt_phone")
    if field == "tax_id" and "placeholder_token" not in found:
        if low in WORDS.get("not_a_tax_id", set()) or len(re.sub(r"\D", "", v)) < 5:
            found.add("corrupt_tax")
    if field == "drivers_license_number" and re.match(r"[^\W\d_]{3,}.*-", v):
        found.add("region_code")             # "Salzburg-H46PQ20IWDK"

    return found


# --- Run on every cell ---------------------------------------------------------

def main():
    cells = pd.read_parquet(DATA / "cells.parquet")

    cells["predicted_types"] = [
        sorted(detect(v, f, c))
        for v, f, c in zip(cells["raw_value"], cells["field"], cells["country_iso"])
    ]
    cells["is_flagged"] = cells["predicted_types"].map(len) > 0

    out = cells[["record_id", "entity_type", "field", "split", "predicted_types", "is_flagged"]]
    out.to_parquet(DATA / "rules_predictions.parquet", index=False)
    print(f"Flagged {out['is_flagged'].sum():,} of {len(out):,} cells "
          f"({out['is_flagged'].mean():.1%}). Saved to {DATA / 'rules_predictions.parquet'}")


if __name__ == "__main__":
    main()
