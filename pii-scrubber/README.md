# pii-scrubber

**De-identify qualitative research data — interview transcripts, survey open-ends, and field notes — with consistent pseudonyms and a shareable redaction manifest.**

`pii-scrubber` is CPR Orbital tool **#35** (Season 6 · *Pre-study & impact*). The rule-based core runs **fully offline** and handles direct identifiers; an optional LLM layer (on by default) catches the context-dependent quasi-identifiers that pattern matching cannot see.

---

## What it does

- **Detects direct identifiers offline** — names, emails, phone numbers, addresses, URLs, IP addresses, ID/case codes, and organisations — with regex, heuristics, and a name gazetteer. Zero API calls required.
- **Catches quasi-identifiers with an optional LLM layer** — role + organisation combinations, rare job titles, narrowing location specifics, and distinctive personal details. **On by default**, across Claude Opus, Gemini 4 Argon, and GPT-5.5.
- **Pseudonymises consistently across a corpus** — the same entity always maps to the same token (`Participant 1`, `[COMPANY_A]`), so the analytic relationships in your data survive de-identification. A bare "Sarah" attaches to an earlier "Sarah Chen".
- **Produces a shareable redaction manifest** — types and counts only, no original values — safe to attach to a study file as evidence of the de-identification pass.
- **Runs in your pipeline** — `scrub` and `batch` CLI commands, `--json-output` for CI, and an optional Streamlit drop-zone UI.

## What this is *not*

This is the honest part, and it matters most:

- **Not a guarantee of anonymity.** It *reduces* re-identification risk; it does not eliminate it.
- **Not a compliance certification.** It does not certify GDPR/HIPAA/IRB conformance or any legal standard.
- **Not a substitute for human review.** A person must review the output before any data leaves the room. Free text is adversarial; rare combinations slip through.

Treat the output as a strong first pass, not a finished clearance.

---

## Install

```bash
pip install pii-scrubber                 # core (offline) + CLI
pip install "pii-scrubber[llm]"          # + DSPy/LiteLLM for the quasi-identifier layer
pip install "pii-scrubber[ui]"           # + Streamlit UI
```

The LLM layer activates when an API key is present in the environment
(`ANTHROPIC_API_KEY`, `GEMINI_API_KEY` / `GOOGLE_API_KEY`, or `OPENAI_API_KEY`).
With no key — or with `--no-llm` — the tool falls back to the offline core and
never hard-fails.

## Usage

```bash
# Scrub one file, print the result and a manifest
pii-scrubber scrub interview.txt

# Force the fully-offline rule-based path
pii-scrubber scrub interview.txt --no-llm -o interview.clean.txt

# Pin a backend (default is auto: first available key, anthropic > gemini > openai)
pii-scrubber scrub interview.txt --llm-backend anthropic

# Machine-readable JSON for CI
pii-scrubber scrub interview.txt --json-output

# Scrub a whole study directory with corpus-wide consistent tokens
pii-scrubber batch ./study --output-dir ./study_clean

# Which backends are configured?
pii-scrubber backends
```

In Python:

```python
from pii_scrubber import scrub_text, ScrubConfig

result = scrub_text(open("interview.txt").read(), ScrubConfig(use_llm=True))
print(result.scrubbed_text)
print(result.manifest.to_dict())   # types + counts, no originals
```

A reversible key (`token → original`) is **off by default**. Turning it on
(`--reversible`) re-introduces re-identification risk wherever that key is
stored — keep it separate from the scrubbed text and treat it as raw PII.

## UI

```bash
streamlit run pii_scrubber/app.py
```

A drop-zone: paste or upload a transcript, choose options, and get scrubbed text
plus a manifest and a JSON download. DM Mono / DM Sans, consistent with the rest
of the CPR Orbital tools.

## LLM backends

| Backend   | Model string                    |
|-----------|---------------------------------|
| Anthropic | `anthropic/claude-opus-4-7`     |
| Gemini    | `gemini/gemini-4-argon` |
| OpenAI    | `openai/gpt-5.5`                |

Model strings live in `pii_scrubber/llm.py` (`BACKENDS`) — edit them if your
account exposes different names.

---

## Part of the CPR Ecosystem

`pii-scrubber` is one of the **CPR Orbital** tools — open-source research
infrastructure shipped almost daily, alongside the core
[Computational Product Research](https://github.com/kgkazakos) projects.

Related tools:

- [**transcript-cleaner**](https://github.com/kgkazakos/transcript-cleaner) — fixes diarization and turn-taking before you scrub. Natural upstream pair.
- [**survey-cleaner**](https://github.com/kgkazakos/survey-cleaner) — removes speeders and gibberish open-ends; scrub the survivors.
- [**saturation-meter**](https://github.com/kgkazakos/saturation-meter) — estimate thematic saturation on de-identified transcripts.

`pii-scrubber` is text/tabular only and intentionally distinct from the
multimodal `pii-shield` work in the wider CPR roadmap.

## License

MIT © 2026 Kostas Kazakos
