"""Optional LLM enrichment for pii-scrubber.

The offline core handles *direct* identifiers. This layer is *on by default*
and adds the context-dependent *quasi*-identifiers that regex cannot see:

  * role + organisation combinations ("a senior PM at a ride-share startup")
  * unique or rare job titles
  * location specifics that narrow a person down
  * distinctive personal details ("the only left-handed pitcher on the team")

It is strictly additive and never destructive. If DSPy / LiteLLM is not
installed, or no API key is present, enrichment is skipped and the rule-based
result is returned unchanged (with a warning) — the tool never hard-fails on a
missing key. ``--no-llm`` forces that same offline path explicitly.

LLM support ships ON BY DEFAULT across three backends:

    anthropic  ->  anthropic/claude-opus-4-7      (Claude Opus)
    gemini     ->  gemini/gemini-3.1-pro-preview  (Gemini 3.1 Pro)
    openai     ->  openai/gpt-5.5                  (GPT-5.5)

Model strings are LiteLLM-style ``provider/model`` identifiers — edit the
``BACKENDS`` map below if your account exposes different names.
"""

from __future__ import annotations

import json
import os

from .models import Detection, EntityType, Source

# Canonical backend -> model string map. Update model strings here only.
BACKENDS: dict[str, str] = {
    "anthropic": "anthropic/claude-opus-4-7",
    "gemini": "gemini/gemini-3.1-pro-preview",
    "openai": "openai/gpt-5.5",
}

# Env var(s) that must be present for each backend to be usable.
_ENV_KEYS: dict[str, tuple[str, ...]] = {
    "anthropic": ("ANTHROPIC_API_KEY",),
    "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "openai": ("OPENAI_API_KEY",),
}

# Auto-selection order when the caller does not name a backend.
_PRIORITY = ("anthropic", "gemini", "openai")

_QUASI_TYPES = {
    "ROLE": EntityType.ROLE,
    "LOCATION_DETAIL": EntityType.LOCATION_DETAIL,
    "DETAIL": EntityType.DETAIL,
}


def available_backends() -> list[str]:
    """Backends whose API key is present in the environment."""
    return [name for name, keys in _ENV_KEYS.items() if any(os.environ.get(k) for k in keys)]


def default_backend() -> str | None:
    available = available_backends()
    for name in _PRIORITY:
        if name in available:
            return name
    return None


def is_available(backend: str | None = None) -> bool:
    if backend is None:
        return default_backend() is not None
    return backend in available_backends()


_INSTRUCTION = (
    "You are a privacy reviewer for qualitative research data. Identify only "
    "QUASI-IDENTIFIERS: phrases that could help re-identify a participant when "
    "combined with other information. These include role+organisation combos, "
    "rare/unique job titles, narrowing location specifics, and distinctive "
    "personal details. Do NOT return plain names, emails, phones, or addresses "
    "(those are handled separately). Return STRICT JSON: a list of objects with "
    'keys "text" (the exact substring from the input), "type" (one of ROLE, '
    'LOCATION_DETAIL, DETAIL), and "reason" (short). Return [] if none.'
)


def _generate(text: str, model: str) -> str:
    """Run one DSPy ChainOfThought call. Isolated so tests can monkeypatch it."""
    import dspy  # imported lazily; package works without dspy installed

    class QuasiIdentifierScan(dspy.Signature):
        """Find quasi-identifiers in qualitative research text."""

        instruction: str = dspy.InputField()
        document: str = dspy.InputField()
        quasi_identifiers_json: str = dspy.OutputField(
            desc="Strict JSON list of {text, type, reason} objects."
        )

    lm = dspy.LM(model)
    with dspy.context(lm=lm):
        scan = dspy.ChainOfThought(QuasiIdentifierScan)
        result = scan(instruction=_INSTRUCTION, document=text)
    return result.quasi_identifiers_json


def _parse(raw: str) -> list[dict]:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
    raw = raw.strip()
    start, end = raw.find("["), raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        data = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return [d for d in data if isinstance(d, dict) and d.get("text")]


def _locate(text: str, phrase: str, taken: list[tuple[int, int]]) -> tuple[int, int] | None:
    """Find the first occurrence of ``phrase`` not already claimed."""
    idx = 0
    while True:
        pos = text.find(phrase, idx)
        if pos == -1:
            return None
        span = (pos, pos + len(phrase))
        if not any(span[0] < e and s < span[1] for s, e in taken):
            return span
        idx = pos + 1


def find_quasi_identifiers(
    text: str,
    existing: list[Detection],
    backend: str | None = None,
) -> list[Detection]:
    """Detect quasi-identifiers via the LLM. Returns [] if unavailable.

    Raising is avoided here; callers in ``scrubber.py`` also wrap this in a
    try/except so a backend outage can never break a scrub run.
    """
    backend = backend or default_backend()
    if backend is None or backend not in BACKENDS:
        return []
    model = BACKENDS[backend]

    raw = _generate(text, model)
    items = _parse(raw)

    taken: list[tuple[int, int]] = [(d.start, d.end) for d in existing]
    out: list[Detection] = []
    for item in items:
        etype = _QUASI_TYPES.get(str(item.get("type", "")).upper(), EntityType.DETAIL)
        phrase = str(item["text"]).strip()
        if not phrase:
            continue
        span = _locate(text, phrase, taken)
        if span is None:
            continue
        taken.append(span)
        out.append(
            Detection(
                entity_type=etype,
                start=span[0],
                end=span[1],
                original=phrase,
                source=Source.LLM,
                confidence=0.7,
                note=str(item.get("reason") or "")[:200] or None,
            )
        )
    return out
