"""Tests for consistent pseudonymisation."""

from pii_scrubber.models import Detection, EntityType, Source
from pii_scrubber.pseudonymizer import Registry, _alpha_label, normalise


def test_normalise():
    assert normalise("  Acme, Inc. ") == "acme, inc"
    assert normalise("ACME") == "acme"


def test_alpha_label():
    assert _alpha_label(0) == "A"
    assert _alpha_label(25) == "Z"
    assert _alpha_label(26) == "AA"


def test_same_entity_same_token():
    r = Registry()
    t1 = r.token_for(EntityType.ORG, "Acme")
    t2 = r.token_for(EntityType.ORG, "acme")  # case-insensitive
    assert t1 == t2 == "[COMPANY_A]"


def test_different_entities_different_tokens():
    r = Registry()
    a = r.token_for(EntityType.ORG, "Acme")
    b = r.token_for(EntityType.ORG, "Globex")
    assert a == "[COMPANY_A]"
    assert b == "[COMPANY_B]"


def test_person_participant_style():
    r = Registry(person_style="participant")
    assert r.token_for(EntityType.PERSON, "Sarah Chen") == "Participant 1"
    assert r.token_for(EntityType.PERSON, "Michael") == "Participant 2"


def test_person_tag_style():
    r = Registry(person_style="tag")
    assert r.token_for(EntityType.PERSON, "Sarah Chen") == "[PERSON_1]"


def test_alias_first_name_maps_to_full_name():
    r = Registry()
    full = r.token_for(EntityType.PERSON, "Sarah Chen")
    bare = r.token_for(EntityType.PERSON, "Sarah")
    assert full == bare


def test_assign_orders_full_names_first():
    dets = [
        Detection(EntityType.PERSON, 40, 45, "Sarah", Source.GAZETTEER),
        Detection(EntityType.PERSON, 0, 10, "Sarah Chen", Source.GAZETTEER),
    ]
    r = Registry()
    r.assign(dets)
    tokens = {d.original: d.token for d in dets}
    assert tokens["Sarah"] == tokens["Sarah Chen"] == "Participant 1"


def test_key_records_original():
    r = Registry()
    tok = r.token_for(EntityType.EMAIL, "a@b.com")
    assert r.key[tok] == "a@b.com"
