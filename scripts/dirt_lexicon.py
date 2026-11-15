"""Load placeholder_lexicon.yaml and pick locale tokens for dirt handlers."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any, Dict, List

import yaml

GLOBAL_SYSTEM = ["NULL", "N/A", "-", "TBD"]
FAKE_PHONE_SHORT = ["123", "12", "1", "000"]
FAKE_PHONE_REPEAT = ["11111111", "00000000", "99999999", "55555555"]
NUMERIC_TOKENS = ["123", "999", "0000", "42"]
TEST_EMAILS = [
    "anonymous.test@example.invalid",
    "test@example.invalid",
    "noreply.test@invalid.example",
    "placeholder@example.invalid",
]
MALFORMED_EMAILS = ["foo@", "user @domain.com", "a@b@c.com", "local @ x.com"]
WEBSITES = [
    "https://example.com",
    "https://www.example.org",
    "http://company.example.net",
]
FAKE_PHONE_RUNS = [
    "123456789",
    "987654321",
    "11111111",
    "00000000",
    "55555555",
    "11223344",
]


class DirtLexicon:
    def __init__(self, doc: Dict[str, Any]) -> None:
        self.iso_language: Dict[str, str] = {str(k): str(v) for k, v in (doc.get("iso_language") or {}).items()}
        self.languages: Dict[str, Dict[str, List[str]]] = {}
        for lang, keys in (doc.get("languages") or {}).items():
            self.languages[str(lang)] = {
                str(k): [str(x) for x in v if x is not None] for k, v in (keys or {}).items()
            }

    def lang(self, iso: str) -> str:
        return self.iso_language.get(iso, "en")

    def pick(self, iso: str, key: str, rng: random.Random, *, mix_global: bool = False) -> str:
        lang = self.lang(iso)
        pool = list(self.languages.get(lang, {}).get(key) or self.languages["en"].get(key) or ["unknown"])
        if mix_global:
            pool = pool + GLOBAL_SYSTEM
        return rng.choice(pool)


def load_lexicon(base: Path) -> DirtLexicon:
    path = base / "placeholder_lexicon.yaml"
    with path.open(encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    return DirtLexicon(doc)
