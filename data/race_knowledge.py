"""Committed race-knowledge access for LatentLap.

External race context lives in reviewed dossier JSON files with source_refs.
Deterministic performance evidence is built only from committed session/prediction
artifacts. Query time never reaches the live web.
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
KNOWLEDGE_DIR = ROOT / "data" / "race_dossiers"
PREDICTION_DIR = ROOT / "store" / "predictions"
SESSION_ORDER = ("SQ", "S", "Q", "R")


def _dossier_path(year: int, race_round: int) -> Path | None:
    if not KNOWLEDGE_DIR.exists():
        return None
    matches = sorted(KNOWLEDGE_DIR.glob(f"{year}_R{race_round:02d}_*.json"))
    return matches[0] if matches else None


def list_dossiers(year: int = 2026, approved_only: bool = True) -> list[dict]:
    rows = []
    if not KNOWLEDGE_DIR.exists():
        return rows
    for path in sorted(KNOWLEDGE_DIR.glob(f"{year}_R*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if approved_only and data.get("review_status") != "approved":
            continue
        rows.append(
            {
                "round": data.get("metadata", {}).get("round"),
                "circuit": data.get("metadata", {}).get("circuit"),
                "review_status": data.get("review_status"),
                "path": str(path),
            }
        )
    return rows


def load_dossier(
    race_round: int,
    year: int = 2026,
    *,
    approved_only: bool = True,
    hydrate_snapshot: bool = True,
) -> dict | None:
    path = _dossier_path(year, race_round)
    if path is None:
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if approved_only and data.get("review_status") != "approved":
        return None
    if hydrate_snapshot:
        data = dict(data)
        data["performance_snapshot"] = build_performance_snapshot(race_round, year)
    return data


def _safe_float(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if np.isfinite(value) else None


def _fp_rows(year: int, race_round: int, session: str):
    from data.race_store import load_fingerprints

    rf = load_fingerprints(year, race_round, session)
    return [] if rf is None else list(rf.fingerprints)


def _session_snapshot(year: int, race_round: int, session: str) -> dict | None:
    fps = _fp_rows(year, race_round, session)
    if not fps:
        return None

    pace = [
        fp for fp in fps
        if _safe_float(getattr(fp, "lap_time_gap_pct", None)) is not None
    ]
    pace.sort(key=lambda fp: fp.lap_time_gap_pct)

    team_gaps = defaultdict(list)
    for fp in pace:
        team_gaps[fp.team].append(float(fp.lap_time_gap_pct))
    team_pace = [
        {
            "team": team,
            "median_gap_pct": round(float(np.median(values)), 4),
            "drivers_sampled": len(values),
        }
        for team, values in team_gaps.items()
    ]
    team_pace.sort(key=lambda row: row["median_gap_pct"])

    result_rows = []
    if session in ("R", "S"):
        from config import lineup_for_round
        from data.race_store import load_session_results

        official = load_session_results(year, race_round, session)
        lineup = lineup_for_round(race_round)
        if official:
            for driver, row in official.items():
                pos = row.get("finishing_position")
                status = row.get("result_status", "") or ""
                status_l = status.strip().lower()
                completed = (
                    not status
                    or status_l in {"finished", "lapped", "classified"}
                    or status_l.startswith("finished")
                    or status_l.startswith("+")
                )
                result_rows.append(
                    {
                        "driver": driver,
                        "name": lineup.get(driver, {}).get("name", driver),
                        "team": lineup.get(driver, {}).get("team", "Unknown"),
                        "position": int(pos) if pos is not None else None,
                        "status": status,
                        "completed": completed,
                        "grid": row.get("grid_position"),
                        "laps_completed": row.get("laps_completed"),
                        "has_representative_pace": any(
                            fp.driver_code == driver for fp in fps
                        ),
                    }
                )
        else:
            for fp in fps:
                pos = getattr(fp, "finishing_position", None)
                result_rows.append(
                    {
                        "driver": fp.driver_code,
                        "name": lineup.get(fp.driver_code, {}).get("name", fp.driver_code),
                        "team": fp.team,
                        "position": int(pos) if pos is not None else None,
                        "status": getattr(fp, "result_status", "") or "",
                        "completed": bool(getattr(fp, "completed_race", True)),
                        "grid": getattr(fp, "grid_position", None),
                        "laps_completed": getattr(fp, "laps_completed", None),
                        "has_representative_pace": True,
                    }
                )
        result_rows.sort(
            key=lambda row: (
                row["position"] is None,
                row["position"] if row["position"] is not None else 999,
            )
        )

    return {
        "session": session,
        "n_drivers_with_pace": len(fps),
        "n_official_results": len(result_rows) if result_rows else len(fps),
        "pace_reference_driver": pace[0].driver_code if pace else None,
        "top_pace": [
            {
                "driver": fp.driver_code,
                "team": fp.team,
                "gap_pct": round(float(fp.lap_time_gap_pct), 4),
                "lap_time_s": round(float(fp.lap_time_s), 4)
                if _safe_float(getattr(fp, "lap_time_s", None)) is not None
                else None,
            }
            for fp in pace[:8]
        ],
        "team_pace": team_pace,
        "results": result_rows,
        "race_telemetry_comparability": (
            "For R/S, representative pace is comparable only at the aggregate lap-time level. "
            "Straight/braking/corner speed deltas and ERS harvest/deploy ratios are not used "
            "as cross-driver race evidence because representative laps occur under different "
            "fuel loads, tyres and track states."
            if session in ("R", "S") else None
        ),
    }


def _stint_snapshot(year: int, race_round: int, session: str) -> dict:
    from data.race_store import load_stint_data

    raw = load_stint_data(year, race_round, session)
    out = {}
    for driver, stints in (raw or {}).items():
        cleaned = []
        for stint in stints or []:
            cleaned.append(
                {
                    "stint": stint.get("stint"),
                    "compound": stint.get("compound"),
                    "avg_pace_s": round(float(stint["avg_pace"]), 3)
                    if _safe_float(stint.get("avg_pace")) is not None
                    else None,
                    "filtered_stint_laps": int(stint.get("stint_length", 0)),
                    "pace_trend_s_per_lap": round(float(stint["degradation_rate"]), 4)
                    if _safe_float(stint.get("degradation_rate")) is not None
                    else None,
                }
            )
        if cleaned:
            out[driver] = cleaned
    return out


def build_performance_snapshot(race_round: int, year: int = 2026) -> dict:
    sessions = {}
    for session in SESSION_ORDER:
        snap = _session_snapshot(year, race_round, session)
        if snap:
            sessions[session] = snap

    stint_context = {}
    for session in ("S", "R"):
        stint = _stint_snapshot(year, race_round, session)
        if stint:
            stint_context[session] = stint

    return {
        "source": "committed_session_store",
        "year": year,
        "round": race_round,
        "sessions": sessions,
        "stint_context": stint_context,
        "stint_interpretation_limit": (
            "pace_trend_s_per_lap is a fitted lap-time slope over filtered green-flag "
            "laps. It is useful stint-pace context, not direct tyre degradation; fuel "
            "burn, traffic, track evolution and driver management can contribute."
        ),
    }


def prediction_snapshot(circuit: str, pred_type: str, year: int = 2026) -> dict | None:
    path = PREDICTION_DIR / f"{year}_{circuit.replace(' ', '_')}_{pred_type}_prediction.json"
    if not path.exists():
        return None
    try:
        pred = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    rows = pred.get("predictions", [])
    return {
        "source_file": path.name,
        "pred_type": pred_type,
        "overall_confidence": pred.get("overall_confidence"),
        "top_8": [
            {
                "position": i,
                "driver": row.get("driver_code"),
                "team": row.get("team"),
                "predicted_delta_s": row.get("predicted_delta_s"),
                "uncertainty_low_s": row.get("delta_range_low"),
                "uncertainty_high_s": row.get("delta_range_high"),
                "confidence": row.get("confidence"),
            }
            for i, row in enumerate(rows[:8], start=1)
        ],
    }


def dossier_sources(dossier: dict) -> list[dict]:
    return list(dossier.get("sources") or [])


def _flatten_items(items):
    for item in items or []:
        if isinstance(item, str):
            yield item
        elif isinstance(item, dict):
            text = item.get("text") or item.get("summary") or item.get("note")
            if text:
                yield text


def dossier_to_text(dossier: dict, question: str = "") -> str:
    """Compact, question-aware dossier text for RAG.

    Narrative/context is deliberately placed before the deterministic snapshot.
    For casual "why" questions this gives the LLM the race story first, while
    Python-computed metrics remain available as supporting evidence.
    """
    if not dossier:
        return ""
    q = question.lower()
    meta = dossier.get("metadata", {})
    out = [
        f"RACE DOSSIER — R{meta.get('round')} {meta.get('circuit')} {meta.get('year')}",
        f"Weekend type: {meta.get('weekend_type', 'unknown')}",
    ]
    if dossier.get("weekend_summary"):
        out.append(f"WEEKEND STORY: {dossier['weekend_summary']}")

    # Race results are a different evidence type from representative pace. For
    # race-result/recap questions, put the deterministic official classification
    # ahead of narrative and pace evidence so the LLM cannot mistake a pace
    # reference driver for the race winner.
    wants_race_results = any(
        phrase in q
        for phrase in (
            "recap", "race summary", "summarize the race", "summarise the race",
            "what happened", "winner", "won", "podium", "finish", "finished",
            "result", "classification", "dnf", "retire", "race",
        )
    )
    if wants_race_results:
        race_snap = ((dossier.get("performance_snapshot") or {}).get("sessions") or {}).get("R")
        result_rows = (race_snap or {}).get("results") or []
        if result_rows:
            out.append(
                "OFFICIAL RACE CLASSIFICATION — AUTHORITATIVE FOR WINNER, PODIUM, "
                "FINISHING ORDER AND DRIVER/TEAM IDENTITY:"
            )
            for row in result_rows:
                code = row.get("driver", "?")
                name = row.get("name") or code
                team = row.get("team") or "Unknown"
                pos = row.get("position")
                status = row.get("status") or ("Finished" if row.get("completed") else "Not classified")
                grid = row.get("grid")
                laps = row.get("laps_completed")
                pos_text = f"P{pos}" if pos is not None else "NC"
                extra = []
                if grid is not None:
                    extra.append(f"grid P{grid}")
                if laps is not None:
                    extra.append(f"{laps} laps")
                suffix = f"; {', '.join(extra)}" if extra else ""
                out.append(f"  {pos_text} {code} — {name} — {team} — {status}{suffix}")
            out.append(
                "RESULT/IDENTITY RULE: use this classification for race outcome and identity. "
                "The deterministic pace snapshot below is pace evidence only and MUST NOT be "
                "used to infer who won, finished on the podium, or which team a driver belongs to."
            )

    # For upgrade questions, put the reviewed weekend inventory near the top so it
    # cannot be overshadowed by season-level PU/update summaries later in the prompt.
    if any(word in q for word in ("upgrade", "development", "floor", "wing", "technical", "aduo")):
        upgrade_items = dossier.get("upgrades_and_technical_context") or []
        out.append(
            f"AUTHORITATIVE WEEKEND UPGRADE INVENTORY: {len(upgrade_items)} reviewed entries. "
            "This list defines what arrived at this event; PU/ADUO and chassis/aero entries "
            "are separate categories."
        )
        for item in upgrade_items:
            if isinstance(item, str):
                out.append(f"  - {item}")
                continue
            team = item.get("team") or "Weekend"
            manufacturer = item.get("manufacturer")
            category = item.get("category", "unspecified")
            owner = f"{manufacturer} PU for {team}" if category == "pu" and manufacturer else team
            text = item.get("text") or item.get("change") or item.get("summary") or ""
            out.append(f"  - {owner} [{category}]: {text}")
            if item.get("reported_effect"):
                out.append(f"      Reported effect/context: {item['reported_effect']}")
            else:
                out.append("      No isolated performance effect is established in the reviewed knowledge.")

    driver_notes = dossier.get("driver_insights") or {}
    team_notes = dossier.get("team_insights") or {}
    named_drivers = []
    named_teams = []
    for code, note in driver_notes.items():
        tokens = [code.lower()] + [
            part.lower() for part in note.get("name", "").split() if len(part) > 3
        ]
        if any(token in q for token in tokens):
            named_drivers.append(code)
    for team in team_notes:
        if team.lower() in q:
            named_teams.append(team)

    # A named driver also implies their team for context filtering when the
    # reviewed dossier supplies it. This prevents a simple driver question from
    # dragging every team's strategy notes into the prompt.
    context_teams = list(named_teams)
    for code in named_drivers:
        team = driver_notes.get(code, {}).get("team")
        if team and team not in context_teams:
            context_teams.append(team)

    # Session progression is useful for a named weekend even when the user did
    # not explicitly say "Sprint"/"Qualifying". Keep it compact but narrative.
    sessions = dossier.get("sessions") or {}
    out.append("SESSION PROGRESSION:")
    for key in SESSION_ORDER:
        section = sessions.get(key)
        if not section:
            continue
        out.append(f"  {key}: {section.get('summary', '')}")
        for text in list(_flatten_items(section.get("key_moments")))[:4]:
            out.append(f"    - {text}")

    for code in named_drivers:
        note = driver_notes[code]
        out.append(f"DRIVER CONTEXT — {code} ({note.get('name', code)}): {note.get('summary', '')}")
        for text in _flatten_items(note.get("details")):
            out.append(f"  - {text}")
        rc = note.get("result_context")
        if rc:
            out.append(
                f"  Result representative of pace: {rc.get('representative_of_pace')} "
                f"— {rc.get('reason', '')}"
            )

    for team in named_teams:
        note = team_notes[team]
        out.append(f"TEAM CONTEXT — {team}: {note.get('summary', '')}")
        for text in _flatten_items(note.get("details")):
            out.append(f"  - {text}")

    # Explicit interpretation items are reviewed narrative, not new LLM
    # inference. Filter them to named entities when possible.
    interpretations = dossier.get("performance_interpretation") or []
    selected_interpretations = []
    for item in interpretations:
        if isinstance(item, str):
            selected_interpretations.append(item)
            continue
        item_teams = {x.lower() for x in item.get("teams", [])}
        item_drivers = {x.lower() for x in item.get("drivers", [])}
        if context_teams or named_drivers:
            if not (
                item_teams & {x.lower() for x in context_teams}
                or item_drivers & {x.lower() for x in named_drivers}
            ):
                continue
        text = item.get("text") or item.get("summary")
        if text:
            selected_interpretations.append(text)
    if selected_interpretations:
        out.append("REVIEWED PERFORMANCE INTERPRETATION:")
        out.extend(f"  - {text}" for text in selected_interpretations[:8])

    if any(word in q for word in ("strategy", "tyre", "tire", "weather", "rain", "stint", "race", "why")):
        strategy_items = []
        for item in dossier.get("strategy_and_conditions") or []:
            if isinstance(item, str):
                strategy_items.append(item)
                continue
            item_teams = {x.lower() for x in item.get("teams", [])}
            if context_teams and item_teams and not (item_teams & {x.lower() for x in context_teams}):
                continue
            text = item.get("text") or item.get("summary")
            if text:
                strategy_items.append(text)
        if strategy_items:
            out.append("STRATEGY / CONDITIONS:")
            out.extend(f"  - {text}" for text in strategy_items[:10])

    if any(word in q for word in ("upgrade", "development", "floor", "wing", "technical", "car", "aduo")):
        technical = []
        for item in dossier.get("upgrades_and_technical_context") or []:
            if not isinstance(item, dict):
                continue
            team = item.get("team")
            if context_teams and team and team not in context_teams:
                continue
            intent = item.get("reported_intent")
            if intent:
                manufacturer = item.get("manufacturer")
                category = item.get("category", "unspecified")
                owner = f"{manufacturer} PU for {team}" if category == "pu" and manufacturer else (team or "weekend")
                technical.append(f"{owner}: reported intent — {intent}")
        if technical:
            out.append("REPORTED UPGRADE INTENT:")
            out.extend(f"  - {line}" for line in technical[:12])

    pred = dossier.get("prediction_review") or {}
    if any(word in q for word in ("predict", "forecast", "model", "expected")) and pred:
        out.append(f"PREDICTION REVIEW: {pred.get('overall_assessment', '')}")
        for text in _flatten_items(pred.get("successes")):
            out.append(f"  success: {text}")
        for text in _flatten_items(pred.get("misses")):
            out.append(f"  miss: {text}")
        for text in _flatten_items(pred.get("known_exceptions")):
            out.append(f"  exception: {text}")

    snap = dossier.get("performance_snapshot") or {}
    if snap and any(
        word in q for word in (
            "pace", "fast", "quick", "quali", "qualifying", "race", "sprint",
            "team", "driver", "stint", "degradation", "tyre", "tire", "why",
        )
    ):
        out.append(
            "DETERMINISTIC PERFORMANCE EVIDENCE — PACE ONLY, NOT CLASSIFICATION OR RESULT:"
        )
        for session, ss in (snap.get("sessions") or {}).items():
            leaders = ", ".join(
                f"{row['driver']} {row['gap_pct']:+.3f}%"
                for row in ss.get("top_pace", [])[:5]
            )
            out.append(f"  {session} top pace: {leaders}")
            if context_teams:
                team_map = {row["team"]: row for row in ss.get("team_pace", [])}
                relevant = [
                    f"{team} median {team_map[team]['median_gap_pct']:+.3f}%"
                    for team in context_teams if team in team_map
                ]
                if relevant:
                    out.append(f"    named-team evidence: {', '.join(relevant)}")
        if snap.get("stint_context") and any(
            word in q for word in ("stint", "degradation", "tyre", "tire", "race pace")
        ):
            out.append(
                "  Stint slopes are contextual pace trends, not measured tyre degradation."
            )

    limits = dossier.get("knowledge_limits") or []
    if limits:
        out.append("KNOWLEDGE LIMITS:")
        out.extend(f"  - {text}" for text in _flatten_items(limits))

    return "\n".join(out)



def season_dossiers_to_text(
    question: str = "",
    year: int = 2026,
    *,
    approved_only: bool = True,
) -> str:
    """Compact chronological context across all reviewed race dossiers.

    This exists for season-wide queries such as "race by race" where entity
    matching cannot name twelve circuits individually. It deliberately keeps
    each round small so query-time context stays inside the Groq free tier.
    """
    q = question.lower()
    rows = list_dossiers(year=year, approved_only=approved_only)
    if not rows:
        return ""

    out = [
        "APPROVED SEASON DOSSIER CHRONOLOGY:",
        "  These are reviewed weekend narratives. Preserve round order and do not fill missing rounds from memory.",
    ]
    for row in sorted(rows, key=lambda item: item.get("round") or 999):
        race_round = row.get("round")
        dossier = load_dossier(
            race_round,
            year=year,
            approved_only=approved_only,
            hydrate_snapshot=False,
        )
        if not dossier:
            continue
        meta = dossier.get("metadata", {})
        circuit = meta.get("circuit") or row.get("circuit") or f"R{race_round}"
        out.append(f"R{race_round} {circuit}:")
        story = dossier.get("weekend_summary")
        if story:
            out.append(f"  Weekend story: {story}")

        sessions = dossier.get("sessions") or {}
        # Q/R summaries give enough sporting structure for a season chronology;
        # include SQ/S too only when the weekend has them.
        for key in SESSION_ORDER:
            section = sessions.get(key)
            if not section:
                continue
            summary = section.get("summary")
            if summary:
                out.append(f"  {key}: {summary}")

        # Add at most two reviewed key moments if the dossier stores a top-level list.
        moments = _flatten_items(dossier.get("key_moments"))
        for moment in moments[:2]:
            out.append(f"  Key moment: {moment}")

        # For generic season stories, avoid dumping team/driver notes. If the user
        # explicitly asks about one team, include that reviewed team's summary.
        team_notes = dossier.get("team_insights") or {}
        for team, note in team_notes.items():
            if team.lower() in q:
                summary = note.get("summary") if isinstance(note, dict) else str(note)
                if summary:
                    out.append(f"  {team}: {summary}")

    return "\n".join(out)

def save_hydrated_snapshot(race_round: int, year: int = 2026) -> Path:
    """Write the deterministic performance_snapshot into the dossier JSON."""
    path = _dossier_path(year, race_round)
    if path is None:
        raise FileNotFoundError(f"No dossier file for {year} R{race_round:02d}.")
    data = json.loads(path.read_text(encoding="utf-8"))
    data["performance_snapshot"] = build_performance_snapshot(race_round, year)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return path
