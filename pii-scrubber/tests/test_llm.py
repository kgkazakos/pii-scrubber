"""Tests for the optional LLM layer.

These never hit a network. ``_generate`` is monkeypatched, and backend
availability is forced via environment variables.
"""

import json

import pii_scrubber.llm as llm
from pii_scrubber.models import EntityType, Source


def test_backends_map_has_three_models():
    assert set(llm.BACKENDS) == {"anthropic", "gemini", "openai"}
    assert llm.BACKENDS["anthropic"] == "anthropic/claude-opus-4-7"
    assert llm.BACKENDS["gemini"] == "gemini/gemini-3.1-pro-preview"
    assert llm.BACKENDS["openai"] == "openai/gpt-5.5"


def test_available_backends_reads_env(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert llm.available_backends() == []
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert llm.available_backends() == ["openai"]


def test_default_backend_priority(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "y")
    assert llm.default_backend() == "anthropic"  # anthropic has priority


def test_no_backend_returns_empty(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    assert llm.find_quasi_identifiers("any text", []) == []


def test_parse_handles_fenced_json():
    raw = "```json\n[{\"text\": \"a senior PM\", \"type\": \"ROLE\", \"reason\": \"role\"}]\n```"
    items = llm._parse(raw)
    assert items[0]["text"] == "a senior PM"


def test_parse_returns_empty_on_garbage():
    assert llm._parse("not json at all") == []


def test_find_quasi_identifiers_with_mock(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    text = "She is a senior PM at a ride-share startup in a small town."

    payload = json.dumps([
        {"text": "a senior PM at a ride-share startup", "type": "ROLE", "reason": "role+org"},
        {"text": "a small town", "type": "LOCATION_DETAIL", "reason": "location"},
    ])
    monkeypatch.setattr(llm, "_generate", lambda t, model: payload)

    dets = llm.find_quasi_identifiers(text, [])
    assert len(dets) == 2
    assert all(d.source is Source.LLM for d in dets)
    types = {d.entity_type for d in dets}
    assert EntityType.ROLE in types
    assert EntityType.LOCATION_DETAIL in types


def test_llm_phrase_not_in_text_is_skipped(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    monkeypatch.setattr(
        llm, "_generate",
        lambda t, model: json.dumps([{"text": "not present", "type": "DETAIL", "reason": "x"}]),
    )
    assert llm.find_quasi_identifiers("totally different text", []) == []


def test_scrubber_uses_llm_when_available(monkeypatch):
    """End-to-end: a quasi-identifier from the LLM gets pseudonymised."""
    monkeypatch.setenv("GEMINI_API_KEY", "x")
    monkeypatch.setattr(
        llm, "_generate",
        lambda t, model: json.dumps([{"text": "the only data scientist in Hobart",
                                       "type": "ROLE", "reason": "rare role"}]),
    )
    from pii_scrubber.models import ScrubConfig
    from pii_scrubber.scrubber import Scrubber

    text = "He is the only data scientist in Hobart, by the way."
    res = Scrubber(config=ScrubConfig(use_llm=True)).scrub(text)
    assert "the only data scientist in Hobart" not in res.scrubbed_text
    assert "[ROLE_1]" in res.scrubbed_text
