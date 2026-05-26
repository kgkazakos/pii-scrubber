"""Tests for the core Scrubber orchestration."""

import warnings
from pathlib import Path

from pii_scrubber.models import Detection, EntityType, ScrubConfig, Source
from pii_scrubber.scrubber import _resolve_overlaps, scrub_text

FIXTURES = Path(__file__).parent / "fixtures"


def _offline_config(**kw):
    return ScrubConfig(use_llm=False, **kw)


def test_scrub_replaces_email_and_phone():
    text = "Email sarah.chen@globex.com or call 0412 998 221."
    res = scrub_text(text, _offline_config())
    assert "sarah.chen@globex.com" not in res.scrubbed_text
    assert "[EMAIL_1]" in res.scrubbed_text
    assert "[PHONE_1]" in res.scrubbed_text


def test_scrub_is_deterministic_offline():
    text = FIXTURES.joinpath("transcript.txt").read_text()
    a = scrub_text(text, _offline_config()).scrubbed_text
    b = scrub_text(text, _offline_config()).scrubbed_text
    assert a == b


def test_consistent_person_token_across_mentions():
    text = "Sarah: hi.\nLater Sarah Chen confirmed it. Sarah signed off."
    res = scrub_text(text, _offline_config())
    # Every Sarah / Sarah Chen mention collapses to one participant token.
    assert res.scrubbed_text.count("Participant 1") >= 2
    assert "Sarah" not in res.scrubbed_text


def test_manifest_counts_and_unique():
    text = "Acme Inc and Acme Inc again, plus Globex Pty Ltd."
    res = scrub_text(text, _offline_config())
    man = res.manifest.to_dict()
    assert man["counts"]["ORG"] == 3
    assert man["unique_entities"]["ORG"] == 2


def test_manifest_to_dict_has_no_originals():
    text = "Email sarah.chen@globex.com now."
    res = scrub_text(text, _offline_config())
    blob = str(res.to_dict())
    assert "sarah.chen@globex.com" not in blob  # not reversible by default


def test_reversible_key_opt_in_records_original():
    text = "Email sarah.chen@globex.com now."
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = scrub_text(text, _offline_config(keep_key=True))
    assert res.reversible
    assert "sarah.chen@globex.com" in res.key.values()
    assert "sarah.chen@globex.com" in str(res.to_dict())


def test_dates_off_by_default():
    text = "Recorded 12/03/2025."
    assert "[DATE_1]" not in scrub_text(text, _offline_config()).scrubbed_text
    assert "[DATE_1]" in scrub_text(text, _offline_config(scrub_dates=True)).scrubbed_text


def test_overlap_resolution_prefers_longer_span():
    # A full email span should beat any sub-span.
    dets = [
        Detection(EntityType.EMAIL, 0, 21, "sarah.chen@globex.com", Source.REGEX),
        Detection(EntityType.PERSON, 0, 5, "sarah", Source.GAZETTEER),
    ]
    kept = _resolve_overlaps(dets)
    assert len(kept) == 1
    assert kept[0].entity_type is EntityType.EMAIL


def test_llm_disabled_by_config_makes_no_calls(monkeypatch):
    # If use_llm is False, llm.find_quasi_identifiers must never run.
    import pii_scrubber.llm as llm

    def boom(*a, **k):  # pragma: no cover - should not be called
        raise AssertionError("LLM should not be called when use_llm=False")

    monkeypatch.setattr(llm, "find_quasi_identifiers", boom)
    res = scrub_text("Plain text with no PII at all.", _offline_config())
    assert res.scrubbed_text == "Plain text with no PII at all."


def test_role_label_speaker_left_intact():
    text = "Interviewer: Welcome.\nSarah: Thanks."
    res = scrub_text(text, _offline_config())
    assert "Interviewer:" in res.scrubbed_text
    assert "Participant 1:" in res.scrubbed_text
