"""Generate clean_*.csv splits from country_profiles.yaml + Faker + phonenumbers."""

from __future__ import annotations

import csv
import hashlib
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from drivers_license_formats import (
    SUPPORTED_DL_ISOS,
    PersonNameDob,
    generate_drivers_license,
    is_valid_drivers_license,
)
import phonenumbers
import yaml
from faker import Faker
from phonenumbers import PhoneNumberFormat, PhoneNumberType

SEED = 480
ROWS_PER_COUNTRY = 1000
PERSON_RATIO = 0.5


def person_rows_per_country() -> int:
    return int(ROWS_PER_COUNTRY * PERSON_RATIO)


def org_rows_per_country() -> int:
    return ROWS_PER_COUNTRY - person_rows_per_country()

PLACEHOLDER_TOKENS = {"unknown", "tba", "no name", "test", "no address", "n/a"}
FAKE_PHONE_VALUES = {
    "12345678",
    "123",
    "99999999",
    "11111111",
    "00000000",
    "55555555",
    "123456789",
    "987654321",
    "00012345",
    "11223344",
}

_faker_cache: Dict[str, Faker] = {}


def _profiles_path() -> Path:
    return Path(__file__).resolve().parent.parent / "country_profiles.yaml"


def load_country_profiles() -> Dict[str, Dict[str, Any]]:
    path = _profiles_path()
    if not path.is_file():
        raise FileNotFoundError(f"Missing {path}")
    with path.open(encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError("country_profiles.yaml must be a mapping of ISO -> profile")
    return data


def get_faker(locale: str) -> Faker:
    if locale not in _faker_cache:
        try:
            _faker_cache[locale] = Faker(locale)
        except Exception:
            _faker_cache[locale] = Faker("en_US")
    return _faker_cache[locale]


def stable_seed(*parts: str) -> int:
    h = hashlib.sha256("\0".join(parts).encode("utf-8")).digest()
    return int.from_bytes(h[:8], "big")


def _phone_has_fake_run(e164: str) -> bool:
    digits = re.sub(r"\D", "", e164)
    return any(run in digits for run in FAKE_PHONE_VALUES)


def _format_if_valid_unique(
    n: phonenumbers.PhoneNumber,
    region: str,
    seen: Set[str],
) -> Optional[str]:
    if not phonenumbers.is_valid_number_for_region(n, region):
        return None
    e164 = phonenumbers.format_number(n, PhoneNumberFormat.E164)
    digits = re.sub(r"\D", "", e164)
    if len(digits) < 8 or len(digits) > 15:
        return None
    if _phone_has_fake_run(e164):
        return None
    if e164 in seen:
        return None
    return e164


def make_phone_e164(region: str, fake: Faker, rng: random.Random, seen: Set[str]) -> str:
    for _ in range(80):
        raw = fake.phone_number()
        raw = re.sub(r"\s*x\s*\d+", "", raw, flags=re.I)
        try:
            n = phonenumbers.parse(raw, region)
        except phonenumbers.NumberParseException:
            continue
        e164 = _format_if_valid_unique(n, region, seen)
        if e164:
            seen.add(e164)
            return e164

    cc = phonenumbers.country_code_for_region(region) or 1
    example = phonenumbers.example_number_for_type(region, PhoneNumberType.MOBILE)
    if example is None:
        example = phonenumbers.example_number(region)
    nsn_len = len(phonenumbers.national_significant_number(example)) if example is not None else 9
    lengths = sorted({max(6, nsn_len - 1), nsn_len, nsn_len + 1})

    for _ in range(4000):
        if example is not None and rng.random() < 0.55:
            chars = list(phonenumbers.national_significant_number(example))
            start = max(0, len(chars) - 7)
            for i in range(start, len(chars)):
                chars[i] = str(rng.randint(0, 9))
            national = "".join(chars)
        else:
            length = rng.choice(lengths)
            national = "".join(str(rng.randint(0, 9)) for _ in range(length))
        try:
            n = phonenumbers.parse(f"+{cc}{national}", None)
        except phonenumbers.NumberParseException:
            continue
        e164 = _format_if_valid_unique(n, region, seen)
        if e164:
            seen.add(e164)
            return e164

    raise ValueError(f"could not generate unique valid E.164 phone for region {region}")


def apply_plus_addressing(email: str, record_id: str) -> str:
    if "@" not in email:
        return email
    if stable_seed("plus", record_id) % 10 != 0:
        return email
    local, domain = email.rsplit("@", 1)
    local = local.split("+", 1)[0]
    if not local:
        return email
    tag = f"mdm{stable_seed('plustag', record_id) % 10000:04d}"
    return f"{local}+{tag}@{domain}"


def apply_tax_format_variant(tax: str, iso: str, record_id: str) -> str:
    compact = re.sub(r"[\s.\-]", "", tax)
    if not compact:
        return tax
    mode = stable_seed("taxfmt", record_id, iso) % 4
    if mode == 0:
        return compact
    if mode == 1:
        return tax
    if mode == 2:
        if iso == "US" and re.fullmatch(r"\d{9}", compact):
            return f"{compact[:2]}-{compact[2:]}"
        if compact.upper().startswith(iso) and len(compact) > 4:
            return f"{compact[:2]}-{compact[2:]}"
        if len(compact) >= 8:
            return f"{compact[:4]}-{compact[4:]}"
        return compact
    groups = [compact[i : i + 3] for i in range(0, len(compact), 3)]
    return " ".join(groups)


def _state_value(fake: Faker, rng: random.Random, state_required: bool) -> str:
    if not state_required:
        return ""
    order = ("state", "region", "province", "state_abbr", "province_abbr", "county")
    for attr in order:
        fn = getattr(fake, attr, None)
        if not callable(fn):
            continue
        for _ in range(12):
            try:
                s = str(fn()).strip()
                if s:
                    return s[:48]
            except Exception:
                break
    return f"ADM{rng.randint(1, 99)}"


def make_address(
    fake: Faker,
    rng: random.Random,
    state_required: bool,
) -> Tuple[str, str, str, str, str]:
    street = fake.street_address()
    sec = getattr(fake, "secondary_address", None)
    line2 = ""
    if rng.random() < 0.38 and callable(sec):
        try:
            line2 = str(sec()).strip()
        except Exception:
            line2 = ""
    city = fake.city()
    postal = str(fake.postcode()).strip()
    state = _state_value(fake, rng, state_required)
    return street, line2, city, postal, state


def make_person_names(fake: Faker, rng: random.Random) -> Tuple[str, str, str]:
    first = fake.first_name()
    last = fake.last_name()
    if rng.random() < 0.42:
        middle = fake.first_name() if rng.random() < 0.55 else ""
    else:
        middle = ""
    return first, middle, last


def make_org_tax_id(fake: Faker, iso: str, eu_vat: bool, rng: random.Random) -> str:
    vat_fn = getattr(fake, "vat_id", None)
    if callable(vat_fn):
        for _ in range(25):
            try:
                t = str(vat_fn()).replace(" ", "").strip()
                if len(t) >= 8:
                    return t
            except Exception:
                break
    if iso == "US" and hasattr(fake, "ein"):
        return str(fake.ein())
    if hasattr(fake, "cnpj"):
        return re.sub(r"\D", "", str(fake.cnpj()))
    if hasattr(fake, "rfc"):
        return str(fake.rfc())
    if eu_vat:
        try:
            from stdnum.eu import vat

            for _ in range(400):
                digits = "".join(str(rng.randint(0, 9)) for _ in range(9))
                cand = iso + digits
                try:
                    if vat.is_valid(cand):
                        return vat.compact(cand)
                except Exception:
                    continue
        except ImportError:
            pass
    if iso == "UA":
        return f"{rng.randint(1000000000, 4294967295):010d}"[:10]
    return f"{iso}{rng.randint(10**8, 10**10 - 1)}"


def make_duns(rng: random.Random) -> str:
    body = [rng.randint(0, 9) for _ in range(8)]
    s = sum((3 if i % 2 == 0 else 1) * n for i, n in enumerate(body))
    check = (10 - (s % 10)) % 10
    return "".join(str(x) for x in body) + str(check)


def read_countries(path: Path) -> List[Dict[str, str]]:
    rows = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(
                {
                    "country": row["Country Name"].strip(),
                    "country_iso": row["ISO Code"].strip(),
                }
            )
    return rows


def build_rows(
    countries: List[Dict[str, str]],
    profiles: Dict[str, Dict[str, Any]],
) -> Tuple[List[Dict[str, str]], Counter, Counter, set, set]:
    rows: List[Dict[str, str]] = []
    country_counts: Counter = Counter()
    entity_counts: Counter = Counter()
    person_ids: set = set()
    org_ids: set = set()
    record_num = 1
    seen_person_phones: Dict[str, Set[str]] = defaultdict(set)
    seen_org_phones: Dict[str, Set[str]] = defaultdict(set)

    isos = {c["country_iso"] for c in countries}
    if isos != SUPPORTED_DL_ISOS:
        raise ValueError(
            "countries.csv ISO codes must match drivers_license_formats.SUPPORTED_DL_ISOS "
            f"(missing {sorted(SUPPORTED_DL_ISOS - isos)}, extra {sorted(isos - SUPPORTED_DL_ISOS)})"
        )

    for country_rec in countries:
        country = country_rec["country"]
        iso = country_rec["country_iso"]
        prof = profiles.get(iso) or {}
        locale = str(prof.get("faker_locale") or "en_US")
        phone_region = str(prof.get("phone_region") or iso)
        state_required = bool(prof.get("state_required", False))
        eu_vat = bool(prof.get("eu_vat", False))

        rng = random.Random(stable_seed(str(SEED), iso) % (2**32))
        fake = get_faker(locale)

        person_target = person_rows_per_country()
        org_target = org_rows_per_country()

        for _ in range(person_target):
            first, middle, last = make_person_names(fake, rng)
            record_id = f"{iso}-{record_num:06d}"
            record_num += 1
            address_1, address_2, city, postal, state = make_address(fake, rng, state_required)
            phone = make_phone_e164(phone_region, fake, rng, seen_person_phones[iso])
            email = apply_plus_addressing(fake.email(), record_id)
            dob = fake.date_of_birth(minimum_age=18, maximum_age=90)
            female = rng.random() < 0.5
            dl_ctx = PersonNameDob(
                first_name=first,
                middle_name=middle,
                last_name=last,
                dob=dob,
                female=female,
            )
            dl = generate_drivers_license(iso, rng, fake, dl_ctx)
            rows.append(
                {
                    "record_id": record_id,
                    "country": country,
                    "country_iso": iso,
                    "entity_type": "person",
                    "first_name": first,
                    "middle_name": middle,
                    "last_name": last,
                    "organization_name": "",
                    "address_line_1": address_1,
                    "address_line_2": address_2,
                    "city": city,
                    "postal_code": postal,
                    "state": state,
                    "email": email,
                    "phone": phone,
                    "drivers_license_number": dl,
                    "tax_id": "",
                    "duns_number": "",
                }
            )
            country_counts[iso] += 1
            entity_counts["person"] += 1
            person_ids.add(record_id)

        for _ in range(org_target):
            org_name = fake.company()
            record_id = f"{iso}-{record_num:06d}"
            record_num += 1
            address_1, address_2, city, postal, state = make_address(fake, rng, state_required)
            phone = make_phone_e164(phone_region, fake, rng, seen_org_phones[iso])
            raw_email = fake.company_email() if hasattr(fake, "company_email") else fake.email()
            email = apply_plus_addressing(raw_email, record_id)
            tax = apply_tax_format_variant(make_org_tax_id(fake, iso, eu_vat, rng), iso, record_id)
            duns = make_duns(rng)
            rows.append(
                {
                    "record_id": record_id,
                    "country": country,
                    "country_iso": iso,
                    "entity_type": "organization",
                    "first_name": "",
                    "middle_name": "",
                    "last_name": "",
                    "organization_name": org_name,
                    "address_line_1": address_1,
                    "address_line_2": address_2,
                    "city": city,
                    "postal_code": postal,
                    "state": state,
                    "email": email,
                    "phone": phone,
                    "drivers_license_number": "",
                    "tax_id": tax,
                    "duns_number": duns,
                }
            )
            country_counts[iso] += 1
            entity_counts["organization"] += 1
            org_ids.add(record_id)

    return rows, country_counts, entity_counts, person_ids, org_ids


def split_files(rows: List[Dict[str, str]]) -> Dict[str, List[Dict[str, str]]]:
    person_name: List[Dict[str, str]] = []
    org_name: List[Dict[str, str]] = []
    person_address: List[Dict[str, str]] = []
    org_address: List[Dict[str, str]] = []
    person_email: List[Dict[str, str]] = []
    org_email: List[Dict[str, str]] = []
    person_phone: List[Dict[str, str]] = []
    org_phone: List[Dict[str, str]] = []
    dl_rows: List[Dict[str, str]] = []
    tax_rows: List[Dict[str, str]] = []
    duns_rows: List[Dict[str, str]] = []

    for r in rows:
        is_person = r["entity_type"] == "person"
        if is_person:
            person_name.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "first_name": r["first_name"],
                    "middle_name": r["middle_name"],
                    "last_name": r["last_name"],
                }
            )
            person_address.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "country": r["country"],
                    "address_line_1": r["address_line_1"],
                    "address_line_2": r["address_line_2"],
                    "city": r["city"],
                    "postal_code": r["postal_code"],
                    "state": r["state"],
                }
            )
            person_email.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "email": r["email"],
                }
            )
            person_phone.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "phone": r["phone"],
                }
            )
            dl_rows.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "drivers_license_number": r["drivers_license_number"],
                }
            )
        else:
            org_name.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "organization_name": r["organization_name"],
                }
            )
            org_address.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "country": r["country"],
                    "address_line_1": r["address_line_1"],
                    "address_line_2": r["address_line_2"],
                    "city": r["city"],
                    "postal_code": r["postal_code"],
                    "state": r["state"],
                }
            )
            org_email.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "email": r["email"],
                }
            )
            org_phone.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "phone": r["phone"],
                }
            )
            tax_rows.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "tax_id": r["tax_id"],
                }
            )
            duns_rows.append(
                {
                    "record_id": r["record_id"],
                    "country_iso": r["country_iso"],
                    "duns_number": r["duns_number"],
                }
            )

    return {
        "clean_person_name.csv": person_name,
        "clean_organization_name.csv": org_name,
        "clean_person_address.csv": person_address,
        "clean_organization_address.csv": org_address,
        "clean_person_email.csv": person_email,
        "clean_organization_email.csv": org_email,
        "clean_person_phone.csv": person_phone,
        "clean_organization_phone.csv": org_phone,
        "clean_drivers_license_number.csv": dl_rows,
        "clean_tax_id.csv": tax_rows,
        "clean_duns_number.csv": duns_rows,
    }


