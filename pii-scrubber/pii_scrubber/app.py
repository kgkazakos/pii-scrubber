"""Streamlit UI for pii-scrubber — a de-identification drop-zone.

Run with:  streamlit run pii_scrubber/app.py

Paste or upload a transcript / open-ends / field notes, choose options in the
sidebar, and get scrubbed text plus a redaction manifest. The rule-based core
runs offline; the LLM layer is on by default and activates when an API key is
present in the environment.
"""

from __future__ import annotations

import json

import streamlit as st

from pii_scrubber import __version__
from pii_scrubber.llm import available_backends, default_backend
from pii_scrubber.models import ScrubConfig
from pii_scrubber.scrubber import Scrubber

st.set_page_config(page_title="pii-scrubber", page_icon="🛡", layout="wide")

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Mono:wght@400;500&family=DM+Sans:opsz,wght@9..40,400;9..40,500;9..40,700&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.block-container { padding-top: 2.4rem; max-width: 1180px; }
h1, h2, h3 { font-family: 'DM Sans', sans-serif; font-weight: 700; letter-spacing: -0.01em; }
code, .mono, pre, textarea { font-family: 'DM Mono', monospace !important; }
.cpr-tag { font-family: 'DM Mono', monospace; font-size: 0.72rem; letter-spacing: 0.08em;
           text-transform: uppercase; color: #8a8a8a; }
.cpr-title { font-size: 2.0rem; margin: 0 0 2px; }
.cpr-sub { color: #5f5f5f; font-size: 0.96rem; margin-bottom: 4px; }
.cpr-note { background: #fbf7ed; border: 1px solid #ecdcb6; border-radius: 8px;
            padding: 10px 14px; font-size: 0.82rem; color: #7a5a18; margin: 10px 0 4px; }
.statcard { border: 1px solid #ececec; border-radius: 12px; padding: 14px 16px; background: #fff; }
.statcard .n { font-family: 'DM Mono', monospace; font-size: 1.7rem; font-weight: 500; color: #16604a; }
.statcard .l { font-size: 0.78rem; color: #777; text-transform: uppercase; letter-spacing: 0.05em; }
.scrubbed { white-space: pre-wrap; font-family: 'DM Mono', monospace; font-size: 0.86rem;
            line-height: 1.55; background: #fafafa; border: 1px solid #ededed;
            border-radius: 10px; padding: 16px 18px; }
.tok { background: #e7f3ee; color: #0f6e56; border-radius: 4px; padding: 0 4px;
       font-weight: 500; }
.tok-q { background: #faeeda; color: #854f0b; }
.footer { color: #9a9a9a; font-size: 0.78rem; margin-top: 26px; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

SAMPLE = """Interviewer: Thanks for joining. Could you introduce yourself?
Sarah: Sure — I'm Sarah Chen, a senior product manager at Globex Pty Ltd. You can reach me at sarah.chen@globex.com or on 0412 998 221.
Interviewer: And how long have you used the product?
Sarah: About two years. I moved to 14 Marlin Avenue last spring, so my commute changed and I started using the mobile app more. My account ID is UX2024-AC91.
Interviewer: Anyone else on your team involved in the decision?
Sarah: My manager, Dr. Okafor, signed off. He's the only person at our Sydney office who handles procurement."""


def _highlight(text: str, tokens: list[str]) -> str:
    safe = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    for tok in sorted(set(tokens), key=len, reverse=True):
        esc = tok.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        cls = "tok tok-q" if esc.startswith("[ROLE") or esc.startswith("[LOCATION") or esc.startswith("[DETAIL") else "tok"
        safe = safe.replace(esc, f'<span class="{cls}">{esc}</span>')
    return safe


# ---- Header ---------------------------------------------------------------
st.markdown('<div class="cpr-tag">CPR Orbital · #35 · Season 6 · Pre-study &amp; impact</div>', unsafe_allow_html=True)
st.markdown('<h1 class="cpr-title">pii-scrubber</h1>', unsafe_allow_html=True)
st.markdown(
    '<div class="cpr-sub">De-identify transcripts, survey open-ends, and field notes — '
    'consistent pseudonyms, a shareable redaction manifest, fully offline core.</div>',
    unsafe_allow_html=True,
)

# ---- Sidebar --------------------------------------------------------------
with st.sidebar:
    st.markdown("### Options")
    avail = available_backends()
    use_llm = st.toggle("LLM quasi-identifier layer", value=True,
                        help="On by default. Catches role+company combos, rare titles, and "
                             "location/detail specifics the rules miss.")
    backend_choice = "auto"
    if use_llm:
        opts = ["auto"] + ["anthropic", "gemini", "openai"]
        backend_choice = st.selectbox(
            "Backend",
            opts,
            help="Claude Opus / Gemini 4 Argon / GPT-5.5. 'auto' picks the first "
                 "backend with an API key in the environment.",
        )
        if avail:
            st.caption(f"Available: {', '.join(avail)} · default: {default_backend()}")
        else:
            st.caption("No API key detected — the core still runs rule-based only.")
    st.divider()
    scrub_dates = st.checkbox("Also redact dates", value=False)
    person_style = st.radio("Person token", ["participant", "tag"], horizontal=True,
                            help="'Participant 1' or '[PERSON_1]'.")
    st.divider()
    st.caption("Reduces re-identification risk. Not anonymity, not compliance "
               "certification. Human review required before data leaves the room.")

# ---- Input ----------------------------------------------------------------
left, right = st.columns([1, 1])
with left:
    uploaded = st.file_uploader("Upload a .txt / .md / .vtt / .csv", type=["txt", "md", "vtt", "csv"])
    if uploaded is not None:
        text = uploaded.read().decode("utf-8", errors="replace")
    else:
        text = st.text_area("…or paste text", value=SAMPLE, height=320)
    run = st.button("Scrub", type="primary", use_container_width=True)

# ---- Run ------------------------------------------------------------------
if run and text.strip():
    config = ScrubConfig(
        use_llm=use_llm,
        llm_backend=None if backend_choice == "auto" else backend_choice,
        scrub_dates=scrub_dates,
        person_style=person_style,
    )
    result = Scrubber(config=config).scrub(text)
    tokens = [d.token for d in result.detections if d.token]

    with right:
        m = result.manifest.to_dict()
        c1, c2, c3 = st.columns(3)
        for col, n, label in (
            (c1, m["total_redactions"], "Redactions"),
            (c2, m["total_unique_entities"], "Unique entities"),
            (c3, len({d.entity_type.value for d in result.detections}), "PII types"),
        ):
            col.markdown(f'<div class="statcard"><div class="n">{n}</div><div class="l">{label}</div></div>',
                        unsafe_allow_html=True)
        st.markdown("&nbsp;", unsafe_allow_html=True)
        st.markdown("**Redaction manifest**")
        st.dataframe(
            [{"type": k, "redactions": m["counts"].get(k, 0), "unique": m["unique_entities"].get(k, 0)}
             for k in sorted(set(m["counts"]) | set(m["unique_entities"]))],
            use_container_width=True, hide_index=True,
        )

    st.divider()
    tab_text, tab_det, tab_json = st.tabs(["🛡 Scrubbed text", "🔎 Detections", "{ } JSON"])
    with tab_text:
        st.markdown(f'<div class="scrubbed">{_highlight(result.scrubbed_text, tokens)}</div>',
                    unsafe_allow_html=True)
    with tab_det:
        st.dataframe(
            [{"type": d.entity_type.value, "token": d.token, "source": d.source.value,
              "confidence": round(d.confidence, 2)} for d in result.detections],
            use_container_width=True, hide_index=True,
        )
    with tab_json:
        payload = json.dumps(result.to_dict(), indent=2, ensure_ascii=False)
        st.download_button("Download JSON", payload, file_name="scrubbed.json", mime="application/json")
        st.code(payload, language="json")
elif run:
    st.warning("Paste or upload some text first.")

st.markdown(
    f'<div class="footer">pii-scrubber v{__version__} · part of the CPR Orbital series — '
    'open-source research infrastructure shipped almost daily.</div>',
    unsafe_allow_html=True,
)
