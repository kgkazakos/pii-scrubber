"""Consistent pseudonymisation.

The registry maps a *normalised entity value* to a stable token, so the same
entity always becomes the same token — within a document and, when the registry
is shared, across a whole corpus. This preserves analytic relationships: every
mention of "Acme" becomes ``[COMPANY_A]`` everywhere, so you can still reason
about which quotes refer to the same organisation.

Aliases let a bare first name attach to a previously-seen full name
("Sarah Chen" -> Participant 1, then later "Sarah" -> Participant 1).
"""

from __future__ import annotations

import re
import string

from .models import Detection, EntityType

_WS_RE = re.compile(r"\s+")


def normalise(value: str) -> str:
    """Case/space/punctuation-insensitive key for matching the same entity."""
    value = value.strip().lower()
    value = value.strip(string.punctuation + " ")
    return _WS_RE.sub(" ", value)


def _alpha_label(n: int) -> str:
    """0 -> A, 1 -> B, ... 25 -> Z, 26 -> AA, ..."""
    out = ""
    n += 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        out = chr(ord("A") + rem) + out
    return out


class Registry:
    """Assigns and remembers tokens for entities, shared across documents."""

    def __init__(self, person_style: str = "participant") -> None:
        self.person_style = person_style
        # (type) -> { normalised value -> token }
        self._tokens: dict[EntityType, dict[str, str]] = {}
        # (type) -> running counter
        self._counters: dict[EntityType, int] = {}
        # token -> original (canonical surface form) for the reversible key
        self.key: dict[str, str] = {}
        # alias normalised-value -> canonical normalised-value (PERSON only)
        self._aliases: dict[str, str] = {}

    # -- token minting -----------------------------------------------------
    def _mint(self, etype: EntityType) -> str:
        idx = self._counters.get(etype, 0)
        self._counters[etype] = idx + 1
        if etype is EntityType.PERSON and self.person_style == "participant":
            return f"Participant {idx + 1}"
        if etype is EntityType.ORG:
            return f"[COMPANY_{_alpha_label(idx)}]"
        if etype is EntityType.PERSON:
            return f"[PERSON_{idx + 1}]"
        return f"[{etype.value}_{idx + 1}]"

    def _canonical(self, etype: EntityType, norm: str) -> str:
        if etype is EntityType.PERSON and norm in self._aliases:
            return self._aliases[norm]
        return norm

    def token_for(self, etype: EntityType, value: str) -> str:
        norm = normalise(value)
        canon = self._canonical(etype, norm)
        bucket = self._tokens.setdefault(etype, {})
        if canon in bucket:
            return bucket[canon]
        token = self._mint(etype)
        bucket[canon] = token
        self.key[token] = value
        # Register first/last-name aliases for people.
        if etype is EntityType.PERSON:
            parts = canon.split()
            if len(parts) >= 2:
                for part in (parts[0], parts[-1]):
                    if len(part) > 1:
                        self._aliases.setdefault(part, canon)
        return token

    def assign(self, detections: list[Detection]) -> None:
        """Fill ``token`` on each detection in place.

        Full-name PERSON detections are processed before bare names so the
        alias map is populated first.
        """
        def sort_key(d: Detection) -> tuple:
            is_person = d.entity_type is EntityType.PERSON
            return (0 if is_person else 1, -d.length if is_person else d.start)

        for d in sorted(detections, key=sort_key):
            d.token = self.token_for(d.entity_type, d.original)
