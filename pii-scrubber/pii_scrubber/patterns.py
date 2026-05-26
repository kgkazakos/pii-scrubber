"""Regex / pattern detectors for direct identifiers.

Everything here is deterministic and offline. Each detector yields
``Detection`` objects with character offsets into the original text. Overlap
resolution happens later in ``scrubber.py``; detectors are free to over-emit.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from .models import Detection, EntityType, Source

# ---------------------------------------------------------------------------
# Compiled patterns
# ---------------------------------------------------------------------------

EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"
)

# URLs (http/https or bare www.) — emails are matched first so we exclude '@'.
URL_RE = re.compile(
    r"\b(?:https?://|www\.)[^\s<>\")]+",
    re.IGNORECASE,
)

IP_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"
)

# Phone numbers: international and common national formats. Deliberately
# conservative — requires at least 7 digits and typical separators so it does
# not swallow ordinary numbers. Anchored to avoid matching inside longer IDs.
PHONE_RE = re.compile(
    r"(?<![\w.])"
    r"(?:\+\d{1,3}[\s.\-]?)?"           # optional country code (must start with +)
    r"(?:\(\d{1,4}\)[\s.\-]?)?"         # optional area code in parens
    r"\d{2,4}(?:[\s.\-]\d{2,4}){1,3}"   # grouped digits
    r"(?![\w])(?!\.\d)"
)

# Standalone ID-like tokens: mixed alphanumerics, or long digit runs that are
# not phone-shaped. e.g. participant codes, case numbers, SSNs, card numbers.
ID_RE = re.compile(
    r"\b(?="
    r"[A-Z0-9][A-Z0-9\-]{5,}"          # at least 6 chars, dashes allowed
    r")(?:"
    r"[A-Z]{2,}\d{2,}[A-Z0-9\-]*"      # letters then digits (e.g. UX2024A)
    r"|\d{3}[\-\s]?\d{2}[\-\s]?\d{4}"  # SSN-shaped
    r"|\d{13,19}"                       # long card-like digit run
    r"|[A-Z0-9]{4,}-[A-Z0-9\-]{2,}"    # dashed code blocks
    r")\b"
)

# US-style ZIP and common postcode tails (used to anchor address heuristics).
DATE_RE = re.compile(
    r"\b(?:"
    r"\d{1,2}[/\-.]\d{1,2}[/\-.]\d{2,4}"                       # 12/03/2025
    r"|\d{4}[/\-.]\d{1,2}[/\-.]\d{1,2}"                        # 2025-03-12
    r"|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4}"          # March 12, 2025
    r"|\d{1,2}(?:st|nd|rd|th)?\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
    r"[a-z]*\.?\s+\d{4}"                                       # 12 March 2025
    r")\b",
    re.IGNORECASE,
)

# Street addresses: a number followed by 1–4 capitalised words ending in a
# street-type token. Heuristic — kept tight to limit false positives.
_STREET_TYPES = (
    r"Street|St|Avenue|Ave|Boulevard|Blvd|Road|Rd|Lane|Ln|Drive|Dr|Court|Ct"
    r"|Place|Pl|Square|Sq|Terrace|Way|Close|Crescent|Cres|Parade|Highway|Hwy"
)
ADDRESS_RE = re.compile(
    rf"\b\d{{1,5}}[A-Za-z]?\s+(?:[A-Z][A-Za-z'.\-]+\s+){{0,4}}"
    rf"(?:{_STREET_TYPES})\b\.?",
)

# Organisation suffixes: "Acme Inc", "Globex Pty Ltd", "Initech GmbH".
_ORG_SUFFIX = (
    r"Inc|Incorporated|Ltd|Limited|LLC|LLP|PLC|Corp|Corporation|Co|Company"
    r"|GmbH|AG|Pty|NV|BV|SA|SpA|Group|Holdings|Technologies|Labs|Systems"
    r"|Solutions|Partners|Ventures|Capital|Industries|Enterprises"
)
ORG_SUFFIX_RE = re.compile(
    rf"\b(?:[A-Z][A-Za-z0-9&'\-]+\s+){{0,3}}[A-Z][A-Za-z0-9&'\-]+"
    rf"\s+(?:{_ORG_SUFFIX})\b\.?",
)
# "University of X", "X University", "X College/Institute/Hospital".
ORG_INST_RE = re.compile(
    r"\b(?:University of [A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){0,2}"
    r"|[A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+){0,2}\s+"
    r"(?:University|College|Institute|Hospital|Clinic|Academy|Foundation))\b"
)


def _emit(pattern: re.Pattern, text: str, etype: EntityType, source: Source) -> Iterator[Detection]:
    for m in pattern.finditer(text):
        s, e = m.span()
        # Trim a trailing period that the pattern may have grabbed.
        surface = m.group(0)
        if surface.endswith(".") and etype in {EntityType.ADDRESS, EntityType.ORG}:
            surface = surface[:-1]
            e -= 1
        if not surface.strip():
            continue
        yield Detection(
            entity_type=etype,
            start=s,
            end=e,
            original=surface,
            source=source,
        )


def find_emails(text: str) -> list[Detection]:
    return list(_emit(EMAIL_RE, text, EntityType.EMAIL, Source.REGEX))


def find_urls(text: str) -> list[Detection]:
    # Drop URLs that are actually the domain part of an email (contain '@').
    return [d for d in _emit(URL_RE, text, EntityType.URL, Source.REGEX) if "@" not in d.original]


def find_ips(text: str) -> list[Detection]:
    return list(_emit(IP_RE, text, EntityType.IP, Source.REGEX))


def find_phones(text: str) -> list[Detection]:
    out = []
    for d in _emit(PHONE_RE, text, EntityType.PHONE, Source.REGEX):
        digits = re.sub(r"\D", "", d.original)
        if 7 <= len(digits) <= 15:
            out.append(d)
    return out


def find_ids(text: str) -> list[Detection]:
    out = []
    for d in _emit(ID_RE, text, EntityType.ID, Source.REGEX):
        digits = re.sub(r"\D", "", d.original)
        # Avoid swallowing plain years or short counts handled elsewhere.
        if len(digits) >= 4 or any(c.isalpha() for c in d.original):
            out.append(d)
    return out


def find_dates(text: str) -> list[Detection]:
    return list(_emit(DATE_RE, text, EntityType.DATE, Source.REGEX))


def find_addresses(text: str) -> list[Detection]:
    return list(_emit(ADDRESS_RE, text, EntityType.ADDRESS, Source.HEURISTIC))


def find_orgs(text: str) -> list[Detection]:
    out = list(_emit(ORG_SUFFIX_RE, text, EntityType.ORG, Source.HEURISTIC))
    out += list(_emit(ORG_INST_RE, text, EntityType.ORG, Source.HEURISTIC))
    return out


# Detector registry keyed by entity type.
DETECTORS = {
    EntityType.EMAIL: find_emails,
    EntityType.URL: find_urls,
    EntityType.IP: find_ips,
    EntityType.PHONE: find_phones,
    EntityType.ID: find_ids,
    EntityType.DATE: find_dates,
    EntityType.ADDRESS: find_addresses,
    EntityType.ORG: find_orgs,
}
