"""pii-scrubber · CPR Orbital #35 (Season 6)

De-identify qualitative research data — interview transcripts, survey
open-ends, and field notes — by detecting and replacing personally
identifying information with consistent pseudonyms.

Design contract
---------------
* The rule-based core (regex + heuristics + name gazetteer) runs fully
  offline with zero API calls and handles *direct* identifiers: names,
  emails, phones, addresses, URLs, IDs, and organisations.
* The optional LLM layer (``llm.py``) is *on by default* and catches the
  context-dependent *quasi*-identifiers regex cannot see — role+company
  combinations, unique job titles, distinctive personal details. It is
  strictly additive: with no API key (or with ``--no-llm``) the tool falls
  back to the rule-based result and never hard-fails.
* Pseudonymisation is *consistent across a corpus*: the same entity always
  maps to the same token (``Participant 1``, ``[COMPANY_A]``) so the
  analytic relationships in the data survive de-identification.

What this is NOT
----------------
pii-scrubber reduces re-identification risk; it does not eliminate it. It is
not a guarantee of anonymity and not a compliance certification. Human review
is required before any data leaves the room. See the README for the full
framing.
"""

__version__ = "0.1.0"

from .corpus import CorpusScrubber
from .models import (
    Detection,
    EntityType,
    RedactionManifest,
    ScrubConfig,
    ScrubResult,
)
from .scrubber import Scrubber, scrub_text

__all__ = [
    "__version__",
    "Detection",
    "EntityType",
    "RedactionManifest",
    "ScrubConfig",
    "ScrubResult",
    "Scrubber",
    "scrub_text",
    "CorpusScrubber",
]
