"""
analysis/llm.py — thin Groq client for PitWall's AI features.

Design constraints, all deliberate:

  * No SDK. Groq speaks an OpenAI-compatible REST endpoint, so a single
    requests.post keeps requirements.txt unchanged and removes a dependency
    that could break a deploy.

  * Non-blocking. Every entry point returns (text, error) and never raises
    into a Streamlit page. If the key is missing or Groq is down, the feature
    shows "AI unavailable" and the rest of the app keeps working.

  * Key from st.secrets only. Never a literal, never committed. Falls back to
    an environment variable for local CLI use (build-digest runs outside
    Streamlit, where st.secrets does not exist).

  * Strict RAG. The system prompt forbids outside knowledge. The model angit add pages/1_Predictions.py run.py
git commit -m "Wave 5 feature 1: LLM client, explain-prediction, build-digest command"
git pushswers
    from the context block or says it doesn't have the data. This is enforced
    by instruction, not code — so the caller must still treat output as
    advisory, and the UI says so.
"""

import os
import json

import requests

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "gpt-oss-120b"
TIMEOUT_S  = 30

STRICT_RAG_SYSTEM = (
    "You are the PitWall race engineer, explaining a data-driven Formula 1 "
    "2026 analytics model to a knowledgeable fan.\n\n"
    "Rules you must follow:\n"
    "1. Answer ONLY from the DATA block provided in the user message. Treat it "
    "as the complete truth about this season.\n"
    "2. If the data does not contain what's needed to answer, say so plainly — "
    "e.g. 'The model doesn't track that.' Never invent lap times, positions, "
    "quotes, or events.\n"
    "3. Do not use knowledge of real-world F1 results from your training. This "
    "is an alternate 2026 season; only the DATA block is real here.\n"
    "4. Be concise and specific. Cite the numbers from the data. No preamble, "
    "no 'as an AI'.\n"
    "5. Never present a prediction as a certainty. It's a model output with an "
    "uncertainty range."
)


def _api_key():
    """st.secrets when inside Streamlit, else env var for CLI use."""
    try:
        import streamlit as st
        if "GROQ_API_KEY" in st.secrets:
            return st.secrets["GROQ_API_KEY"]
    except Exception:
        pass
    return os.environ.get("GROQ_API_KEY")


def available():
    """True if a key is configured. Lets a page hide AI UI entirely."""
    return bool(_api_key())


def ask(user_content, system=STRICT_RAG_SYSTEM, temperature=0.3, max_tokens=700):
    """
    Single completion. Returns (text, error): exactly one is non-None.

    error is a short, user-safe string — never a raw exception or stack.
    """
    key = _api_key()
    if not key:
        return None, "AI features need a GROQ_API_KEY in Streamlit secrets."

    try:
        r = requests.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {key}",
                     "Content-Type": "application/json"},
            json={
                "model":       GROQ_MODEL,
                "temperature": temperature,
                "max_tokens":  max_tokens,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user",   "content": user_content},
                ],
            },
            timeout=TIMEOUT_S,
        )
    except requests.Timeout:
        return None, "The AI request timed out. Try again in a moment."
    except requests.RequestException:
        return None, "Couldn't reach the AI service. Try again later."

    if r.status_code == 401:
        return None, "The AI key was rejected. Check GROQ_API_KEY in secrets."
    if r.status_code == 429:
        return None, "AI rate limit reached. Give it a minute and retry."
    if r.status_code >= 400:
        return None, f"AI service error ({r.status_code}). Try again later."

    try:
        return r.json()["choices"][0]["message"]["content"].strip(), None
    except (KeyError, IndexError, json.JSONDecodeError):
        return None, "The AI returned an unexpected response. Try again."


# ─────────────────────────────────────────────
#  Feature: explain one prediction
# ─────────────────────────────────────────────

def _row_line(r, pos):
    note = "; ".join(r.get("regulation_notes", [])) or "none"
    return (
        f"P{pos} {r['driver_code']} ({r['team']}, {r['pu_name']} PU): "
        f"predicted {r['predicted_delta_s']:+.3f}s vs the fastest car, "
        f"range [{r['delta_range_low']:+.2f}, {r['delta_range_high']:+.2f}], "
        f"model confidence {r['confidence']:.0%}, "
        f"built from {r.get('n_races_used', '?')} sessions. "
        f"Regulation notes: {note}"
    )


def explain_prediction(pred, driver_code):
    """
    Plain-English 'why is this driver here' for one grid row.
    Returns (text, error).
    """
    rows = pred.get("predictions", [])
    idx  = next((i for i, r in enumerate(rows)
                 if r["driver_code"] == driver_code), None)
    if idx is None:
        return None, "That driver isn't in this prediction."

    me   = rows[idx]
    pos  = idx + 1
    near = [(rows[j], j + 1) for j in (idx - 1, idx + 1) if 0 <= j < len(rows)]

    ctx_lines = [
        f"SESSION: {pred.get('circuit_name')} 2026, "
        f"{pred.get('pred_type', 'quali')} prediction (round {pred.get('race_round')}).",
        f"Circuit type: {pred.get('circuit_type')}.",
        "Method: " + " | ".join(pred.get("methodology_notes", [])),
        "",
        "THE DRIVER IN QUESTION:",
        _row_line(me, pos),
        "",
        "FOR CONTEXT, THE FASTEST CAR:",
        _row_line(rows[0], 1),
    ]
    if near:
        ctx_lines.append("")
        ctx_lines.append("CARS DIRECTLY AROUND THEM:")
        ctx_lines.extend(_row_line(r, p) for r, p in near)

    prompt = (
        "DATA:\n" + "\n".join(ctx_lines) + "\n\n"
        f"Explain in 2-4 sentences why the model places {me['driver_code']} "
        f"at P{pos} for this session. Reference the specific gap, the "
        f"confidence, and any relevant regulation note. If a note says an "
        f"upgrade is incoming, add that the prediction may understate them."
    )
    return ask(prompt, max_tokens=350)


