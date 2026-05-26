"""Core data models for pii-scrubber.

These dataclasses and enums are the shared vocabulary between the rule-based
core (patterns, names, pseudonymizer, scrubber) and the optional LLM layer.
Everything here is import-light and has no third-party dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class EntityType(str, Enum):
    """A category of personally identifying information.

    Direct identifiers are found by the offline rule-based core. Quasi
    identifiers (ROLE, LOCATION_DETAIL, DETAIL) are typically surfaced by the
    optional LLM layer because they are context dependent.
    """

    PERSON = "PERSON"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    ADDRESS = "ADDRESS"
    ORG = "ORG"
    URL = "URL"
    IP = "IP"
    ID = "ID"
    DATE = "DATE"
    # Quasi-identifiers — mostly LLM-surfaced.
    ROLE = "ROLE"
    LOCATION_DETAIL = "LOCATION_DETAIL"
    DETAIL = "DETAIL"

    @property
    def is_quasi(self) -> bool:
        return self in {EntityType.ROLE, EntityType.LOCATION_DETAIL, EntityType.DETAIL}


class Source(str, Enum):
    """Where a detection came from."""

    REGEX = "regex"
    HEURISTIC = "heuristic"
    GAZETTEER = "gazetteer"
    LLM = "llm"


# Token templates per entity type. PERSON and ORG use research-friendly,
# human-readable tokens; everything else uses a bracketed type tag. The label
# field is filled by the pseudonymizer (e.g. "Participant 1", "[COMPANY_A]").
TOKEN_STYLE: dict[EntityType, str] = {
    EntityType.PERSON: "Participant {n}",
    EntityType.ORG: "[COMPANY_{alpha}]",
    EntityType.EMAIL: "[EMAIL_{n}]",
    EntityType.PHONE: "[PHONE_{n}]",
    EntityType.ADDRESS: "[ADDRESS_{n}]",
    EntityType.URL: "[URL_{n}]",
    EntityType.IP: "[IP_{n}]",
    EntityType.ID: "[ID_{n}]",
    EntityType.DATE: "[DATE_{n}]",
    EntityType.ROLE: "[ROLE_{n}]",
    EntityType.LOCATION_DETAIL: "[LOCATION_{n}]",
    EntityType.DETAIL: "[DETAIL_{n}]",
}


@dataclass
class Detection:
    """A single span of text identified as PII.

    Attributes:
        entity_type: The category of identifier.
        start: Inclusive character offset into the *original* text.
        end: Exclusive character offset into the *original* text.
        original: The matched surface text.
        source: Which subsystem produced the detection.
        token: The replacement token (filled by the pseudonymizer).
        confidence: 0–1 confidence; rule-based detections default to 1.0.
        note: Optional rationale (used by the LLM layer).
    """

    entity_type: EntityType
    start: int
    end: int
    original: str
    source: Source = Source.REGEX
    token: str | None = None
    confidence: float = 1.0
    note: str | None = None

    @property
    def length(self) -> int:
        return self.end - self.start

    def overlaps(self, other: Detection) -> bool:
        return self.start < other.end and other.start < self.end

    def to_dict(self, *, reveal: bool = False) -> dict:
        """Serialise a detection.

        By default the original surface text is *not* included — the manifest
        and JSON output are safe to share. Pass ``reveal=True`` only when the
        caller has explicitly opted into a reversible key.
        """
        out = {
            "entity_type": self.entity_type.value,
            "start": self.start,
            "end": self.end,
            "token": self.token,
            "source": self.source.value,
            "confidence": round(self.confidence, 3),
        }
        if self.note:
            out["note"] = self.note
        if reveal:
            out["original"] = self.original
        return out


@dataclass
class RedactionManifest:
    """A shareable summary of what was redacted — types and counts only.

    Contains no original values, so it is safe to attach to a study file or
    hand to a reviewer as evidence of the de-identification pass.
    """

    counts: dict[str, int] = field(default_factory=dict)
    unique_entities: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    @property
    def total_unique(self) -> int:
        return sum(self.unique_entities.values())

    def to_dict(self) -> dict:
        return {
            "total_redactions": self.total,
            "total_unique_entities": self.total_unique,
            "counts": dict(sorted(self.counts.items())),
            "unique_entities": dict(sorted(self.unique_entities.items())),
        }


@dataclass
class ScrubConfig:
    """Runtime configuration for a scrub pass."""

    # Which entity types to detect. Defaults to the safe direct-identifier set
    # plus organisations. DATE is opt-in because dates are often analytically
    # meaningful and only sometimes identifying.
    enabled_types: set[EntityType] = field(
        default_factory=lambda: {
            EntityType.PERSON,
            EntityType.EMAIL,
            EntityType.PHONE,
            EntityType.ADDRESS,
            EntityType.ORG,
            EntityType.URL,
            EntityType.IP,
            EntityType.ID,
        }
    )
    scrub_dates: bool = False
    # Person token style: "participant" -> "Participant 1", "tag" -> "[PERSON_1]".
    person_style: str = "participant"
    # Treat these speaker labels as roles, not participant names (left intact).
    role_labels: set[str] = field(
        default_factory=lambda: {
            "interviewer",
            "moderator",
            "facilitator",
            "researcher",
            "respondent",
            "participant",
            "interviewee",
            "speaker",
            "host",
            "narrator",
            "note",
            "notes",
        }
    )
    # LLM enrichment is ON BY DEFAULT. Set use_llm=False or pass --no-llm to
    # force the fully-offline rule-based path.
    use_llm: bool = True
    llm_backend: str | None = None  # None => auto-select first available
    # Reversible key: keep the token->original mapping. OFF by default; turning
    # this on re-introduces re-identification risk wherever the key is stored.
    keep_key: bool = False

    def __post_init__(self) -> None:
        if self.scrub_dates:
            self.enabled_types = set(self.enabled_types) | {EntityType.DATE}


@dataclass
class ScrubResult:
    """The output of scrubbing a single document."""

    original_text: str
    scrubbed_text: str
    detections: list[Detection] = field(default_factory=list)
    manifest: RedactionManifest = field(default_factory=RedactionManifest)
    # token -> original. Populated only when ScrubConfig.keep_key is True.
    key: dict[str, str] = field(default_factory=dict)

    @property
    def reversible(self) -> bool:
        return bool(self.key)

    def to_dict(self) -> dict:
        reveal = self.reversible
        out = {
            "scrubbed_text": self.scrubbed_text,
            "manifest": self.manifest.to_dict(),
            "detections": [d.to_dict(reveal=reveal) for d in self.detections],
            "reversible": self.reversible,
        }
        if self.reversible:
            out["key"] = dict(self.key)
        return out
