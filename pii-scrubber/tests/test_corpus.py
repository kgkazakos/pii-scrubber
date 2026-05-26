"""Tests for corpus-wide scrubbing."""

from pii_scrubber.corpus import CorpusScrubber
from pii_scrubber.models import ScrubConfig


def _cfg():
    return ScrubConfig(use_llm=False)


def test_tokens_consistent_across_documents():
    docs = {
        "doc1.txt": "Acme Inc is great. I'm Sarah Chen.",
        "doc2.txt": "Sarah Chen left Acme Inc last year.",
    }
    cs = CorpusScrubber(config=_cfg())
    out = cs.scrub_all(docs)
    s1 = out.results["doc1.txt"].scrubbed_text
    s2 = out.results["doc2.txt"].scrubbed_text
    # Same org -> same token in both files.
    assert "[COMPANY_A]" in s1 and "[COMPANY_A]" in s2
    # Same person -> same token in both files.
    assert "Participant 1" in s1 and "Participant 1" in s2


def test_combined_manifest_counts_unique_once():
    docs = {
        "a.txt": "Acme Inc. Acme Inc.",
        "b.txt": "Acme Inc again.",
    }
    cs = CorpusScrubber(config=_cfg())
    out = cs.scrub_all(docs)
    man = out.combined.to_dict()
    assert man["counts"]["ORG"] == 3  # three total mentions
    assert man["unique_entities"]["ORG"] == 1  # one unique org corpus-wide


def test_corpus_to_dict_structure():
    cs = CorpusScrubber(config=_cfg())
    out = cs.scrub_all({"a.txt": "Email a@b.com"})
    d = out.to_dict()
    assert "documents" in d and "combined_manifest" in d
    assert "a.txt" in d["documents"]
