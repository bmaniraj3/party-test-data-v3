"""Validate country_profiles.yaml against countries.csv."""

from __future__ import annotations

import csv
import sys
from pathlib import Path

import yaml

REQUIRED_PROFILE_KEYS = ("faker_locale", "analyzer_language", "phone_region", "state_required", "eu_vat")


def _profiles_path() -> Path:
    return Path(__file__).resolve().parent.parent / "country_profiles.yaml"


def _countries_path() -> Path:
    return Path(__file__).resolve().parent.parent / "countries.csv"


def load_country_profiles(path: Path | None = None) -> dict:
    p = path or _profiles_path()
    with p.open(encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{p}: expected mapping of ISO -> profile")
    return data


def load_country_isos(path: Path | None = None) -> list[str]:
    p = path or _countries_path()
    isos: list[str] = []
    with p.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            iso = (row.get("ISO Code") or "").strip()
            if iso:
                isos.append(iso)
    return isos


def validate_country_profiles(
    profiles_path: Path | None = None,
    countries_path: Path | None = None,
) -> list[str]:
    profiles = load_country_profiles(profiles_path)
    errors: list[str] = []
    for iso in load_country_isos(countries_path):
        prof = profiles.get(iso)
        if prof is None:
            errors.append(f"missing profile for ISO {iso}")
            continue
        if not isinstance(prof, dict):
            errors.append(f"{iso}: profile must be a mapping")
            continue
        for key in REQUIRED_PROFILE_KEYS:
            if key not in prof:
                errors.append(f"{iso}: missing required key {key!r}")
        lang = prof.get("analyzer_language")
        if lang is False or lang is True:
            errors.append(
                f"{iso}: analyzer_language parsed as YAML boolean; quote the value (e.g. \"no\")"
            )
        elif lang is not None and (not isinstance(lang, str) or not lang.strip()):
            errors.append(f"{iso}: analyzer_language must be a non-empty string")
    extra = set(profiles.keys()) - set(load_country_isos(countries_path))
    for iso in sorted(extra):
        errors.append(f"profile exists for ISO {iso} but it is not in countries.csv")
    return errors


def main() -> int:
    errors = validate_country_profiles()
    if errors:
        for e in errors:
            print(f"ERROR: {e}", file=sys.stderr)
        return 1
    print("country_profiles.yaml OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
