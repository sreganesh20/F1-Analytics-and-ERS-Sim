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

  * Strict RAG. The system prompt forbids outside knowledge. The model 
    from the context block or says it doesn't have the data. This is enforced
    by instruction, not code — so the caller must still treat output as
    advisory, and the UI says so.
"""

import os
import json

import requests

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
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
    "3. This is the REAL 2026 Formula 1 season, but it happened after your "
    "training data ends — so you do not know its results. Anything you think "
    "you remember about 2026 is unreliable. Never fill a gap from memory: if a "
    "name, result or figure is not in the DATA block, say you don't have it.\n"
    "4. Driver codes are three letters. Expand a code to a full name ONLY if "
    "the roster in the DATA block gives that name. Never guess a driver's name "
    "from their code.\n"
    "5. Be concise and specific. Cite the numbers from the data. No preamble, "
    "no 'as an AI'.\n"
    "6. Never present a prediction as a certainty. It's a model output with an "
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


def ask(user_content, system=STRICT_RAG_SYSTEM, temperature=0.3,
        max_tokens=1200, reasoning_effort="low"):
    """
    Single completion. Returns (text, error): exactly one is non-None.

    error is a short, user-safe string — never a raw exception or stack.

    gpt-oss-120b is a reasoning model: it spends tokens on a hidden reasoning
    pass before writing visible content, and max_tokens caps the TOTAL. A tight
    cap can therefore return an empty answer with finish_reason 'length'. So the
    default ceiling is generous and reasoning_effort defaults to 'low' — these
    are short, grounded answers that don't need deep deliberation.
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
                "model":            GROQ_MODEL,
                "temperature":      temperature,
                "max_tokens":       max_tokens,
                "reasoning_effort": reasoning_effort,
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
    return ask(prompt, max_tokens=900)


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
           "(Real 2026 Formula 1 session data from FastF1. Figures are measured, "
           "except where marked as predictions.)",
           ""]

    # ---- Driver roster ----
    # Without this the model has only three-letter codes and invents full names
    # for them: STR became "Stoffel Vandoorne", BOR became "Börje Rikardsson",
    # SAI became "Said Al-Saadi". The numbers were right; the names were fiction.
    out.append("DRIVER ROSTER (code — name — team):")
    for code, car in sorted(CARS.items(), key=lambda kv: kv[1]["team"]):
        out.append(f"  {code} — {car['name']} — {car['team']}")
    out.append("")

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
        f_name = CARS.get(faster, {}).get("name", faster)
        s_name = CARS.get(slower, {}).get("name", slower)
        out.append(f"  {team}: {faster} ({f_name}) ahead of {slower} ({s_name}) by "
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


# =============================================================
#  Feature: auto-generated race commentary
# =============================================================
#
#  Supplements the hand-written data/commentary.json. Reads the real finishing
#  order from the stored race session and asks for a short recap in the same
#  voice. The result is clearly labelled auto-generated on the page — it is a
#  convenience for rounds nobody has written up yet, not a replacement for the
#  editorial entries.

def _race_result_context(race_round):
    """Assemble the real finishing order for one round from the store."""
    import glob
    from app.data_loader import get_fingerprints, driver_name

    fps = [f for f in get_fingerprints()
           if f.race_round == race_round and f.session_type == "R"]
    if not fps:
        return None, None

    def sort_key(f):
        # DNF/NC sink to the bottom; finishers by position
        pos = getattr(f, "finishing_position", None)
        return (pos is None, pos if pos is not None else 999)

    fps.sort(key=sort_key)
    circuit = fps[0].circuit_name if hasattr(fps[0], "circuit_name") else f"Round {race_round}"

    lines = []
    for f in fps:
        pos    = getattr(f, "finishing_position", None)
        grid   = getattr(f, "grid_position", None)
        status = getattr(f, "result_status", "") or ""
        gained = getattr(f, "positions_gained", None)
        posstr = f"P{pos}" if pos else status or "DNF"
        extra  = ""
        if grid and pos:
            move = grid - pos
            if move > 0:   extra = f" (+{move} from P{grid})"
            elif move < 0: extra = f" ({move} from P{grid})"
            else:          extra = f" (held P{grid})"
        elif status and status != "Finished":
            extra = f" ({status})"
        lines.append(f"  {posstr} {f.driver_code} ({f.team}){extra}")

    return circuit, lines


def generate_race_commentary(race_round):
    """
    Draft a race recap for one round from stored results. Returns (dict, error)
    where dict matches the commentary.json schema so it can slot straight in.
    """
    circuit, lines = _race_result_context(race_round)
    if not lines:
        return None, f"No race result stored for round {race_round}."

    prompt = (
        f"DATA — final classification, {circuit} 2026 (round {race_round}):\n"
        + "\n".join(lines) + "\n\n"
        "Write a race recap in this exact style: one punchy headline (max 12 "
        "words), then a 3-4 sentence body. Factual, race-engineer tone, like a "
        "post-race note. Mention the winner, the podium, and the biggest mover "
        "or notable retirement. Use ONLY the classification above — invent no "
        "lap times, no quotes, no incidents not implied by the data.\n\n"
        "Return exactly this format, nothing else:\n"
        "HEADLINE: <the headline>\n"
        "BODY: <the body>"
    )

    text, err = ask(prompt, max_tokens=1400, temperature=0.5)
    if err:
        return None, err

    headline, body = "", text
    for line in text.splitlines():
        if line.upper().startswith("HEADLINE:"):
            headline = line.split(":", 1)[1].strip()
        elif line.upper().startswith("BODY:"):
            body = line.split(":", 1)[1].strip()
    # if the model ran the body across multiple lines after BODY:
    if "BODY:" in text:
        body = text.split("BODY:", 1)[1].strip()

    return {
        "round":    race_round,
        "circuit":  circuit,
        "headline": headline or f"{circuit} race recap",
        "body":     body,
        "tags":     ["auto-generated"],
        "auto":     True,
    }, None


# =============================================================
#  Feature: Ask the F1 Engineer  (whole-season RAG)
# =============================================================
#
#  The season digest gives the model a whole-season overview on every
#  question. On top of that, a lightweight retrieval step scans the question
#  for driver codes, driver surnames, team names and circuits, and appends the
#  specific fingerprint rows for whatever it finds. The model then sees the
#  overview plus the exact rows relevant to the question — never the whole raw
#  dataset, which would be tens of thousands of tokens.

def _entity_index():
    """Build lookup tables once: code->driver, surname->code, team set, circuit set."""
    from config import CARS, CIRCUITS
    codes    = {c: v for c, v in CARS.items()}
    surnames = {}
    for code, v in CARS.items():
        last = v["name"].split()[-1].lower()
        surnames[last] = code
    teams    = {c["team"] for c in CARS.values()}
    circuits = set(CIRCUITS.keys())
    # People say the track, not our config key. Map common venue and country
    # names back to the circuit key so "Zandvoort" or "Monza" resolve.
    aliases = {
        "zandvoort": "Netherlands", "dutch": "Netherlands",
        "monza": "Italy", "italian": "Italy",
        "silverstone": "Britain", "british": "Britain",
        "spa": "Belgium", "belgian": "Belgium",
        "monaco": "Monaco", "monte carlo": "Monaco",
        "montreal": "Canada", "canadian": "Canada",
        "shanghai": "China", "chinese": "China",
        "suzuka": "Japan", "japanese": "Japan",
        "barcelona": "Spain", "spanish": "Spain",
        "red bull ring": "Austria", "austrian": "Austria",
        "hungaroring": "Hungary", "hungarian": "Hungary",
        "miami": "Miami", "imola": "Imola",
        "singapore": "Singapore", "marina bay": "Singapore",
        "interlagos": "Brazil", "brazilian": "Brazil", "sao paulo": "Brazil",
        "las vegas": "LasVegas", "vegas": "LasVegas",
        "abu dhabi": "AbuDhabi", "yas marina": "AbuDhabi",
        "baku": "Azerbaijan", "azerbaijan": "Azerbaijan",
        "melbourne": "Australia", "australian": "Australia",
        "mexico": "Mexico", "mexican": "Mexico", "austin": "Austin", "cota": "Austin",
    }
    return codes, surnames, teams, circuits, aliases


def _retrieve_rows(question, max_rows=60):
    """
    Pull fingerprint rows for entities named in the question.
    Returns a formatted context string (possibly empty).
    """
    from app.data_loader import get_fingerprints
    codes, surnames, teams, circuits, aliases = _entity_index()
    q = question.lower()

    want_codes = {c for c in codes if c.lower() in q.split()
                  or c.lower() in q.replace(",", " ").split()}
    for surname, code in surnames.items():
        if surname in q:
            want_codes.add(code)
    want_teams = {t for t in teams if t.lower() in q}
    want_circuits = {c for c in circuits if c.lower() in q}
    for alias, circuit in aliases.items():
        if alias in q and circuit in circuits:
            want_circuits.add(circuit)

    if not (want_codes or want_teams or want_circuits):
        return ""

    fps = get_fingerprints()
    rows = []
    for f in fps:
        if f.session_type not in ("Q", "SQ", "R", "S"):
            continue
        hit = (f.driver_code in want_codes
               or f.team in want_teams
               or (hasattr(f, "circuit_name") and f.circuit_name in want_circuits))
        if not hit:
            continue
        gap = getattr(f, "lap_time_gap_pct", None)
        pos = getattr(f, "finishing_position", None)
        if f.session_type in ("Q", "SQ") and gap is not None:
            detail = f"gap {gap:+.3f}% to session-fastest"
        elif f.session_type in ("R", "S") and pos is not None:
            status = getattr(f, "result_status", "") or ""
            detail = f"finished P{pos}" + (f" ({status})" if status and status != "Finished" else "")
        else:
            detail = "no comparable result"
        rows.append(
            f"  R{f.race_round} {f.session_type} {f.driver_code} ({f.team}): {detail}")
        if len(rows) >= max_rows:
            break

    if not rows:
        return ""
    return "RELEVANT SESSION ROWS:\n" + "\n".join(rows)


def ask_engineer(question):
    """
    Answer a free-text question about the season under strict RAG.
    Returns (text, error).
    """
    digest = load_season_digest()
    rows   = _retrieve_rows(question)

    context = digest
    if rows:
        context += "\n\n" + rows

    prompt = (
        "DATA:\n" + context + "\n\n"
        f"QUESTION: {question}\n\n"
        "Answer from the DATA only. If the data doesn't cover it, say so.\n"
        "Formatting: when listing several drivers or teams, use a markdown "
        "bulleted list with one item per line — never a run-on paragraph of "
        "dash-separated entries. Use full driver names from the roster, with "
        "the code in brackets on first mention. Keep it under 200 words unless "
        "the question needs more."
    )
    return ask(prompt, max_tokens=1400, temperature=0.3)