# =============================================================
#  Season digest — the RAG context every AI feature reads first
# =============================================================
#
#  A compact (~2-3k token) plain-text summary of the whole season: standings,
#  per-team pace, teammate records, PU/ADUO state, and the upgrade timeline.
#  Groq has never seen the data, so this packet is injected before every
#  question. It is a COMMITTED artifact built by `python run.py build-digest`,
#  regenerated each weekend alongside `predict`, exactly like telemetry
#  extracts. Building it live on every page load would be slower and burn the
#  free tier, and the data only changes on race weekends.

import os as _os

DIGEST_PATH = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "store", "season_digest.txt")


def build_season_digest():
    """
    Assemble the digest text from stored data. Pure data assembly, no LLM.
    Returns the digest string; the caller writes it to disk.
    """
    import numpy as np
    from collections import defaultdict
    from app.data_loader import (get_fingerprints, get_constructor_standings,
                                 get_driver_standings, get_upgrade_timeline,
                                 teammate_stats)
    from config import CARS, CIRCUITS, PU_ADUO_UPGRADES

    fps = get_fingerprints()
    out = ["PITWALL 2026 SEASON DIGEST",
           "(Model-derived summary. All figures come from stored session data.)",
           ""]

    # ---- Constructor standings ----
    cons = get_constructor_standings()
    if cons:
        out.append("CONSTRUCTOR STANDINGS:")
        for row in cons:
            out.append(f"  P{row['pos']} {row['team']}: {row['points']:.0f} pts, "
                       f"{row['wins']} wins")
        out.append("")

    # ---- Driver standings (top 12) ----
    drv = get_driver_standings()
    if drv:
        out.append("DRIVER STANDINGS (top 12):")
        for row in drv[:12]:
            out.append(f"  P{row['pos']} {row['name']} ({row['team']}): "
                       f"{row['points']:.0f} pts")
        out.append("")

    # ---- Per-team qualifying pace (median gap to pole) ----
    gaps = defaultdict(list)
    for fp in fps:
        if fp.session_type in ("Q", "SQ") and fp.lap_time_gap_pct is not None:
            gaps[fp.team].append(fp.lap_time_gap_pct)
    if gaps:
        out.append("QUALIFYING PACE (median % off session-fastest, lower = quicker):")
        for team in sorted(gaps, key=lambda t: float(np.median(gaps[t]))):
            out.append(f"  {team}: {float(np.median(gaps[team])):.3f}%")
        out.append("")

    # ---- Teammate qualifying battles ----
    team_drivers = defaultdict(set)
    for fp in fps:
        if fp.session_type in ("Q", "SQ"):
            team_drivers[fp.team].add(fp.driver_code)
    out.append("TEAMMATE QUALIFYING RECORDS (median gap, head-to-head):")
    for team, ds in sorted(team_drivers.items()):
        ds = sorted(ds)
        if len(ds) != 2:
            continue
        ts = teammate_stats(fps, ds[0], ds[1])
        if ts["total"] == 0:
            continue
        faster = ds[0] if ts["med_gap_s"] <= 0 else ds[1]
        slower = ds[1] if faster == ds[0] else ds[0]
        w = (ts["d1_wins"], ts["d2_wins"]) if faster == ds[0] else (ts["d2_wins"], ts["d1_wins"])
        out.append(f"  {team}: {faster} ahead of {slower} by "
                   f"{abs(ts['med_gap_s']):.3f}s, H2H {w[0]}-{w[1]} over {ts['total']} sessions")
    out.append("")

    # ---- Power units and ADUO state ----
    pu_teams = defaultdict(set)
    for c in CARS.values():
        pu = c.get("pu") or c.get("pu_name")
        if pu:
            pu_teams[pu].add(c["team"])
    out.append("POWER UNITS AND ADUO UPGRADE STATE:")
    for pu, teams in sorted(pu_teams.items()):
        line = f"  {pu} (supplies {', '.join(sorted(teams))})"
        upg = PU_ADUO_UPGRADES.get(pu)
        if upg is None:
            line += ": benchmark PU, no ADUO allocation"
        elif upg.get("round") is None:
            line += ": ADUO allocated but NOT yet deployed"
        else:
            line += f": ADUO upgrade deployed at round {upg['round']}"
        out.append(line)
    out.append("")

    # ---- Upgrade timeline (confirmed only, chronological) ----
    ups = [u for u in get_upgrade_timeline() if not u["incoming"]]
    if ups:
        out.append("CONFIRMED UPGRADE TIMELINE:")
        for u in sorted(ups, key=lambda x: x["round"]):
            tag = f" [{u['pu']} PU]" if u.get("pu") else ""
            out.append(f"  R{u['round']} {u['team']}{tag}: {u.get('headline', '')}")
        out.append("")

    return "\n".join(out)


def load_season_digest():
    """Read the committed digest, or a short fallback if it hasn't been built."""
    try:
        with open(DIGEST_PATH, encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ("No season digest has been generated yet. "
                "Run `python run.py build-digest` and commit store/season_digest.txt.")
