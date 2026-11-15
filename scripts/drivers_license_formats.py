"""Country-specific synthetic driving-licence numbers for the party benchmark.

Each ISO in ``countries.csv`` has a dedicated generator. Where a country exposes
a public checksum (national ID on the card, EU harmonised number rules, etc.),
we use ``python-stdnum`` or the same algorithms as ``faker`` locale SSN providers.

This is **synthetic** data: numbers are structurally and algebraically valid where
documented, but are not issued by any motor vehicle authority.
"""

from __future__ import annotations

import datetime
import random
import re
import string
from dataclasses import dataclass
from typing import Callable, Dict, Set

from faker import Faker

# stdnum (already required by generate_clean_country_party_data)
from stdnum.bg import egn as bg_egn
from stdnum.cz import rc as cz_rc
from stdnum.dk import cpr as dk_cpr
from stdnum.ee import ik as ee_ik
from stdnum.hr import oib as hr_oib
from stdnum.ie import pps as ie_pps
from stdnum.lt import asmens as lt_asmens
from stdnum.no import fodselsnummer as no_fn
from stdnum.ro import cnp as ro_cnp
from stdnum.se import personnummer as se_personnummer
from stdnum.si import emso as si_emso
from stdnum.sk import rc as sk_rc
from stdnum.iso7064 import mod_11_10

UL = string.ascii_uppercase
DIG = string.digits
ALNUM = UL + DIG

# Must match every ``ISO Code`` in countries.csv
SUPPORTED_DL_ISOS: Set[str] = {
    "AR",
    "AT",
    "BE",
    "BG",
    "BR",
    "CA",
    "CH",
    "CL",
    "CO",
    "CZ",
    "DE",
    "DK",
    "EE",
    "ES",
    "FI",
    "FR",
    "GB",
    "HR",
    "HU",
    "IE",
    "IT",
    "LT",
    "LV",
    "MX",
    "NL",
    "NO",
    "PL",
    "PT",
    "RO",
    "RS",
    "SE",
    "SI",
    "SK",
    "UA",
    "US",
}


@dataclass(frozen=True)
class PersonNameDob:
    """Person context used for formats that embed name or birth date (e.g. UK)."""

    first_name: str
    middle_name: str
    last_name: str
    dob: datetime.date
    female: bool


_faker_cache: Dict[str, Faker] = {}


def _faker(locale: str) -> Faker:
    if locale not in _faker_cache:
        try:
            _faker_cache[locale] = Faker(locale)
        except Exception:
            _faker_cache[locale] = Faker("en_US")
    return _faker_cache[locale]


def _rand_alnum(rng: random.Random, n: int, alphabet: str = ALNUM) -> str:
    return "".join(rng.choice(alphabet) for _ in range(n))


def _rand_digits(rng: random.Random, n: int) -> str:
    return "".join(rng.choice(DIG) for _ in range(n))


def _brute(std_is_valid: Callable[[str], bool], build: Callable[[], str], tries: int = 800) -> str:
    for _ in range(tries):
        cand = build()
        if std_is_valid(cand):
            return cand
    raise RuntimeError("could not synthesize valid ID after many attempts")


# --- National / checksum-backed (often printed on EU-style cards) ---


def _gen_cz_sk_rc(rng: random.Random) -> str:
    """Czech/Slovak rodné číslo (10 digits: 9-digit body + mod-11 check)."""

    def build() -> str:
        y = rng.randint(1960, 2004)
        m = rng.randint(1, 12)
        d = rng.randint(1, 28)
        female = rng.random() < 0.5
        mo = m + (50 if female else 0)
        if mo > 62:
            return ""
        yy = y % 100
        body6 = f"{yy:02d}{mo:02d}{d:02d}"
        tail3 = f"{rng.randint(0, 999):03d}"
        nine = body6 + tail3
        if len(nine) != 9:
            return ""
        check = int(nine) % 11 % 10
        return nine + str(check)

    return _brute(cz_rc.is_valid, build)


def _gen_ro_cnp(rng: random.Random, dob: datetime.date, female: bool) -> str:
    if dob.year < 1900 or dob.year > 2099:
        dob = datetime.date(1980, 6, 15)
    if dob.year < 2000:
        g = "2" if female else "1"
    else:
        g = "6" if female else "5"
    yy = dob.year % 100
    county = rng.choice(
        [f"{i:02d}" for i in range(1, 48)]
        + ["51", "52", "70", "80", "81", "82", "83"]
    )
    serial = rng.randint(1, 998)

    def build() -> str:
        s = f"{g}{yy:02d}{dob.month:02d}{dob.day:02d}{county}{serial:03d}"
        if len(s) != 12:
            return ""
        return s + ro_cnp.calc_check_digit(s)

    return _brute(ro_cnp.is_valid, build)


