"""Basic usage examples for pii-scrubber.

Run:  python examples/basic_usage.py
Everything here runs fully offline (use_llm=False) so it works with no API key.
"""

from pii_scrubber import CorpusScrubber, ScrubConfig, scrub_text

TRANSCRIPT = """Interviewer: Could you introduce yourself?
Sarah: I'm Sarah Chen, a product manager at Globex Pty Ltd. Email sarah.chen@globex.com.
Interviewer: Thanks. Anyone else involved?
Sarah: My manager Dr. Okafor signed off. Reach me on 0412 998 221."""


def single_document() -> None:
    print("=== Single document ===")
    result = scrub_text(TRANSCRIPT, ScrubConfig(use_llm=False))
    print(result.scrubbed_text)
    print("\nManifest:", result.manifest.to_dict())


def corpus() -> None:
    print("\n=== Corpus (shared tokens) ===")
    docs = {
        "session1.txt": "Sarah Chen at Globex Pty Ltd led the session.",
        "session2.txt": "Globex Pty Ltd renewed; Sarah Chen was thrilled.",
    }
    cs = CorpusScrubber(config=ScrubConfig(use_llm=False))
    out = cs.scrub_all(docs)
    for name, res in out.results.items():
        print(f"\n[{name}]")
        print(res.scrubbed_text)
    print("\nCombined manifest:", out.combined.to_dict())


if __name__ == "__main__":
    single_document()
    corpus()
