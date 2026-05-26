"""Tests for person-name detection."""

from pii_scrubber import names
from pii_scrubber.models import ScrubConfig

ROLES = ScrubConfig().role_labels


def test_speaker_label_detected():
    text = "Sarah: I think it's fine.\nMichael: Agreed."
    dets = names.find_speaker_labels(text, ROLES)
    surfaces = {d.original for d in dets}
    assert "Sarah" in surfaces
    assert "Michael" in surfaces


def test_role_label_not_flagged():
    text = "Interviewer: Welcome.\nModerator: Let's begin."
    dets = names.find_speaker_labels(text, ROLES)
    assert dets == []


def test_titled_name_detected():
    text = "My manager, Dr. Okafor, signed off."
    dets = names.find_titled_names(text)
    assert any("Okafor" in d.original for d in dets)


def test_gazetteer_first_and_last():
    text = "I spoke to Sarah Chen yesterday."
    dets = names.find_gazetteer_names(text)
    assert any(d.original == "Sarah Chen" for d in dets)


def test_gazetteer_bare_first_name():
    text = "Then Priya joined the call."
    dets = names.find_gazetteer_names(text)
    assert any(d.original == "Priya" for d in dets)


def test_unknown_capitalised_word_not_flagged():
    text = "The Quarterly Roadmap was approved."
    dets = names.find_gazetteer_names(text)
    assert dets == []


def test_find_persons_combines_sources():
    text = "Sarah: Hi. My colleague Dr. Okafor and Michael are here."
    dets = names.find_persons(text, ROLES)
    surfaces = {d.original for d in dets}
    assert "Sarah" in surfaces
    assert any("Okafor" in s for s in surfaces)
    assert "Michael" in surfaces
