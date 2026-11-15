"""Strip house/premise identifiers from one address line. No-op if none are present."""

from __future__ import annotations

import re
import unicodedata

_ORDINAL = re.compile(r"(?i)\b\d{1,3}(?:st|nd|rd|th)\b")
_ROUTE = re.compile(
    r"(?i)\b(?:route|hwy|highway|rt|fm|cr|county road|state road|us|i)\s*[-#]?\s*\d+\b"
)
_SN = re.compile(r"(?i)\bS\s*/\s*N\b")
_UNIT_BLOCK = re.compile(
    r"(?i)\b(?:bl|sc|ap|apt|apartment|suite|ste|unit|flat|bldg|nr|bloco|andar)\.?\s+"
    r"\d+[A-Za-z]?\b"
)
_PREMISE_NUM = r"(?:n[oº°]\.?\s*|no\.?\s*|#\s*)?\d+[A-Za-z]?(?:\s*[-–/]\s*\d+[A-Za-z]?)?"
_LEADING = re.compile(rf"(?iu)^\s*{_PREMISE_NUM}\s*,?\s+")
_SOLE = re.compile(rf"(?iu)^\s*{_PREMISE_NUM}\s*$")
_TRAILING = re.compile(rf"(?iu),?\s+{_PREMISE_NUM}\s*$")
_MID_NO = re.compile(r"(?iu)\b(?:n[oº°]\.?|no\.?|#)\s*\d+[A-Za-z]?\b")
_PH = "\ufffc"


def _fold_digits(s: str) -> str:
    out: list[str] = []
    for ch in s:
        if ch.isdigit():
            try:
                out.append(str(unicodedata.digit(ch)))
            except Exception:
                out.append(ch)
        else:
            out.append(ch)
    return "".join(out)


def _protect(s: str) -> tuple[str, list[str]]:
    held: list[str] = []

    def stash(m: re.Match[str]) -> str:
        held.append(m.group(0))
        return f"{_PH}{len(held) - 1}{_PH}"

    t = _SN.sub(stash, s)
    t = _ORDINAL.sub(stash, t)
    t = _ROUTE.sub(stash, t)
    return t, held


def _restore(s: str, held: list[str]) -> str:
    out = s
    for i, orig in enumerate(held):
        out = out.replace(f"{_PH}{i}{_PH}", orig)
    return out


def _tidy(s: str) -> str:
    s = re.sub(r"\s+,", ",", s)
    s = re.sub(r",\s*,+", ",", s)
    s = re.sub(r"\s{2,}", " ", s)
    return s.strip(" ,")


def strip_premise_line(value: str) -> str:
    """Return line with premise tokens removed, or the original string if unchanged."""
    raw = (value or "").strip()
    if not raw:
        return value or ""
    folded = _fold_digits(raw)
    protected, held = _protect(folded)
    work = protected
    prev = None
    while prev != work:
        prev = work
        if _SOLE.match(work):
            work = ""
            break
        work = _UNIT_BLOCK.sub(" ", work)
        work = _MID_NO.sub(" ", work)
        work = _LEADING.sub("", work)
        work = _TRAILING.sub("", work)
        work = _tidy(work)
    work = _restore(work, held)
    work = _tidy(work)
    if work == folded or work == raw:
        return raw
    return work
