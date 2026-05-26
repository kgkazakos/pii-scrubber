"""Person-name detection for the offline core.

Detecting names without a heavyweight NER model is inherently imperfect, so
this module combines three conservative signals:

1. **Speaker labels** — ``Sarah:`` at the start of a transcript line. The most
   reliable signal in interview data. Known *role* labels (Interviewer,
   Moderator, ...) are left intact; everything else is treated as a participant.
2. **Title-prefixed names** — ``Dr. Chen``, ``Ms Okafor``.
3. **Gazetteer + capitalisation** — a known first name (capitalised), optionally
   followed by a capitalised surname.

Full names register their first and last tokens as *aliases* so a later bare
"Sarah" maps to the same pseudonym as an earlier "Sarah Chen". The LLM layer is
expected to catch names this misses; the README is explicit that human review
is required.
"""

from __future__ import annotations

import re

from .models import Detection, EntityType, Source

# A compact gazetteer of common given names across several regions. Not
# exhaustive by design — the LLM layer and human review cover the long tail.
COMMON_FIRST_NAMES: frozenset[str] = frozenset(
    name.lower()
    for name in (
        # English / European
        "James John Robert Michael William David Richard Joseph Thomas Charles "
        "Christopher Daniel Matthew Anthony Mark Donald Steven Paul Andrew Joshua "
        "Kenneth Kevin Brian George Edward Ronald Timothy Jason Jeffrey Ryan Jacob "
        "Gary Nicholas Eric Jonathan Stephen Larry Justin Scott Brandon Benjamin "
        "Samuel Gregory Alexander Patrick Frank Raymond Jack Dennis Jerry Tyler "
        "Aaron Henry Douglas Peter Adam Nathan Zachary Walter Kyle Harold Carl "
        "Jeremy Gerald Keith Roger Arthur Lawrence Sean Christian Albert Joe Ethan "
        "Austin Jesse Willie Billy Bryan Bruce Jordan Ralph Roy Noah Dylan Eugene "
        "Wayne Alan Juan Louis Russell Gabriel Randy Vincent Philip Bobby Johnny "
        "Mary Patricia Jennifer Linda Elizabeth Barbara Susan Jessica Sarah Karen "
        "Nancy Lisa Margaret Betty Sandra Ashley Dorothy Kimberly Emily Donna "
        "Michelle Carol Amanda Melissa Deborah Stephanie Rebecca Laura Sharon "
        "Cynthia Kathleen Amy Angela Shirley Anna Brenda Pamela Emma Nicole Helen "
        "Samantha Katherine Christine Debra Rachel Carolyn Janet Catherine Maria "
        "Heather Diane Ruth Julie Olivia Joyce Virginia Victoria Kelly Lauren "
        "Christina Joan Evelyn Judith Megan Andrea Cheryl Hannah Jacqueline Martha "
        "Gloria Teresa Ann Sara Madison Frances Kathryn Janice Jean Abigail Alice "
        "Julia Judy Sophia Grace Denise Amber Doris Marilyn Danielle Beverly Isabella "
        # Common across other regions (broad coverage, not exhaustive)
        "Wei Li Ming Hua Yan Jing Lei Chen Fang Xin Hiro Yuki Kenji Akira Sato "
        "Priya Raj Anil Sunita Arjun Deepa Vikram Neha Ravi Anita Sanjay Pooja "
        "Mohammed Ahmed Fatima Aisha Omar Yusuf Layla Zainab Hassan Ali Mariam "
        "Kwame Ama Kofi Adaeze Chidi Ngozi Tunde Folake Sipho Thabo Nomvula "
        "Mateo Sofia Camila Diego Valentina Santiago Lucia Mateus Isabela Joao "
        "Olga Ivan Natasha Dmitri Svetlana Lars Ingrid Sven Pierre Marie Sofie "
        "Kostas Eleni Yiannis Maria Dimitris Katerina"
    ).split()
)

# Honorific titles that precede a surname.
_TITLE_RE = re.compile(
    r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Sir|Dame|Lord|Lady|Rev|Capt|Sgt|Lt)"
    r"\.?\s+([A-Z][a-zA-Z'\-]+(?:\s+[A-Z][a-zA-Z'\-]+)?)"
)

# Speaker label at the start of a line: "Name:" or "Name (tag):".
_SPEAKER_RE = re.compile(r"(?m)^[ \t]*([A-Z][A-Za-z'.\-]+(?:\s+[A-Z][A-Za-z'.\-]+)?)\s*(?:\([^)]*\))?\s*:")

# A single capitalised token. We scan these one at a time and anchor on the
# token that is actually in the gazetteer, rather than greedily pairing a
# leading capitalised word (e.g. a sentence-initial "Then"/"Later") with the
# name that follows it.
_CAP_TOKEN_RE = re.compile(r"\b[A-Z][a-zA-Z'\-]+\b")


def _add(out: list[Detection], start: int, end: int, text: str, source: Source) -> None:
    if text.strip():
        out.append(
            Detection(
                entity_type=EntityType.PERSON,
                start=start,
                end=end,
                original=text,
                source=source,
            )
        )


def find_speaker_labels(text: str, role_labels: set[str]) -> list[Detection]:
    """Names appearing as transcript speaker labels (excluding known roles)."""
    out: list[Detection] = []
    for m in _SPEAKER_RE.finditer(text):
        name = m.group(1)
        if name.lower() in role_labels:
            continue
        # Skip all-caps acronyms unless they look like a name token.
        if name.isupper() and len(name) <= 4:
            continue
        s = m.start(1)
        e = m.end(1)
        _add(out, s, e, name, Source.HEURISTIC)
    return out


def find_titled_names(text: str) -> list[Detection]:
    out: list[Detection] = []
    for m in _TITLE_RE.finditer(text):
        s, e = m.span(1)
        _add(out, s, e, m.group(1), Source.HEURISTIC)
    return out


def find_gazetteer_names(text: str) -> list[Detection]:
    out: list[Detection] = []
    tokens = list(_CAP_TOKEN_RE.finditer(text))
    n = len(tokens)
    i = 0
    while i < n:
        tok = tokens[i]
        if tok.group(0).lower() not in COMMON_FIRST_NAMES:
            i += 1
            continue
        # Anchored on a known first name. Optionally extend to a following
        # capitalised surname when it sits immediately after on the same line
        # (a single run of spaces/tabs, no newline).
        start, end = tok.start(), tok.end()
        if i + 1 < n:
            nxt = tokens[i + 1]
            gap = text[tok.end() : nxt.start()]
            if gap and not gap.strip() and "\n" not in gap:
                end = nxt.end()
                _add(out, start, end, text[start:end], Source.GAZETTEER)
                i += 2
                continue
        _add(out, start, end, text[start:end], Source.GAZETTEER)
        i += 1
    return out


def find_persons(text: str, role_labels: set[str]) -> list[Detection]:
    """All person detections from the offline core."""
    out: list[Detection] = []
    out += find_speaker_labels(text, role_labels)
    out += find_titled_names(text)
    out += find_gazetteer_names(text)
    return out
