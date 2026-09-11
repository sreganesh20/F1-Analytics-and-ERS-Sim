"""Ask the Engineer — one grounded answer at a time.

The page is intentionally not a chat transcript. Each question is independently
answered from committed LatentLap data, reviewed race dossiers, prediction
artifacts and deterministic analytics.
"""

import os
import sys

import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.llm import (
    available as ai_available,
    ask_engineer,
    get_answer_sources,
    suggest_followups,
)

st.set_page_config(
    page_title="Ask the Engineer — LatentLap",
    page_icon="💬",
    layout="wide",
)

ACCENT = (
    '<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
    'border-radius:2px;margin-bottom:1rem;"></div>'
)
st.markdown(ACCENT, unsafe_allow_html=True)
st.title("💬 Ask the Engineer")
st.caption(
    "Ask about drivers, teams, race weekends, upgrades, predictions, ERS or "
    "LatentLap's methodology. The answer uses committed LatentLap evidence only; "
    "if the data is not there, the assistant says so instead of filling the gap."
)

if not ai_available():
    st.warning(
        "This page needs a GROQ_API_KEY in the app's secrets. "
        "Once it is set, the grounded explanation layer becomes available."
    )
    st.stop()

with st.expander("What this can answer"):
    st.markdown(
        "**Good questions**\n"
        "- Why was McLaren strong at Zandvoort?\n"
        "- Compare Ferrari and Mercedes recent qualifying pace.\n"
        "- How does LatentLap infer ERS behaviour?\n"
        "- Which upgrades matter for a team's development trend?\n"
        "- Why did a saved prediction miss a particular result?\n\n"
        "**Limits**\n"
        "- It does not use live web search at question time.\n"
        "- It does not invent missing 2026 race facts from model memory.\n"
        "- It cannot see true battery state or exact ERS deployment.\n"
        "- Stint pace trends are context, not direct tyre-degradation measurements."
    )

examples = suggest_followups("", limit=3)
st.markdown("**Try one:**")
cols = st.columns(len(examples))
for col, example in zip(cols, examples):
    if col.button(example, use_container_width=True):
        st.session_state["engineer_q"] = example

question = st.text_input(
    "Your question",
    value=st.session_state.get("engineer_q", ""),
    placeholder="Why was McLaren strong at Zandvoort?",
)

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Reading LatentLap's committed evidence…"):
        answer, err = ask_engineer(question.strip())

    if err:
        st.info(err)
    else:
        st.session_state["engineer_last_q"] = question.strip()
        st.session_state["engineer_last_answer"] = answer

if st.session_state.get("engineer_last_answer"):
    q = st.session_state.get("engineer_last_q", "")
    answer = st.session_state["engineer_last_answer"]

    st.markdown(
        '<div style="border-left:3px solid #FF6B35;padding-left:14px;'
        'margin:14px 0 4px;"><span style="font-size:0.7rem;color:#FF6B35;'
        'font-family:monospace;">LATENTLAP · GROUNDED EXPLANATION</span></div>',
        unsafe_allow_html=True,
    )
    rendered_answer = (
        answer
        .replace(r"\[", "$$")
        .replace(r"\]", "$$")
        .replace(r"\(", "$")
        .replace(r"\)", "$")
    )
    st.markdown(rendered_answer)

    sources = get_answer_sources(q)
    with st.expander("Sources & evidence"):
        for source in sources:
            title = source.get("title", "Source")
            publisher = source.get("publisher")
            url = source.get("url")
            path = source.get("path")
            kind = source.get("kind")
            prefix = f"{publisher} — " if publisher else ""
            if url:
                st.markdown(f"- [{prefix}{title}]({url})")
            elif path:
                st.markdown(f"- `{path}` — {prefix}{title}")
            else:
                label = f"{kind}: " if kind else ""
                st.markdown(f"- {label}{prefix}{title}")

    followups = suggest_followups(q, limit=3)
    if followups:
        st.markdown("**Explore next:**")
        cols = st.columns(len(followups))
        for col, followup in zip(cols, followups):
            if col.button(followup, key=f"followup::{followup}", use_container_width=True):
                st.session_state["engineer_q"] = followup
                st.rerun()

    st.caption(
        "The LLM explains retrieved LatentLap evidence; it does not create new "
        "analytical facts. Reviewed race dossiers can add reported context, while "
        "Python remains the source of calculated metrics."
    )
