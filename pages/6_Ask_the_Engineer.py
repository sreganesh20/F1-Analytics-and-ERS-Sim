"""pages/6_Ask_the_Engineer.py — natural-language questions over the season.

Strict RAG: the model answers only from the season digest plus the specific
session rows retrieved for whatever the question names. It says when the data
doesn't cover something rather than inventing an answer. This is deliberate —
the value is a trustworthy read of the model's own numbers, not a general F1
chatbot.
"""

import os, sys
import streamlit as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analysis.llm import available as ai_available, ask_engineer

st.set_page_config(page_title="Ask the Engineer — PitWall",
                   page_icon="💬", layout="wide")

ACCENT = ('<div style="height:3px;background:linear-gradient(90deg,#FF1E00,#FF6B35);'
          'border-radius:2px;margin-bottom:1rem;"></div>')
st.markdown(ACCENT, unsafe_allow_html=True)
st.title("💬 Ask the Engineer")

if not ai_available():
    st.warning("This page needs a GROQ_API_KEY in the app's secrets. "
               "Once it's set, ask anything about the 2026 season's data.")
    st.stop()

st.caption(
    "Ask about the 2026 season and PitWall answers from its own data — "
    "standings, qualifying pace, teammate battles, power units, and upgrades. "
    "It only knows what the model has measured, so it'll say when something "
    "isn't in the data rather than guess."
)

# What it can and can't answer, so "I don't have that" reads as honesty
# rather than failure.
with st.expander("What this can answer"):
    st.markdown(
        "**Good questions** — grounded in stored data:\n"
        "- How does Ferrari's qualifying pace compare to McLaren's?\n"
        "- Who's winning the teammate battle at Aston Martin?\n"
        "- Which power units have deployed their ADUO upgrade?\n"
        "- How did Hamilton do at Silverstone?\n\n"
        "**It won't answer** — not in the data:\n"
        "- Wet-weather pace, tyre strategy, or lap-by-lap detail (not tracked)\n"
        "- Races that haven't happened yet\n"
        "- Real-world F1 results — this is the model's own 2026, not the real season"
    )

EXAMPLES = [
    "Compare Mercedes and Ferrari qualifying pace",
    "Who leads each teammate battle?",
    "Which power units have upgraded and when?",
    "How has Hamilton performed this season?",
]

st.markdown("**Try one:**")
cols = st.columns(len(EXAMPLES))
for col, ex in zip(cols, EXAMPLES):
    if col.button(ex, use_container_width=True):
        st.session_state["engineer_q"] = ex

question = st.text_input(
    "Your question",
    value=st.session_state.get("engineer_q", ""),
    placeholder="How does Audi's pace compare to the rest of the midfield?",
)

if st.button("Ask", type="primary") and question.strip():
    with st.spinner("Reading the season data…"):
        answer, err = ask_engineer(question)
    if err:
        st.info(err)
    else:
        st.markdown(
            f'<div style="background:#141414;border-left:3px solid #FF6B35;'
            f'border-radius:0 8px 8px 0;padding:14px 18px;margin:10px 0;">'
            f'<div style="font-size:0.86rem;color:#E0E0E0;line-height:1.6;">{answer}</div>'
            f'</div>', unsafe_allow_html=True)
        st.caption("Answered from PitWall's stored season data by an LLM under "
                   "strict grounding. It can still misread — treat it as a "
                   "reading of the numbers, not an oracle.")
