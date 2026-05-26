"""Tests for the regex/heuristic detectors."""

from pii_scrubber import patterns
from pii_scrubber.models import EntityType


def _types(dets):
    return {d.entity_type for d in dets}


def test_email_detection():
    dets = patterns.find_emails("Reach me at sarah.chen@globex.com please.")
    assert len(dets) == 1
    assert dets[0].original == "sarah.chen@globex.com"
    assert dets[0].entity_type is EntityType.EMAIL


def test_url_detection_excludes_email():
    dets = patterns.find_urls("Visit https://globex.com/procurement now.")
    assert len(dets) == 1
    assert dets[0].original.startswith("https://")


def test_url_does_not_match_email_domain():
    # An email string should not also surface as a URL.
    dets = patterns.find_urls("contact me at user@example.org")
    assert dets == []


def test_ip_detection():
    dets = patterns.find_ips("Server at 198.51.100.23 logged it.")
    assert len(dets) == 1
    assert dets[0].original == "198.51.100.23"


def test_ip_rejects_out_of_range():
    dets = patterns.find_ips("Version 999.999.1.1 is not an IP.")
    assert dets == []


def test_phone_detection():
    dets = patterns.find_phones("Call 0412 998 221 or (415) 555-0199.")
    assert len(dets) >= 1
    for d in dets:
        digits = "".join(c for c in d.original if c.isdigit())
        assert 7 <= len(digits) <= 15


def test_id_detection():
    dets = patterns.find_ids("Participant code UX2024-AC91 and case 482-19-7765.")
    surfaces = {d.original for d in dets}
    assert any("UX2024" in s for s in surfaces)


def test_address_detection():
    dets = patterns.find_addresses("I live at 14 Marlin Avenue these days.")
    assert len(dets) == 1
    assert "Marlin Avenue" in dets[0].original


def test_org_suffix_detection():
    dets = patterns.find_orgs("She works at Globex Pty Ltd and before that Acme Inc.")
    surfaces = {d.original for d in dets}
    assert any("Globex" in s for s in surfaces)
    assert any("Acme" in s for s in surfaces)


def test_org_institution_detection():
    dets = patterns.find_orgs("He studied at the University of Melbourne.")
    assert any("University of Melbourne" in d.original for d in dets)


def test_date_detection():
    dets = patterns.find_dates("Recorded 12/03/2025 and again on March 12, 2025.")
    assert len(dets) == 2