def _gen_bg_egn(rng: random.Random, dob: datetime.date, female: bool) -> str:
    yy = dob.year % 100
    month = dob.month + (40 if female else 0) + (20 if dob.year >= 2000 else 0)
    if month > 52:
        month = dob.month
    dd = dob.day

    def build() -> str:
        ord_ = rng.randint(0, 999)
        core = f"{yy:02d}{month:02d}{dd:02d}{ord_:03d}"
        if len(core) != 9:
            return ""
        return core + bg_egn.calc_check_digit(core)

    return _brute(bg_egn.is_valid, build)


def _gen_hr_oib(rng: random.Random) -> str:
    def build() -> str:
        body = _rand_digits(rng, 10)
        return body + mod_11_10.calc_check_digit(body)

    return _brute(hr_oib.is_valid, build)


def _gen_si_emso(rng: random.Random, dob: datetime.date, female: bool) -> str:
    dd = dob.day
    mm = dob.month
    yyy = dob.year % 1000
    reg = f"{rng.randint(1, 99):02d}"
    ser = rng.randint(500, 999) if female else rng.randint(0, 499)

    def build() -> str:
        body = f"{dd:02d}{mm:02d}{yyy:03d}{reg}{ser:03d}"
        if len(body) != 12:
            return ""
        return body + si_emso.calc_check_digit(body)

    return _brute(si_emso.is_valid, build)


def _gen_ee_ik(rng: random.Random, dob: datetime.date, female: bool) -> str:
    if dob.year < 1800 or dob.year >= 2100:
        dob = datetime.date(1992, 7, 11)
    century = dob.year // 100
    if century == 18:
        first = rng.choice((2, 4)) if female else rng.choice((1, 3))
    elif century == 19:
        first = 4 if female else 3
    elif century == 20:
        first = 6 if female else 5
    else:
        first = 8 if female else 7
    yy = dob.year % 100
    mm = dob.month
    dd = dob.day

    def build() -> str:
        serial = rng.randint(1, 999)
        body = f"{first}{yy:02d}{mm:02d}{dd:02d}{serial:03d}"
        if len(body) != 10:
            return ""
        return body + ee_ik.calc_check_digit(body)

    return _brute(ee_ik.is_valid, build)


def _gen_lt_asmens(rng: random.Random, dob: datetime.date, female: bool) -> str:
    del female  # gender encoded in first digit; brute search covers valid combos
    for _ in range(8000):
        c0 = str(rng.randint(1, 6))
        cand = f"{c0}{dob.year % 100:02d}{dob.month:02d}{dob.day:02d}{rng.randint(0, 999):03d}{rng.randint(0, 9)}"
        if len(cand) == 11 and lt_asmens.is_valid(cand, validate_birth_date=True):
            return cand
    raise RuntimeError("LT asmens kodas generation failed")


def _gen_dk_cpr(rng: random.Random, dob: datetime.date) -> str:
    dd = dob.day
    mm = dob.month
    yy = dob.year % 100
    for _ in range(800):
        c6 = str(rng.randint(0, 9))
        tail = rng.randint(0, 999)
        cand = f"{dd:02d}{mm:02d}{yy:02d}{c6}{tail:03d}"
        if len(cand) == 10 and dk_cpr.is_valid(cand):
            return cand
    raise RuntimeError("DK CPR generation failed")


def _gen_ie_pps(rng: random.Random) -> str:
    def build() -> str:
        digits = _rand_digits(rng, 7)
        second = rng.choice("ABH")
        cand = digits + _rand_alnum(rng, 1, UL) + second
        return cand

    return _brute(ie_pps.is_valid, build)


def _rs_jmbg(rng: random.Random, dob: datetime.date, female: bool) -> str:
    """Serbian JMBG: 13 digits, public checksum (Unique Master Citizen Number)."""

    def checksum12(d12: str) -> int:
        a = [int(x) for x in d12]
        s = (
            7 * (a[0] + a[6])
            + 6 * (a[1] + a[7])
            + 5 * (a[2] + a[8])
            + 4 * (a[3] + a[9])
            + 3 * (a[4] + a[10])
            + 2 * (a[5] + a[11])
        )
        k = 11 - (s % 11)
        if k > 9:
            return 0
        return k

    for _ in range(1200):
        dd = dob.day
        mm = dob.month
        yyy = dob.year % 1000
        rr = rng.randint(10, 69)
        bbb = rng.randint(500, 999) if female else rng.randint(0, 499)
        core = f"{dd:02d}{mm:02d}{yyy:03d}{rr:02d}{bbb:03d}"
        if len(core) != 12:
            continue
        k = checksum12(core)
        if k == 10:
            continue
        cand = core + str(k)
        if len(cand) == 13 and cand.isdigit():
            return cand
    raise RuntimeError("RS JMBG generation failed")


