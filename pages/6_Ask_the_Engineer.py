"""Ask the Engineer — one grounded LatentLap answer at a time."""

from __future__ import annotations

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
from app.ui import inject_global_css, page_header, section_header


st.set_page_config(
    page_title="Ask the Engineer — LatentLap",
    page_icon="💬",
    layout="wide",
)
inject_global_css()


page_header(
    "Grounded explanation",
    "Ask the Engineer",
    "Ask about drivers, teams, race weekends, upgrades, predictions, ERS or how LatentLap works. Each answer is rebuilt from committed project evidence rather than a chat history.",
)

if not ai_available():
    st.warning(
        "Ask the Engineer needs a GROQ_API_KEY in Streamlit secrets. "
        "The deterministic analytics remain available everywhere else."
    )
    st.stop()

with st.container(border=True):
    st.markdown("### What this can — and cannot — tell you")
    left, right = st.columns(2, gap="large")
    with left:
        st.markdown(
            """
**Good questions**
- How has Ferrari's pace changed over the last few races?
- Why was Mercedes strong at Monza?
- What major upgrades has McLaren introduced?
- How does LatentLap infer ERS behaviour?
- Why does the Madrid model rank this driver here?
            """
        )
    with right:
        st.markdown(
            """
**Ground rules**
- No live web lookup at question time.
- No invented 2026 race facts from model memory.
- True battery state and exact ERS deployment are not public.
- Stint pace trends are context, not direct tyre-degradation measurements.
- Python and committed data remain the analytical source of truth.
            """
        )

examples = suggest_followups("", limit=3)
if examples:
    section_header(
        "Try one",
        "Start with a real F1 question",
        "Suggested questions change with the evidence currently committed to LatentLap.",
    )
    cols = st.columns(len(examples), gap="medium")
    for col, example in zip(cols, examples):
        with col:
            if st.button(
                example,
                key=f"starter::{example}",
                use_container_width=True,
            ):
                st.session_state["engineer_q"] = example
                st.rerun()

section_header(
    "Ask",
    "One question. One grounded answer.",
    "There is deliberately no visible conversation history: each answer stands on its own evidence.",
)

question = st.text_input(
    "Your question",
    value=st.session_state.get("engineer_q", ""),
    placeholder="How has Ferrari's pace changed over the last few races?",
)

ask_clicked = st.button(
    "Ask the Engineer",
    type="primary",
    use_container_width=False,
)

if ask_clicked and question.strip():
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

    section_header(
        "Answer",
        "LatentLap · Grounded explanation",
        "The language model explains retrieved evidence. It does not create new analytical numbers.",
    )

    rendered_answer = (
        answer
        .replace(r"\[", "$$")
        .replace(r"\]", "$$")
        .replace(r"\(", "$")
        .replace(r"\)", "$")
    )

    with st.container(border=True):
        st.markdown(rendered_answer)

    sources = get_answer_sources(q)
    with st.expander(
        f"Sources & evidence ({len(sources)})"
        if sources
        else "Sources & evidence"
    ):
        if not sources:
            st.caption("No additional source entries were returned for this answer.")
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
        st.markdown("### Explore next")
        cols = st.columns(len(followups), gap="medium")
        for col, followup in zip(cols, followups):
            with col:
                if st.button(
                    followup,
                    key=f"followup::{followup}",
                    use_container_width=True,
                ):
                    st.session_state["engineer_q"] = followup
                    st.rerun()

    st.caption(
        "Reviewed race dossiers may add reported context. Deterministic Python remains "
        "the source of calculated metrics, while inferred, assumed, optimised and predicted "
        "information remains labelled by role."
    )