def write_csv(path: Path, rows: List[Dict[str, str]]) -> None:
    if not rows:
        raise ValueError(f"No rows for {path.name}")
    fieldnames = list(rows[0].keys())
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def contains_placeholder(value: str) -> bool:
    lower = value.strip().lower()
    if not lower:
        return False
    return lower in PLACEHOLDER_TOKENS


def _phone_is_plausible_e164(phone: str) -> bool:
    try:
        n = phonenumbers.parse(phone, None)
        return phonenumbers.is_valid_number(n)
    except phonenumbers.NumberParseException:
        return False


def _validate_email_rows(filename: str, rows: List[Dict[str, str]]) -> None:
    for r in rows:
        if not r["email"].strip() or "@" not in r["email"]:
            raise ValueError(f"{filename}: invalid email")


def _validate_phone_rows(filename: str, rows: List[Dict[str, str]]) -> None:
    for r in rows:
        phone = r["phone"].strip()
        if not phone.startswith("+"):
            raise ValueError(f"{filename}: phone must be E.164 (+ prefix)")
        if not _phone_is_plausible_e164(phone):
            raise ValueError(f"{filename}: invalid E.164 phone {phone!r}")
        digits = re.sub(r"\D", "", phone)
        if _phone_has_fake_run(phone):
            raise ValueError(f"{filename}: fake phone pattern detected")
        if len(digits) < 8 or len(digits) > 15:
            raise ValueError(f"{filename}: unlikely phone length")