# --- UK DVLA-style 16-character photocard number (GOV.UK field rules, simplified surname) ---


def _uk_surname_part(surname: str) -> str:
    s = re.sub(r"[^A-Za-z]", "", surname or "").upper()
    if not s:
        return "99999"
    if len(s) >= 5:
        return s[:5]
    return (s + ("9" * 5))[:5]


def _uk_dob_part(dob: datetime.date, female: bool) -> str:
    decade_digit = str((dob.year % 100) // 10)
    month = dob.month + (50 if female else 0)
    return decade_digit + f"{month:02d}" + f"{dob.day:02d}"


def _uk_initials(first: str, middle: str) -> str:
    def one(ch: str, default: str = "9") -> str:
        c = (ch[:1] or default).upper()
        return c if c.isalpha() else default

    return one(first) + (one(middle) if (middle or "").strip() else "9")


def _uk_dl(ctx: PersonNameDob, rng: random.Random) -> str:
    p1 = _uk_surname_part(ctx.last_name)
    p2 = _uk_dob_part(ctx.dob, ctx.female)
    p3 = _uk_initials(ctx.first_name, ctx.middle_name)
    p4 = _rand_digits(rng, 4)
    return (p1 + p2 + p3 + p4).upper()


# --- Pattern-based (document number shapes; no universal public checksum) ---


def _eu_de_style_11(rng: random.Random) -> str:
    """DE/AT/CH-style licence number field (11 alphanumerics, MS Purview-style)."""
    first = rng.choice(DIG + UL)
    two = _rand_digits(rng, 2)
    mid = _rand_alnum(rng, 6)
    last = _rand_alnum(rng, 2)
    return (first + two + mid + last)[:11].upper()


def _finnish_licence_number(rng: random.Random) -> str:
    """Finnish card licence number: one alnum + three digits + hyphen + six digits."""
    head = rng.choice(DIG + UL)
    return f"{head}{_rand_digits(rng, 3)}-{_rand_digits(rng, 6)}"


def generate_drivers_license(iso: str, rng: random.Random, fake: Faker, ctx: PersonNameDob) -> str:
    if iso not in SUPPORTED_DL_ISOS:
        raise ValueError(f"No driving licence generator for ISO {iso!r}")

    if iso == "US":
        return rng.choice(UL) + _rand_digits(rng, 7)
    if iso == "CA":
        return rng.choice(UL) + _rand_digits(rng, 14)
    if iso == "GB":
        return _uk_dl(ctx, rng)
    if iso == "IE":
        return _gen_ie_pps(rng)
    if iso == "SE":
        return _faker("sv_SE").ssn(long=False, dash=True)
    if iso == "NO":
        return _faker("no_NO").ssn()
    if iso == "FI":
        return _finnish_licence_number(rng)
    if iso == "DK":
        return dk_cpr.format(_gen_dk_cpr(rng, ctx.dob))
    if iso == "LV":
        return _faker("lv_LV").ssn()
    if iso == "EE":
        return _gen_ee_ik(rng, ctx.dob, ctx.female)
    if iso == "LT":
        return _gen_lt_asmens(rng, ctx.dob, ctx.female)
    if iso == "CZ":
        return cz_rc.format(_gen_cz_sk_rc(rng))
    if iso == "SK":
        return sk_rc.format(_gen_cz_sk_rc(rng))
    if iso == "RO":
        return _gen_ro_cnp(rng, ctx.dob, ctx.female)
    if iso == "BG":
        return _gen_bg_egn(rng, ctx.dob, ctx.female)
    if iso == "HR":
        return _gen_hr_oib(rng)
    if iso == "SI":
        return _gen_si_emso(rng, ctx.dob, ctx.female)
    if iso == "RS":
        return _rs_jmbg(rng, ctx.dob, ctx.female)
    if iso == "DE" or iso == "AT" or iso == "CH":
        return _eu_de_style_11(rng)
    if iso == "FR":
        return rng.choice(UL) + _rand_digits(rng, 11)
    if iso == "IT":
        return _rand_alnum(rng, 2, UL) + _rand_digits(rng, 7) + _rand_alnum(rng, 2, UL)
    if iso == "ES":
        return _rand_digits(rng, 8) + rng.choice(UL)
    if iso == "PT":
        return _rand_digits(rng, 8)
    if iso == "NL":
        return _rand_digits(rng, 10)
    if iso == "BE":
        return _rand_digits(rng, 10)
    if iso == "PL":
        return _rand_alnum(rng, 5, UL) + _rand_digits(rng, 6)
    if iso == "HU":
        return _rand_digits(rng, 8)
    if iso == "UA":
        return _rand_alnum(rng, 3, UL) + _rand_digits(rng, 6)
    if iso == "BR":
        return _rand_digits(rng, 11)
    if iso == "MX":
        return rng.choice(UL + DIG) + _rand_digits(rng, 8)
    if iso == "AR":
        return _rand_digits(rng, rng.choice([8, 9, 10, 11]))
    if iso == "CL":
        return rng.choice(UL) + _rand_digits(rng, 8)
    if iso == "CO":
        return _rand_digits(rng, rng.choice([8, 9, 10]))

    raise ValueError(f"internal error: missing branch for ISO {iso}")


_DL_VALIDATORS: Dict[str, Callable[[str], bool]] = {}


def _register(iso: str, fn: Callable[[str], bool]) -> None:
    _DL_VALIDATORS[iso] = fn


def _v_regex(pattern: str) -> Callable[[str], bool]:
    r = re.compile(pattern)

    def check(s: str) -> bool:
        return bool(r.fullmatch(s.strip()))

    return check


def _init_validators() -> None:
    if _DL_VALIDATORS:
        return
    _register("US", _v_regex(r"[A-Z][0-9]{7}"))
    _register("CA", _v_regex(r"[A-Z][0-9]{14}"))
    _register("GB", _v_regex(r"[A-Z9]{5}\d{5}[A-Z9]{2}\d{4}"))
    _register("IE", ie_pps.is_valid)
    _register("SE", se_personnummer.is_valid)
    _register("NO", no_fn.is_valid)
    _register("FI", _v_regex(r"[0-9A-Z][0-9]{3}-[0-9]{6}"))
    _register("DK", dk_cpr.is_valid)
    _register("LV", _v_regex(r"\d{6}-\d{5}"))
    _register("EE", ee_ik.is_valid)
    _register("LT", lt_asmens.is_valid)
    _register("CZ", cz_rc.is_valid)
    _register("SK", sk_rc.is_valid)
    _register("RO", ro_cnp.is_valid)
    _register("BG", bg_egn.is_valid)
    _register("HR", hr_oib.is_valid)
    _register("SI", si_emso.is_valid)
    _register("RS", lambda s: s.isdigit() and len(s) == 13 and _rs_checksum_ok(s))
    for x in ("DE", "AT", "CH"):
        _register(x, _v_regex(r"[0-9A-Z]{11}"))
    _register("FR", _v_regex(r"[A-Z][0-9]{11}"))
    _register("IT", _v_regex(r"[A-Z]{2}[0-9]{7}[A-Z]{2}"))
    _register("ES", _v_regex(r"[0-9]{8}[A-Z]"))
    _register("PT", _v_regex(r"[0-9]{8}"))
    _register("NL", _v_regex(r"[0-9]{10}"))
    _register("BE", _v_regex(r"[0-9]{10}"))
    _register("PL", _v_regex(r"[A-Z]{5}[0-9]{6}"))
    _register("HU", _v_regex(r"[0-9]{8}"))
    _register("UA", _v_regex(r"[A-Z]{3}[0-9]{6}"))
    _register("BR", _v_regex(r"[0-9]{11}"))
    _register("MX", _v_regex(r"[A-Z0-9][0-9]{8}"))
    _register("AR", _v_regex(r"[0-9]{8,11}"))
    _register("CL", _v_regex(r"[A-Z][0-9]{8}"))
    _register("CO", _v_regex(r"[0-9]{8,10}"))


def _rs_checksum_ok(s: str) -> bool:
    if not s.isdigit() or len(s) != 13:
        return False
    a = [int(x) for x in s[:12]]
    k = 11 - (
        7 * (a[0] + a[6])
        + 6 * (a[1] + a[7])
        + 5 * (a[2] + a[8])
        + 4 * (a[3] + a[9])
        + 3 * (a[4] + a[10])
        + 2 * (a[5] + a[11])
    ) % 11
    if k > 9:
        k = 0
    return int(s[12]) == k


def is_valid_drivers_license(iso: str, value: str) -> bool:
    _init_validators()
    fn = _DL_VALIDATORS.get(iso)
    if not fn:
        return False
    try:
        return bool(fn(value.strip()))
    except Exception:
        return False
