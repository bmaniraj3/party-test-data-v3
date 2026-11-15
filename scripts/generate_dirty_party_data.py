"""
Generate dirty_person.csv and dirty_organization.csv from clean_*.csv splits (dataset folder v3).
Reads dirt_distribution.csv for sampling weights; writes actual_count back.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

from strip_premise import strip_premise_line
from dirt_lexicon import (
    FAKE_PHONE_REPEAT,
    FAKE_PHONE_SHORT,
    MALFORMED_EMAILS,
    NUMERIC_TOKENS,
    TEST_EMAILS,
    WEBSITES,
    DirtLexicon,
    load_lexicon,
)
from faker import Faker


SEED = 481
DATASET_VERSION = "v3"
PRIMARY_EVENT_PROB = 0.95
SECONDARY_EVENT_PROB = 0.25
MUTATION_ATTEMPTS = 12
FAMILY_MISPLACEMENT_PROB = 0.6
# Matches clean v1: 50% person / 50% org per country, 1,000 rows per country total.
EXPECTED_DIRTY_PERSON_ROWS = 17_500
EXPECTED_DIRTY_ORG_ROWS = 17_500
EXPECTED_DIRTY_ROWS_PER_COUNTRY = 500


def _event(
    dirt_label_id: str,
    dirt_family: str,
    fields_affected: List[str],
    application_mode: str,
    detail: str,
) -> Dict[str, Any]:
    return {
        "dirt_label_id": dirt_label_id,
        "dirt_family": dirt_family,
        "fields_affected": fields_affected,
        "application_mode": application_mode,
        "detail": detail,
    }


def _split_email(email: str) -> Tuple[str, str]:
    if "@" not in email:
        return email, "example.com"
    local, _, domain = email.partition("@")
    return local, domain


def _weighted_choice(rows: List[Dict[str, str]], rng: random.Random) -> Dict[str, str]:
    weights = [float(r["sampling_weight"]) for r in rows]
    total = sum(weights)
    if total <= 0:
        return rows[0]
    x = rng.random() * total
    acc = 0.0
    for r, w in zip(rows, weights):
        acc += w
        if x < acc:
            return r
    return rows[-1]


def _pick_family(rng: random.Random) -> str:
    return "misplacement" if rng.random() < FAMILY_MISPLACEMENT_PROB else "placeholder"


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


def merge_record(
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


def build_person_and_org_lists(
    by_file: Dict[str, Dict[Tuple[str, str], Dict[str, str]]],
) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
    all_keys = set(by_file["pn"].keys()) | set(by_file["on"].keys())
    persons: List[Dict[str, str]] = []
    orgs: List[Dict[str, str]] = []
    for key in sorted(all_keys):
        pn = by_file["pn"].get(key, {})
        on = by_file["on"].get(key, {})
        if (pn.get("first_name") or "").strip():
            persons.append(merge_record(key, by_file))
        if (on.get("organization_name") or "").strip():
            orgs.append(merge_record(key, by_file))
    return persons, orgs


_faker_cache: Dict[str, Faker] = {}


def _faker_for_iso(iso: str) -> Faker:
    loc = {
        "DE": "de_DE",
        "AT": "de_AT",
        "CH": "de_CH",
        "FR": "fr_FR",
        "IT": "it_IT",
        "ES": "es_ES",
        "MX": "es_MX",
        "AR": "es_AR",
        "NL": "nl_NL",
        "PL": "pl_PL",
        "SE": "sv_SE",
        "BR": "pt_BR",
        "PT": "pt_PT",
        "HR": "hr_HR",
        "RS": "hr_HR",
    }.get(iso, "en_US")
    if loc not in _faker_cache:
        try:
            _faker_cache[loc] = Faker(loc)
        except Exception:
            _faker_cache[loc] = Faker("en_US")
    return _faker_cache[loc]


def make_handlers(lex: DirtLexicon) -> Dict[str, Callable[[Dict[str, str], random.Random], Dict[str, Any]]]:
    h: Dict[str, Callable[[Dict[str, str], random.Random], Dict[str, Any]]] = {}

    def iso_of(r: Dict[str, str]) -> str:
        return (r.get("country_iso") or "US").strip() or "US"

    def reg(lid: str, fn: Callable[[Dict[str, str], random.Random], Dict[str, Any]]) -> None:
        h[lid] = fn

    # --- Person misplacement ---
    def mis_name_swap_fl(r, rng):
        a, b = r["first_name"], r["last_name"]
        r["first_name"], r["last_name"] = b, a
        return _event("MIS_NAME_SWAP_FL", "misplacement", ["first_name", "last_name"], "replace", "swapped")

    def mis_middle_to_first(r, rng):
        mid = r.get("middle_name", "")
        r["first_name"] = f"{r['first_name']} {mid}".strip()
        r["middle_name"] = ""
        return _event("MIS_NAME_MIDDLE_TO_FIRST", "misplacement", ["first_name", "middle_name"], "replace", "middle folded")

    def mis_merge_all_first(r, rng):
        r["first_name"] = f"{r['first_name']} {r['middle_name']} {r['last_name']}".strip()
        r["middle_name"] = ""
        r["last_name"] = ""
        return _event("MIS_NAME_MERGE_ALL_FIRST", "misplacement", ["first_name", "middle_name", "last_name"], "replace", "merged")

    def mis_split_wrong(r, rng):
        ln = r["last_name"]
        if len(ln) > 2:
            r["first_name"] = f"{r['first_name']}{ln[:2]}"
            r["last_name"] = ln[2:]
        return _event("MIS_NAME_SPLIT_WRONG", "misplacement", ["first_name", "last_name"], "replace", "split")

    def mis_hyphen(r, rng):
        r["last_name"] = f"{r['last_name']}-{r['first_name'][:1]}"
        r["first_name"] = r["first_name"][1:] if len(r["first_name"]) > 1 else r["first_name"]
        return _event("MIS_NAME_HYPHEN_INCONSISTENT", "misplacement", ["first_name", "last_name"], "replace", "hyphen")

    def mis_email_first(r, rng):
        r["first_name"] = r["email"]
        return _event("MIS_EMAIL_IN_FIRST", "misplacement", ["first_name"], "replace", "email copied")

    def mis_email_last(r, rng):
        r["last_name"] = r["email"]
        return _event("MIS_EMAIL_IN_LAST", "misplacement", ["last_name"], "replace", "email copied")

    def mis_phone_first(r, rng):
        r["first_name"] = r["phone"]
        return _event("MIS_PHONE_IN_FIRST", "misplacement", ["first_name"], "replace", "phone copied")

    def mis_addr_first(r, rng):
        r["first_name"] = r["address_line_1"]
        return _event("MIS_ADDR_LINE_IN_FIRST", "misplacement", ["first_name"], "replace", "address copied")

    def mis_postal_first(r, rng):
        r["first_name"] = r["postal_code"]
        return _event("MIS_POSTAL_IN_FIRST", "misplacement", ["first_name"], "replace", "postal copied")

    def mis_title_first(r, rng):
        r["first_name"] = lex.pick(iso_of(r), "honorific", rng)
        return _event("MIS_TITLE_IN_FIRST", "misplacement", ["first_name"], "replace", "title")

    def mis_dob_addr2(r, rng):
        y = rng.randint(1950, 2010)
        m = rng.randint(1, 12)
        d = rng.randint(1, 28)
        r["address_line_2"] = rng.choice(
            [f"{y:04d}-{m:02d}-{d:02d}", f"{d:02d}/{m:02d}/{y:04d}", f"{m:02d}-{d:02d}-{y:04d}"]
        )
        return _event("MIS_DOB_IN_ADDRESS2", "misplacement", ["address_line_2"], "replace", "date-like")

    def mis_job_first(r, rng):
        r["first_name"] = lex.pick(iso_of(r), "job", rng)
        return _event("MIS_JOB_IN_FIRST", "misplacement", ["first_name"], "replace", "role token")

    def mis_status_first(r, rng):
        r["first_name"] = lex.pick(iso_of(r), "status", rng)
        return _event("MIS_STATUS_IN_FIRST", "misplacement", ["first_name"], "replace", "status")

    def mis_twitter_first(r, rng):
        r["first_name"] = f"@{rng.choice(['ops', 'sales', 'user', 'acct'])}{rng.randint(10, 9999)}"
        return _event("MIS_TWITTER_IN_FIRST", "misplacement", ["first_name"], "replace", "handle")

    def mis_li_phone(r, rng):
        slug = rng.choice(["example", "jsmith", "acme-buyer", "ops-team"])
        r["phone"] = f"https://www.linkedin.com/in/{slug}{rng.randint(1, 99)}"
        return _event("MIS_LINKEDIN_IN_PHONE", "misplacement", ["phone"], "replace", "url")

    def mis_num_first(r, rng):
        r["first_name"] = rng.choice(NUMERIC_TOKENS)
        return _event("MIS_NUMERIC_FIRST", "misplacement", ["first_name"], "replace", "numeric")

    def mis_fake_short(r, rng):
        r["phone"] = rng.choice(FAKE_PHONE_SHORT)
        return _event("MIS_FAKE_PHONE_SHORT", "misplacement", ["phone"], "replace", "fake")

    def mis_fake_rep(r, rng):
        r["phone"] = rng.choice(FAKE_PHONE_REPEAT)
        return _event("MIS_FAKE_PHONE_REPEAT", "misplacement", ["phone"], "replace", "fake")

    def mis_phone_alpha(r, rng):
        r["phone"] = lex.pick(iso_of(r), "not_email", rng).replace("email", "phone")
        return _event("MIS_PHONE_NONNUMERIC", "misplacement", ["phone"], "replace", "alpha")

    def mis_city_phone(r, rng):
        r["phone"] = f"city:{r['city']}"
        return _event("MIS_CITY_IN_PHONE", "misplacement", ["phone"], "replace", "geo bleed")

    def mis_state_dl(r, rng):
        r["drivers_license_number"] = f"{r['state']}-{r['drivers_license_number']}"
        return _event("MIS_STATE_IN_DL", "misplacement", ["drivers_license_number"], "replace", "state")

    def mis_org_token_first(r, rng):
        fake = _faker_for_iso(iso_of(r))
        try:
            r["first_name"] = str(fake.company()).split()[0][:24]
        except Exception:
            r["first_name"] = "Acme"
        return _event("MIS_ORG_TOKEN_IN_FIRST", "misplacement", ["first_name"], "replace", "org token")

    def mis_note_addr(r, rng):
        r["address_line_1"] = lex.pick(iso_of(r), "note", rng)
        return _event("MIS_NOTE_IN_ADDRESS1", "misplacement", ["address_line_1"], "replace", "note")

    def mis_strip_premise(r, rng):
        affected: List[str] = []
        for fld in ("address_line_1", "address_line_2"):
            old = r.get(fld) or ""
            new = strip_premise_line(old)
            if new != old:
                r[fld] = new
                affected.append(fld)
        return _event(
            "MIS_ADDR_STRIP_PREMISE",
            "misplacement",
            affected,
            "replace",
            "strip premise",
        )

    def mis_comp_first(r, rng):
        r["first_name"] = f"{r['first_name']}/{r['last_name'][:3]}"
        return _event("MIS_COMPOSITE_FIRST", "misplacement", ["first_name"], "replace", "delimiter")

    def mis_na_city(r, rng):
        r["city"] = lex.pick(iso_of(r), "na", rng, mix_global=True)
        return _event("MIS_NA_IN_CITY", "misplacement", ["city"], "replace", "na")

    def mis_invalid_email_no_at(r, rng):
        r["email"] = lex.pick(iso_of(r), "not_email", rng)
        return _event("MIS_INVALID_EMAIL_NO_AT", "misplacement", ["email"], "replace", "no at")

    def mis_invalid_email_malformed(r, rng):
        r["email"] = rng.choice(MALFORMED_EMAILS)
        return _event("MIS_INVALID_EMAIL_MALFORMED", "misplacement", ["email"], "replace", "malformed")

    reg("MIS_NAME_SWAP_FL", mis_name_swap_fl)
    reg("MIS_NAME_MIDDLE_TO_FIRST", mis_middle_to_first)
    reg("MIS_NAME_MERGE_ALL_FIRST", mis_merge_all_first)
    reg("MIS_NAME_SPLIT_WRONG", mis_split_wrong)
    reg("MIS_NAME_HYPHEN_INCONSISTENT", mis_hyphen)
    reg("MIS_EMAIL_IN_FIRST", mis_email_first)
    reg("MIS_EMAIL_IN_LAST", mis_email_last)
    reg("MIS_PHONE_IN_FIRST", mis_phone_first)
    reg("MIS_ADDR_LINE_IN_FIRST", mis_addr_first)
    reg("MIS_POSTAL_IN_FIRST", mis_postal_first)
    reg("MIS_TITLE_IN_FIRST", mis_title_first)
    reg("MIS_DOB_IN_ADDRESS2", mis_dob_addr2)
    reg("MIS_JOB_IN_FIRST", mis_job_first)
    reg("MIS_STATUS_IN_FIRST", mis_status_first)
    reg("MIS_TWITTER_IN_FIRST", mis_twitter_first)
    reg("MIS_LINKEDIN_IN_PHONE", mis_li_phone)
    reg("MIS_NUMERIC_FIRST", mis_num_first)
    reg("MIS_FAKE_PHONE_SHORT", mis_fake_short)
    reg("MIS_FAKE_PHONE_REPEAT", mis_fake_rep)
    reg("MIS_PHONE_NONNUMERIC", mis_phone_alpha)
    reg("MIS_CITY_IN_PHONE", mis_city_phone)
    reg("MIS_STATE_IN_DL", mis_state_dl)
    reg("MIS_ORG_TOKEN_IN_FIRST", mis_org_token_first)
    reg("MIS_NOTE_IN_ADDRESS1", mis_note_addr)
    reg("MIS_ADDR_STRIP_PREMISE", mis_strip_premise)
    reg("MIS_COMPOSITE_FIRST", mis_comp_first)
    reg("MIS_NA_IN_CITY", mis_na_city)
    reg("MIS_INVALID_EMAIL_NO_AT", mis_invalid_email_no_at)
    reg("MIS_INVALID_EMAIL_MALFORMED", mis_invalid_email_malformed)

    # --- Person placeholder ---
    def ph_unknown_f(r, rng):
        r["first_name"] = lex.pick(iso_of(r), "unknown", rng, mix_global=True)
        return _event("PH_UNKNOWN_REPLACE_FIRST", "placeholder", ["first_name"], "replace", "unknown")

    def ph_tba(r, rng):
        r["last_name"] = lex.pick(iso_of(r), "tba", rng)
        return _event("PH_TBA_SUFFIX_LAST", "placeholder", ["last_name"], "replace", "tba token")

    def ph_noname(r, rng):
        r["first_name"] = lex.pick(iso_of(r), "no_name", rng)
        return _event("PH_NO_NAME_REPLACE_FIRST", "placeholder", ["first_name"], "replace", "no name")

    def ph_test_email(r, rng):
        r["email"] = rng.choice(TEST_EMAILS)
        return _event("PH_TEST_PREFIX_EMAIL", "placeholder", ["email"], "replace", "test placeholder")

    def ph_noaddr(r, rng):
        r["address_line_1"] = lex.pick(iso_of(r), "no_address", rng)
        return _event("PH_NO_ADDRESS_REPLACE_LINE1", "placeholder", ["address_line_1"], "replace", "no address")

    def ph_nulls(r, rng):
        r["first_name"] = rng.choice(["NULL", "null", "Nil"])
        return _event("PH_NULL_STRING_FIRST", "placeholder", ["first_name"], "replace", "null string")

    def ph_dash(r, rng):
        r["first_name"] = "-"
        return _event("PH_DASH_REPLACE_FIRST", "placeholder", ["first_name"], "replace", "dash")

    def ph_dot(r, rng):
        r["first_name"] = "."
        return _event("PH_DOT_REPLACE_FIRST", "placeholder", ["first_name"], "replace", "dot")

    def ph_single(r, rng):
        r["first_name"] = rng.choice(["?", "#", "*"])
        return _event("PH_SINGLE_CHAR_FIRST", "placeholder", ["first_name"], "replace", "single")

    def ph_space(r, rng):
        r["first_name"] = " "
        return _event("PH_SPACE_ONLY_FIRST", "placeholder", ["first_name"], "replace", "space")

    def ph_na_email(r, rng):
        r["email"] = lex.pick(iso_of(r), "na", rng, mix_global=True)
        return _event("PH_NA_REPLACE_EMAIL", "placeholder", ["email"], "replace", "na")

    def ph_null_email(r, rng):
        r["email"] = "NULL"
        return _event("PH_NULL_REPLACE_EMAIL", "placeholder", ["email"], "replace", "null")

    def ph_unknown_email(r, rng):
        r["email"] = lex.pick(iso_of(r), "unknown", rng)
        return _event("PH_UNKNOWN_REPLACE_EMAIL", "placeholder", ["email"], "replace", "unknown")

    reg("PH_UNKNOWN_REPLACE_FIRST", ph_unknown_f)
    reg("PH_TBA_SUFFIX_LAST", ph_tba)
    reg("PH_NO_NAME_REPLACE_FIRST", ph_noname)
    reg("PH_TEST_PREFIX_EMAIL", ph_test_email)
    reg("PH_NO_ADDRESS_REPLACE_LINE1", ph_noaddr)
    reg("PH_NULL_STRING_FIRST", ph_nulls)
    reg("PH_DASH_REPLACE_FIRST", ph_dash)
    reg("PH_DOT_REPLACE_FIRST", ph_dot)
    reg("PH_SINGLE_CHAR_FIRST", ph_single)
    reg("PH_SPACE_ONLY_FIRST", ph_space)
    reg("PH_NA_REPLACE_EMAIL", ph_na_email)
    reg("PH_NULL_REPLACE_EMAIL", ph_null_email)
    reg("PH_UNKNOWN_REPLACE_EMAIL", ph_unknown_email)

    # --- Org misplacement ---
    def om_email_name(r, rng):
        r["organization_name"] = r["email"]
        return _event("MIS_ORG_EMAIL_AS_NAME", "misplacement", ["organization_name"], "replace", "email")

    def om_phone_name(r, rng):
        r["organization_name"] = r["phone"]
        return _event("MIS_ORG_PHONE_AS_NAME", "misplacement", ["organization_name"], "replace", "phone")

    def om_contact_name(r, rng):
        fake = _faker_for_iso(iso_of(r))
        try:
            r["organization_name"] = f"{fake.first_name()} {fake.last_name()}"
        except Exception:
            r["organization_name"] = "Jane Doe"
        return _event("MIS_ORG_CONTACT_AS_NAME", "misplacement", ["organization_name"], "replace", "person")

    def om_tax_addr(r, rng):
        r["address_line_1"] = r["tax_id"]
        return _event("MIS_ORG_TAX_IN_ADDRESS1", "misplacement", ["address_line_1"], "replace", "tax")

    def om_duns_city(r, rng):
        r["city"] = r["duns_number"]
        return _event("MIS_ORG_DUNS_IN_CITY", "misplacement", ["city"], "replace", "duns")

    def om_country_name(r, rng):
        r["organization_name"] = r["country"]
        return _event("MIS_ORG_COUNTRY_IN_NAME", "misplacement", ["organization_name"], "replace", "country")

    def om_postal_name(r, rng):
        r["organization_name"] = r["postal_code"]
        return _event("MIS_ORG_POSTAL_IN_NAME", "misplacement", ["organization_name"], "replace", "postal")

    def om_web_addr(r, rng):
        r["address_line_1"] = rng.choice(WEBSITES)
        return _event("MIS_ORG_WEBSITE_AS_ADDRESS", "misplacement", ["address_line_1"], "replace", "url")

    def om_dept(r, rng):
        r["address_line_2"] = lex.pick(iso_of(r), "dept", rng)
        return _event("MIS_ORG_DEPT_IN_ADDRESS2", "misplacement", ["address_line_2"], "replace", "dept")

    def om_team(r, rng):
        r["organization_name"] = lex.pick(iso_of(r), "team", rng)
        return _event("MIS_ORG_TEAM_AS_NAME", "misplacement", ["organization_name"], "replace", "team")

    def om_stat(r, rng):
        r["organization_name"] = lex.pick(iso_of(r), "status", rng)
        return _event("MIS_ORG_STATUS_IN_NAME", "misplacement", ["organization_name"], "replace", "status")

    def om_comp(r, rng):
        r["organization_name"] = f"{r['organization_name']} / Beta"
        return _event("MIS_COMPOSITE_ORG_NAME", "misplacement", ["organization_name"], "replace", "delimiter")

    def om_job_name(r, rng):
        r["organization_name"] = lex.pick(iso_of(r), "job", rng)
        return _event("MIS_JOB_IN_ORG_NAME", "misplacement", ["organization_name"], "replace", "job title")

    def om_invalid_tax_not(r, rng):
        r["tax_id"] = lex.pick(iso_of(r), "not_tax", rng)
        return _event("MIS_INVALID_TAX_NOT_ID", "misplacement", ["tax_id"], "replace", "not tax")

    def om_invalid_tax_mal(r, rng):
        r["tax_id"] = rng.choice(["12", "ABC", "XX-1", iso_of(r)])
        return _event("MIS_INVALID_TAX_MALFORMED", "misplacement", ["tax_id"], "replace", "malformed")

    reg("MIS_ORG_EMAIL_AS_NAME", om_email_name)
    reg("MIS_ORG_PHONE_AS_NAME", om_phone_name)
    reg("MIS_ORG_CONTACT_AS_NAME", om_contact_name)
    reg("MIS_ORG_TAX_IN_ADDRESS1", om_tax_addr)
    reg("MIS_ORG_DUNS_IN_CITY", om_duns_city)
    reg("MIS_ORG_COUNTRY_IN_NAME", om_country_name)
    reg("MIS_ORG_POSTAL_IN_NAME", om_postal_name)
    reg("MIS_ORG_WEBSITE_AS_ADDRESS", om_web_addr)
    reg("MIS_ORG_DEPT_IN_ADDRESS2", om_dept)
    reg("MIS_ORG_TEAM_AS_NAME", om_team)
    reg("MIS_ORG_STATUS_IN_NAME", om_stat)
    reg("MIS_COMPOSITE_ORG_NAME", om_comp)
    reg("MIS_JOB_IN_ORG_NAME", om_job_name)
    reg("MIS_INVALID_TAX_NOT_ID", om_invalid_tax_not)
    reg("MIS_INVALID_TAX_MALFORMED", om_invalid_tax_mal)
    # shared org
    reg("MIS_NOTE_IN_ADDRESS1", mis_note_addr)
    reg("MIS_ADDR_STRIP_PREMISE", mis_strip_premise)
    reg("MIS_NA_IN_CITY", mis_na_city)
    reg("MIS_INVALID_EMAIL_NO_AT", mis_invalid_email_no_at)
    reg("MIS_INVALID_EMAIL_MALFORMED", mis_invalid_email_malformed)
    reg("PH_TEST_PREFIX_EMAIL", ph_test_email)
    reg("PH_NA_REPLACE_EMAIL", ph_na_email)
    reg("PH_NULL_REPLACE_EMAIL", ph_null_email)
    reg("PH_UNKNOWN_REPLACE_EMAIL", ph_unknown_email)

    # --- Org placeholder ---
    def op_unk(r, rng):
        r["organization_name"] = lex.pick(iso_of(r), "unknown", rng, mix_global=True)
        return _event("PH_UNKNOWN_REPLACE_ORG", "placeholder", ["organization_name"], "replace", "unknown")

    def op_tbd(r, rng):
        r["organization_name"] = lex.pick(iso_of(r), "tba", rng)
        return _event("PH_TBD_REPLACE_ORG", "placeholder", ["organization_name"], "replace", "tbd")

    def op_nac(r, rng):
        r["city"] = lex.pick(iso_of(r), "na", rng, mix_global=True)
        return _event("PH_NA_REPLACE_CITY", "placeholder", ["city"], "replace", "na")

    def op_tph(r, rng):
        r["phone"] = rng.choice(["test", "TEST", "phone-test"])
        return _event("PH_TEST_REPLACE_PHONE", "placeholder", ["phone"], "replace", "test")

    def op_taxdot(r, rng):
        r["tax_id"] = "."
        return _event("PH_DOT_REPLACE_TAX", "placeholder", ["tax_id"], "replace", "dot")

    def op_duns0(r, rng):
        r["duns_number"] = "0"
        return _event("PH_SINGLE_CHAR_DUNS", "placeholder", ["duns_number"], "replace", "single")

    def op_na_tax(r, rng):
        r["tax_id"] = lex.pick(iso_of(r), "na", rng, mix_global=True)
        return _event("PH_NA_REPLACE_TAX", "placeholder", ["tax_id"], "replace", "na")

    def op_null_tax(r, rng):
        r["tax_id"] = "NULL"
        return _event("PH_NULL_REPLACE_TAX", "placeholder", ["tax_id"], "replace", "null")

    def op_novat_tax(r, rng):
        r["tax_id"] = lex.pick(iso_of(r), "no_vat", rng)
        return _event("PH_NOVAT_REPLACE_TAX", "placeholder", ["tax_id"], "replace", "no vat")

    reg("PH_UNKNOWN_REPLACE_ORG", op_unk)
    reg("PH_TBD_REPLACE_ORG", op_tbd)
    reg("PH_NA_REPLACE_CITY", op_nac)
    reg("PH_TEST_REPLACE_PHONE", op_tph)
    reg("PH_DOT_REPLACE_TAX", op_taxdot)
    reg("PH_SINGLE_CHAR_DUNS", op_duns0)
    reg("PH_NA_REPLACE_TAX", op_na_tax)
    reg("PH_NULL_REPLACE_TAX", op_null_tax)
    reg("PH_NOVAT_REPLACE_TAX", op_novat_tax)

    return h


def _validate_replace_only_handlers(
    handlers: Dict[str, Callable[[Dict[str, str], random.Random], Dict[str, Any]]],
    rng: random.Random,
) -> None:
    """Smoke each handler on a minimal row; every event must use application_mode replace."""
    sample: Dict[str, str] = {
        "record_id": "TEST-001",
        "country_iso": "US",
        "country": "United States",
        "first_name": "Alex",
        "middle_name": "Taylor",
        "last_name": "Smith",
        "organization_name": "Acme Corp",
        "address_line_1": "123 Main St",
        "address_line_2": "Suite 1",
        "city": "Boston",
        "postal_code": "02108",
        "state": "MA",
        "email": "alex@example.com",
        "phone": "+15551234567",
        "drivers_license_number": "S1234567",
        "tax_id": "12-3456789",
        "duns_number": "123456789",
    }
    for lid, fn in handlers.items():
        row = dict(sample)
        ev = fn(row, rng)
        mode = ev.get("application_mode")
        if mode != "replace":
            raise ValueError(f"Handler {lid} returned application_mode={mode!r}; dirty_v2 requires replace")


def _validate_dirty_output_replace_only(rows: List[Dict[str, str]]) -> None:
    bad: List[str] = []
    for row in rows:
        raw = row.get("dirt_events_json") or "[]"
        try:
            events = json.loads(raw)
        except json.JSONDecodeError as e:
            bad.append(f"{row.get('record_id')}: invalid JSON ({e})")
            continue
        for ev in events:
            mode = ev.get("application_mode")
            if mode != "replace":
                bad.append(
                    f"{row.get('record_id')}: {ev.get('dirt_label_id')} has application_mode={mode!r}"
                )
    if bad:
        raise ValueError(
            "dirty_v2 replace-only validation failed:\n" + "\n".join(bad[:20])
            + (f"\n... and {len(bad) - 20} more" if len(bad) > 20 else "")
        )


def load_distribution(path: Path) -> List[Dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def sample_row_from_distribution(
    dist: List[Dict[str, str]],
    entity_type: str,
    country_iso: str,
    rng: random.Random,
) -> Tuple[Dict[str, str], str]:
    family = _pick_family(rng)
    candidates = [
        r
        for r in dist
        if r["dataset_version"] == DATASET_VERSION
        and r["entity_type"] == entity_type
        and r["dirt_family"] == family
        and (r["country_iso"] == country_iso or r["country_iso"] == "ALL")
    ]
    if not candidates:
        candidates = [
            r
            for r in dist
            if r["dataset_version"] == DATASET_VERSION
            and r["entity_type"] == entity_type
            and r["dirt_family"] == family
            and r["country_iso"] == "ALL"
        ]
    chosen = _weighted_choice(candidates, rng)
    return chosen, family


def apply_dirt(
    row: Dict[str, str],
    drow: Dict[str, str],
    rng: random.Random,
    handlers: Dict[str, Callable[..., Dict[str, Any]]],
) -> Dict[str, Any]:
    lid = drow["dirt_label_id"]
    if lid not in handlers:
        raise KeyError(f"No handler for {lid}")
    ev = handlers[lid](row, rng)
    if ev["dirt_label_id"] != lid:
        ev["dirt_label_id"] = lid
    return ev


def _try_mutating_apply(
    row: Dict[str, str],
    drow: Dict[str, str],
    rng: random.Random,
    handlers: Dict[str, Callable[..., Dict[str, Any]]],
) -> Dict[str, Any] | None:
    before = dict(row)
    ev = apply_dirt(row, drow, rng, handlers)
    if dict(row) != before:
        return ev
    row.clear()
    row.update(before)
    return None


def _fallback_mutate(
    row: Dict[str, str],
    entity_type: str,
    rng: random.Random,
    handlers: Dict[str, Callable[..., Dict[str, Any]]],
) -> Dict[str, Any]:
    if entity_type == "person":
        lids = ("PH_DOT_REPLACE_FIRST", "PH_DASH_REPLACE_FIRST", "PH_SINGLE_CHAR_FIRST")
    else:
        lids = ("PH_NA_REPLACE_CITY", "PH_TBD_REPLACE_ORG", "PH_DOT_REPLACE_TAX")
    for lid in lids:
        ev = _try_mutating_apply(
            row,
            {"dirt_label_id": lid, "dirt_family": "placeholder"},
            rng,
            handlers,
        )
        if ev is not None:
            ev["detail"] = "fallback"
            return ev
    raise RuntimeError(f"{row.get('record_id')}: could not apply a mutating dirt fallback")


def process_entity_rows(
    rows: List[Dict[str, str]],
    entity_type: str,
    dist: List[Dict[str, str]],
    rng: random.Random,
    handlers: Dict[str, Callable[..., Dict[str, Any]]],
) -> Tuple[List[Dict[str, str]], Counter]:
    out: List[Dict[str, str]] = []
    counts: Counter = Counter()
    for base in rows:
        row = dict(base)
        events: List[Dict[str, Any]] = []
        labels: List[str] = []

        def add_event() -> None:
            ev: Dict[str, Any] | None = None
            for _ in range(MUTATION_ATTEMPTS):
                drow, _fam_guess = sample_row_from_distribution(
                    dist, entity_type, row["country_iso"], rng
                )
                ev = _try_mutating_apply(row, drow, rng, handlers)
                if ev is not None:
                    break
            if ev is None:
                ev = _fallback_mutate(row, entity_type, rng, handlers)
            events.append(ev)
            labels.append(ev["dirt_label_id"])
            counts[ev["dirt_label_id"]] += 1

        if rng.random() < PRIMARY_EVENT_PROB:
            add_event()
        else:
            ev = _fallback_mutate(row, entity_type, rng, handlers)
            events.append(ev)
            labels.append(ev["dirt_label_id"])
            counts[ev["dirt_label_id"]] += 1

        if rng.random() < SECONDARY_EVENT_PROB:
            add_event()

        out_row = dict(row)
        out_row["dirt_label_ids"] = ";".join(labels)
        out_row["dirt_events_json"] = json.dumps(events, ensure_ascii=False)
        out.append(out_row)
    return out, counts


def write_dirty_csv(path: Path, rows: List[Dict[str, str]], fieldnames: List[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def update_distribution_actual_counts(
    dist_path: Path,
    dist_rows: List[Dict[str, str]],
    person_counts: Counter,
    org_counts: Counter,
) -> None:
    for r in dist_rows:
        if r["dataset_version"] != DATASET_VERSION:
            continue
        lid = r["dirt_label_id"]
        if r["entity_type"] == "person":
            r["actual_count"] = str(person_counts.get(lid, 0))
        else:
            r["actual_count"] = str(org_counts.get(lid, 0))

    fieldnames = list(dist_rows[0].keys())
    with dist_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(dist_rows)


def validate_counts(by_country: Counter, expected_per_country: int) -> None:
    for iso, c in by_country.items():
        if c != expected_per_country:
            raise ValueError(f"country {iso}: expected {expected_per_country} rows, got {c}")


def main() -> None:
    base = Path(__file__).resolve().parent.parent
    rng = random.Random(SEED)
    lex = load_lexicon(base)
    handlers = make_handlers(lex)

    by_file = {
        "pn": load_csv_index(base / "clean_person_name.csv", ("record_id", "country_iso")),
        "on": load_csv_index(base / "clean_organization_name.csv", ("record_id", "country_iso")),
        "pa": load_csv_index(base / "clean_person_address.csv", ("record_id", "country_iso")),
        "oa": load_csv_index(base / "clean_organization_address.csv", ("record_id", "country_iso")),
        "em_p": load_csv_index(base / "clean_person_email.csv", ("record_id", "country_iso")),
        "em_o": load_csv_index(base / "clean_organization_email.csv", ("record_id", "country_iso")),
        "ph_p": load_csv_index(base / "clean_person_phone.csv", ("record_id", "country_iso")),
        "ph_o": load_csv_index(base / "clean_organization_phone.csv", ("record_id", "country_iso")),
        "dl": load_csv_index(base / "clean_drivers_license_number.csv", ("record_id", "country_iso")),
        "tx": load_csv_index(base / "clean_tax_id.csv", ("record_id", "country_iso")),
        "dn": load_csv_index(base / "clean_duns_number.csv", ("record_id", "country_iso")),
    }

    persons, orgs = build_person_and_org_lists(by_file)
    if len(persons) != EXPECTED_DIRTY_PERSON_ROWS or len(orgs) != EXPECTED_DIRTY_ORG_ROWS:
        raise ValueError(
            f"expected {EXPECTED_DIRTY_PERSON_ROWS} person and {EXPECTED_DIRTY_ORG_ROWS} org rows, "
            f"got {len(persons)}, {len(orgs)}"
        )

    dist_path = base / "dirt_distribution.csv"
    dist_rows = load_distribution(dist_path)

    _validate_replace_only_handlers(handlers, rng)

    dirty_persons, c_p = process_entity_rows(persons, "person", dist_rows, rng, handlers)
    dirty_orgs, c_o = process_entity_rows(orgs, "organization", dist_rows, rng, handlers)

    _validate_dirty_output_replace_only(dirty_persons)
    _validate_dirty_output_replace_only(dirty_orgs)

    pc = Counter(r["country_iso"] for r in dirty_persons)
    oc = Counter(r["country_iso"] for r in dirty_orgs)
    validate_counts(pc, EXPECTED_DIRTY_ROWS_PER_COUNTRY)
    validate_counts(oc, EXPECTED_DIRTY_ROWS_PER_COUNTRY)

    person_fields = [
        "record_id",
        "country_iso",
        "country",
        "first_name",
        "middle_name",
        "last_name",
        "address_line_1",
        "address_line_2",
        "city",
        "postal_code",
        "state",
        "email",
        "phone",
        "drivers_license_number",
        "dirt_label_ids",
        "dirt_events_json",
    ]
    org_fields = [
        "record_id",
        "country_iso",
        "country",
        "organization_name",
        "address_line_1",
        "address_line_2",
        "city",
        "postal_code",
        "state",
        "email",
        "phone",
        "tax_id",
        "duns_number",
        "dirt_label_ids",
        "dirt_events_json",
    ]

    write_dirty_csv(base / "dirty_person.csv", dirty_persons, person_fields)
    write_dirty_csv(base / "dirty_organization.csv", dirty_orgs, org_fields)

    strip_bad: List[str] = []
    for bunch in (dirty_persons, dirty_orgs):
        for r in bunch:
            if "MIS_ADDR_STRIP_PREMISE" not in (r.get("dirt_label_ids") or ""):
                continue
            events = json.loads(r.get("dirt_events_json") or "[]")
            for ev in events:
                if ev.get("dirt_label_id") != "MIS_ADDR_STRIP_PREMISE":
                    continue
                fa = ev.get("fields_affected") or []
                if not fa:
                    strip_bad.append(f"{r.get('record_id')}: empty fields_affected")
    if strip_bad:
        raise ValueError("MIS_ADDR_STRIP_PREMISE no-op leaked:\n" + "\n".join(strip_bad[:20]))
    if c_p.get("MIS_ADDR_STRIP_PREMISE", 0) < 1 or c_o.get("MIS_ADDR_STRIP_PREMISE", 0) < 1:
        raise ValueError("expected MIS_ADDR_STRIP_PREMISE counts > 0 for person and org")

    update_distribution_actual_counts(dist_path, dist_rows, c_p, c_o)

    print("v3 dirty generation complete")
    print(f"person rows: {len(dirty_persons)}")
    print(f"organization rows: {len(dirty_orgs)}")
    print(f"unique person dirt labels: {len(c_p)}")
    print(f"unique org dirt labels: {len(c_o)}")


if __name__ == "__main__":
    main()