def _validate_phone_uniqueness(filename: str, rows: List[Dict[str, str]], expected: int) -> None:
    by_iso: Dict[str, Set[str]] = defaultdict(set)
    for r in rows:
        by_iso[r["country_iso"]].add(r["phone"].strip())
    for iso, phones in by_iso.items():
        if len(phones) != expected:
            raise ValueError(
                f"{filename}: country {iso} expected {expected} unique phones, got {len(phones)}"
            )


def validate_outputs(
    split_rows: Dict[str, List[Dict[str, str]]],
    countries: List[Dict[str, str]],
    person_ids: set,
    org_ids: set,
    profiles: Dict[str, Dict[str, Any]],
) -> None:
    n_countries = len(countries)
    exp_person = n_countries * person_rows_per_country()
    exp_org = n_countries * org_rows_per_country()
    per_country_person = person_rows_per_country()
    per_country_org = org_rows_per_country()
    valid_iso_country = {c["country_iso"]: c["country"] for c in countries}

    person_only_files = {
        "clean_person_name.csv",
        "clean_person_address.csv",
        "clean_person_email.csv",
        "clean_person_phone.csv",
        "clean_drivers_license_number.csv",
    }
    org_only_files = {
        "clean_organization_name.csv",
        "clean_organization_address.csv",
        "clean_organization_email.csv",
        "clean_organization_phone.csv",
        "clean_tax_id.csv",
        "clean_duns_number.csv",
    }

    for filename, rows in split_rows.items():
        if filename in person_only_files:
            expected, per_c = exp_person, per_country_person
        elif filename in org_only_files:
            expected, per_c = exp_org, per_country_org
        else:
            raise ValueError(f"unexpected split file {filename}")

        if len(rows) != expected:
            raise ValueError(f"{filename}: expected {expected} rows, got {len(rows)}")

        per_country = Counter(r["country_iso"] for r in rows)
        for c in countries:
            iso = c["country_iso"]
            if per_country[iso] != per_c:
                raise ValueError(
                    f"{filename}: country {iso} expected {per_c}, got {per_country[iso]}"
                )

        for r in rows:
            if not r.get("record_id"):
                raise ValueError(f"{filename}: blank record_id")
            if not r.get("country_iso"):
                raise ValueError(f"{filename}: blank country_iso")
            for v in r.values():
                if isinstance(v, str) and contains_placeholder(v):
                    raise ValueError(f"{filename}: placeholder token found in value '{v}'")

    for filename in ["clean_person_address.csv", "clean_organization_address.csv"]:
        for r in split_rows[filename]:
            expected_country = valid_iso_country[r["country_iso"]]
            if r["country"] != expected_country:
                raise ValueError(f"{filename}: country mismatch for {r['record_id']}")

            is_person_file = filename == "clean_person_address.csv"
            rid = r["record_id"]
            if is_person_file:
                if rid not in person_ids:
                    raise ValueError(f"{filename}: unexpected record_id {rid} (not person)")
                if not (r["address_line_1"] and r["city"] and r["postal_code"]):
                    raise ValueError(f"{filename}: missing mandatory populated address fields")
                prof = profiles.get(r["country_iso"]) or {}
                if prof.get("state_required") and not (r.get("state") or "").strip():
                    raise ValueError(f"{filename}: state required for {r['country_iso']} on {rid}")
            else:
                if rid not in org_ids:
                    raise ValueError(f"{filename}: unexpected record_id {rid} (not organization)")
                if not (r["address_line_1"] and r["city"] and r["postal_code"]):
                    raise ValueError(f"{filename}: missing mandatory populated address fields")
                prof = profiles.get(r["country_iso"]) or {}
                if prof.get("state_required") and not (r.get("state") or "").strip():
                    raise ValueError(f"{filename}: state required for {r['country_iso']} on {rid}")

    _validate_email_rows("clean_person_email.csv", split_rows["clean_person_email.csv"])
    _validate_email_rows("clean_organization_email.csv", split_rows["clean_organization_email.csv"])
    _validate_phone_rows("clean_person_phone.csv", split_rows["clean_person_phone.csv"])
    _validate_phone_rows("clean_organization_phone.csv", split_rows["clean_organization_phone.csv"])
    _validate_phone_uniqueness("clean_person_phone.csv", split_rows["clean_person_phone.csv"], per_country_person)
    _validate_phone_uniqueness(
        "clean_organization_phone.csv", split_rows["clean_organization_phone.csv"], per_country_org
    )

    for r in split_rows["clean_person_email.csv"]:
        if r["record_id"] not in person_ids:
            raise ValueError("clean_person_email.csv: record_id must be person")
    for r in split_rows["clean_organization_email.csv"]:
        if r["record_id"] not in org_ids:
            raise ValueError("clean_organization_email.csv: record_id must be organization")
    for r in split_rows["clean_person_phone.csv"]:
        if r["record_id"] not in person_ids:
            raise ValueError("clean_person_phone.csv: record_id must be person")
    for r in split_rows["clean_organization_phone.csv"]:
        if r["record_id"] not in org_ids:
            raise ValueError("clean_organization_phone.csv: record_id must be organization")

    for r in split_rows["clean_drivers_license_number.csv"]:
        rid = r["record_id"]
        if rid not in person_ids:
            raise ValueError("clean_drivers_license_number.csv: row must be person")
        iso = r["country_iso"]
        v = r["drivers_license_number"].strip()
        if not v:
            raise ValueError("clean_drivers_license_number.csv: missing person DL")
        if not is_valid_drivers_license(iso, v):
            raise ValueError(
                f"clean_drivers_license_number.csv: invalid DL for {iso} record {rid}: {v!r}"
            )
    for r in split_rows["clean_tax_id.csv"]:
        rid = r["record_id"]
        if rid not in org_ids:
            raise ValueError("clean_tax_id.csv: row must be organization")
        if not r["tax_id"].strip():
            raise ValueError("clean_tax_id.csv: missing org tax ID")
    for r in split_rows["clean_duns_number.csv"]:
        rid = r["record_id"]
        if rid not in org_ids:
            raise ValueError("clean_duns_number.csv: row must be organization")
        if not r["duns_number"].strip():
            raise ValueError("clean_duns_number.csv: missing org duns")
        if not re.fullmatch(r"\d{9}", r["duns_number"].strip()):
            raise ValueError("clean_duns_number.csv: duns must be 9 digits")

    for r in split_rows["clean_person_name.csv"]:
        if r["record_id"] not in person_ids:
            raise ValueError("clean_person_name.csv: row must be person")
        if not (r.get("first_name") or "").strip() or not (r.get("last_name") or "").strip():
            raise ValueError("clean_person_name.csv: first and last name required")
        joined = " ".join([r["first_name"], r["middle_name"], r["last_name"]]).strip()
        if "@" in joined:
            raise ValueError("clean_person_name.csv: email-like content in name")
    for r in split_rows["clean_organization_name.csv"]:
        if r["record_id"] not in org_ids:
            raise ValueError("clean_organization_name.csv: row must be organization")
        if not (r.get("organization_name") or "").strip():
            raise ValueError("clean_organization_name.csv: organization_name required")
        if "@" in r["organization_name"]:
            raise ValueError("clean_organization_name.csv: email-like content in org name")


def main() -> None:
    base_dir = Path(__file__).resolve().parent.parent
    countries_path = base_dir / "countries.csv"
    out_dir = base_dir

    profiles = load_country_profiles()
    countries = read_countries(countries_path)
    for c in countries:
        if c["country_iso"] not in profiles:
            raise ValueError(f"country_profiles.yaml missing entry for {c['country_iso']}")

    rows, country_counts, entity_counts, person_ids, org_ids = build_rows(countries, profiles)
    split_rows = split_files(rows)

    validate_outputs(split_rows, countries, person_ids, org_ids, profiles)

    for filename, records in split_rows.items():
        write_csv(out_dir / filename, records)

    print("Generation complete.")
    print(f"Seed: {SEED}")
    print(f"Rows per country: {ROWS_PER_COUNTRY}")
    print(f"Total records: {len(rows)}")
    print("Entity distribution:")
    for k, v in entity_counts.items():
        print(f"  - {k}: {v}")
    print("Per-country counts:")
    for iso, count in sorted(country_counts.items()):
        print(f"  - {iso}: {count}")
    print("Output files:")
    for filename in split_rows.keys():
        print(f"  - {filename}: {len(split_rows[filename])} rows")


if __name__ == "__main__":
    main()
