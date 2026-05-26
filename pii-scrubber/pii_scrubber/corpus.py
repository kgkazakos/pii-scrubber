"""Corpus-level scrubbing.

A ``CorpusScrubber`` keeps a single shared ``Registry`` so that the same entity
maps to the same token across *every* document in a study. Scrub the corpus in
one pass (or document by document on the same instance) and the relationships
between files survive de-identification.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import RedactionManifest, ScrubConfig, ScrubResult
from .pseudonymizer import Registry
from .scrubber import Scrubber


@dataclass
class CorpusResult:
    """Per-document results plus a combined manifest."""

    results: dict[str, ScrubResult] = field(default_factory=dict)
    combined: RedactionManifest = field(default_factory=RedactionManifest)

    def to_dict(self) -> dict:
        return {
            "documents": {name: r.to_dict() for name, r in self.results.items()},
            "combined_manifest": self.combined.to_dict(),
        }


class CorpusScrubber:
    """Scrub many documents while keeping tokens consistent corpus-wide."""

    def __init__(self, config: ScrubConfig | None = None) -> None:
        self.config = config or ScrubConfig()
        self.registry = Registry(person_style=self.config.person_style)
        self._scrubber = Scrubber(config=self.config, registry=self.registry)

    def scrub_one(self, name: str, text: str) -> ScrubResult:
        return self._scrubber.scrub(text)

    def scrub_all(self, documents: dict[str, str]) -> CorpusResult:
        out = CorpusResult()
        counts: dict[str, int] = {}
        for name, text in documents.items():
            res = self._scrubber.scrub(text)
            out.results[name] = res
            for k, v in res.manifest.counts.items():
                counts[k] = counts.get(k, 0) + v
        # Unique entities are counted once corpus-wide from the shared registry.
        unique: dict[str, int] = {}
        for etype, bucket in self.registry._tokens.items():  # noqa: SLF001
            if bucket:
                unique[etype.value] = len(bucket)
        out.combined = RedactionManifest(counts=counts, unique_entities=unique)
        return out
