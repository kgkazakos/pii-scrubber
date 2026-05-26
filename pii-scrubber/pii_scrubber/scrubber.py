"""Core scrubbing orchestration.

``Scrubber`` ties together the offline detectors, the optional LLM layer, the
pseudonymiser, and the text-rewriting step. A single ``Registry`` can be shared
across documents (see ``corpus.py``) to keep tokens consistent corpus-wide.
"""

from __future__ import annotations

import warnings

from . import names, patterns
from .models import (
    Detection,
    EntityType,
    RedactionManifest,
    ScrubConfig,
    ScrubResult,
)
from .pseudonymizer import Registry

# Priority used when two detections overlap. Higher wins.
_PRIORITY: dict[EntityType, int] = {
    EntityType.EMAIL: 100,
    EntityType.URL: 95,
    EntityType.IP: 90,
    EntityType.ID: 85,
    EntityType.PHONE: 80,
    EntityType.ADDRESS: 70,
    EntityType.ORG: 60,
    EntityType.PERSON: 55,
    EntityType.DATE: 40,
    EntityType.ROLE: 30,
    EntityType.LOCATION_DETAIL: 28,
    EntityType.DETAIL: 25,
}


def _resolve_overlaps(detections: list[Detection]) -> list[Detection]:
    """Greedy non-overlapping selection: longer span first, then priority."""
    ordered = sorted(
        detections,
        key=lambda d: (-(d.length), -_PRIORITY.get(d.entity_type, 0), d.start),
    )
    kept: list[Detection] = []
    for d in ordered:
        if any(d.overlaps(k) for k in kept):
            continue
        kept.append(d)
    kept.sort(key=lambda d: d.start)
    return kept


def _apply(text: str, detections: list[Detection]) -> str:
    """Replace detected spans with their tokens, working right-to-left."""
    out = text
    for d in sorted(detections, key=lambda d: d.start, reverse=True):
        if d.token is None:
            continue
        out = out[: d.start] + d.token + out[d.end :]
    return out


def _build_manifest(detections: list[Detection]) -> RedactionManifest:
    counts: dict[str, int] = {}
    seen_tokens: dict[str, set[str]] = {}
    for d in detections:
        key = d.entity_type.value
        counts[key] = counts.get(key, 0) + 1
        seen_tokens.setdefault(key, set()).add(d.token or d.original)
    unique = {k: len(v) for k, v in seen_tokens.items()}
    return RedactionManifest(counts=counts, unique_entities=unique)


class Scrubber:
    """Stateful scrubber. Reuse one instance (or its registry) across a corpus."""

    def __init__(self, config: ScrubConfig | None = None, registry: Registry | None = None) -> None:
        self.config = config or ScrubConfig()
        self.registry = registry or Registry(person_style=self.config.person_style)

    # -- detection ---------------------------------------------------------
    def detect(self, text: str) -> list[Detection]:
        cfg = self.config
        found: list[Detection] = []

        for etype, detector in patterns.DETECTORS.items():
            if etype in cfg.enabled_types:
                found += detector(text)

        if EntityType.PERSON in cfg.enabled_types:
            found += names.find_persons(text, cfg.role_labels)

        if cfg.use_llm:
            found += self._llm_detect(text, found)

        return _resolve_overlaps(found)

    def _llm_detect(self, text: str, existing: list[Detection]) -> list[Detection]:
        """Run the optional quasi-identifier layer. Never raises."""
        try:
            from . import llm
        except Exception as exc:  # pragma: no cover - import guard
            warnings.warn(f"LLM layer unavailable, continuing rule-based only: {exc}", stacklevel=2)
            return []
        try:
            return llm.find_quasi_identifiers(
                text, existing, backend=self.config.llm_backend
            )
        except Exception as exc:  # pragma: no cover - runtime guard
            warnings.warn(f"LLM enrichment skipped: {exc}", stacklevel=2)
            return []

    # -- full pass ---------------------------------------------------------
    def scrub(self, text: str) -> ScrubResult:
        detections = self.detect(text)
        self.registry.assign(detections)
        scrubbed = _apply(text, detections)
        manifest = _build_manifest(detections)
        key = dict(self.registry.key) if self.config.keep_key else {}
        if self.config.keep_key:
            warnings.warn(
                "keep_key=True stores a reversible token->original map. Anyone "
                "with this key can re-identify the data — store it separately "
                "from the scrubbed text and treat it as raw PII.",
                stacklevel=2,
            )
        return ScrubResult(
            original_text=text,
            scrubbed_text=scrubbed,
            detections=detections,
            manifest=manifest,
            key=key,
        )


def scrub_text(text: str, config: ScrubConfig | None = None) -> ScrubResult:
    """One-shot convenience wrapper for a single document."""
    return Scrubber(config=config).scrub(text)
