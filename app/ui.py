"""Shared presentation helpers for the LatentLap Streamlit UI.

Wave 3 introduces one visual system that pages can opt into incrementally.
Keep analytical logic out of this module: it should only contain rendering,
copy helpers, and styling primitives.
"""

from __future__ import annotations

import html
from typing import Iterable, Sequence

import streamlit as st


ACCENT = "#e10600"
ACCENT_SOFT = "#ff6b61"
BLUE = "#65baff"
GREEN = "#74d6a4"
TEXT = "#f4f7fb"
MUTED = "#c88f94"
PANEL = "#0f151d"
PANEL_ALT = "#121a24"
BORDER = "#273140"


def inject_global_css() -> None:
    """Apply the shared LatentLap visual language to the current page."""
    st.markdown(
        """
<style>
:root {
    --ll-bg: #080b10;
    --ll-panel: #0f151d;
    --ll-panel-2: #121a24;
    --ll-border: #273140;
    --ll-border-soft: #1b2430;
    --ll-text: #f4f7fb;
    --ll-muted: #c88f94;
    --ll-accent: #e10600;
    --ll-accent-hover: #ff1a12;
    --ll-accent-soft: #ff6b61;
    --ll-blue: #65baff;
    --ll-green: #74d6a4;
}

html, body, [class*="css"] {
    font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.stApp {
    background:
        radial-gradient(circle at 88% 2%, rgba(101, 186, 255, 0.07), transparent 28rem),
        radial-gradient(circle at 7% 12%, rgba(225, 6, 0, 0.08), transparent 24rem),
        var(--ll-bg);
    color: var(--ll-text);
}

.block-container {
    max-width: 1420px;
    padding-top: 2.15rem;
    padding-bottom: 4rem;
}

[data-testid="stSidebar"] {
    background: #090d12;
    border-right: 1px solid var(--ll-border-soft);
}

[data-testid="stSidebarNav"] a {
    border-radius: 9px;
}

[data-testid="stSidebarNav"] a:hover {
    background: rgba(255, 255, 255, 0.045);
}

h1, h2, h3, h4 {
    letter-spacing: -0.025em;
}

p, li {
    line-height: 1.6;
}

hr {
    border-color: var(--ll-border-soft) !important;
}

.ll-kicker {
    display: inline-flex;
    align-items: center;
    gap: 0.55rem;
    color: var(--ll-accent-soft);
    font-size: 0.76rem;
    font-weight: 750;
    letter-spacing: 0.16em;
    text-transform: uppercase;
    margin-bottom: 1rem;
}

.ll-kicker::before {
    content: "";
    width: 1.65rem;
    height: 2px;
    background: var(--ll-accent);
    border-radius: 999px;
}

/* ── CTA system ─────────────────────────────────────────────── */
.ll-cta {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-height: 2.7rem;
    padding: 0.68rem 1.05rem;
    border-radius: 9px;
    text-decoration: none !important;
    font-size: 0.82rem;
    font-weight: 800;
    letter-spacing: 0.01em;
    line-height: 1;
    white-space: nowrap;
    transition: transform 130ms ease, background 130ms ease, border-color 130ms ease, box-shadow 130ms ease;
    cursor: pointer;
}

.ll-cta-primary {
    color: #fff !important;
    background: var(--ll-accent);
    border: 1px solid var(--ll-accent);
    box-shadow: 0 7px 22px rgba(225, 6, 0, 0.18);
}

.ll-cta-primary:hover {
    color: #fff !important;
    background: var(--ll-accent-hover);
    border-color: var(--ll-accent-hover);
    transform: translateY(-1px);
    box-shadow: 0 10px 26px rgba(225, 6, 0, 0.28);
}

.ll-cta-secondary {
    color: #fff !important;
    background: rgba(225, 6, 0, 0.055);
    border: 1px solid rgba(255, 74, 69, 0.6);
}

.ll-cta-secondary:hover {
    color: #fff !important;
    background: rgba(225, 6, 0, 0.14);
    border-color: var(--ll-accent-soft);
    transform: translateY(-1px);
}

.ll-hero {
    border: 1px solid var(--ll-border);
    border-radius: 18px;
    padding: 2.8rem 3rem 2.65rem 3rem;
    background:
        linear-gradient(120deg, rgba(225, 6, 0, 0.07), transparent 43%),
        linear-gradient(160deg, rgba(101, 186, 255, 0.045), transparent 55%),
        rgba(15, 21, 29, 0.86);
    box-shadow: 0 26px 80px rgba(0, 0, 0, 0.23);
    position: relative;
    overflow: hidden;
}

.ll-hero::after {
    content: "";
    position: absolute;
    inset: auto -7rem -9rem auto;
    width: 20rem;
    height: 20rem;
    border: 1px solid rgba(101, 186, 255, 0.12);
    border-radius: 50%;
    box-shadow: 0 0 0 3rem rgba(101, 186, 255, 0.025), 0 0 0 6rem rgba(225, 6, 0, 0.018);
    pointer-events: none;
}

.ll-wordmark {
    color: var(--ll-text);
    font-size: clamp(1rem, 1.4vw, 1.22rem);
    font-weight: 850;
    letter-spacing: 0.23em;
    text-transform: uppercase;
    margin-bottom: 1.25rem;
}

.ll-wordmark span {
    color: var(--ll-accent);
}

.ll-hero h1 {
    font-size: clamp(2.55rem, 5.6vw, 5.35rem);
    max-width: 980px;
    line-height: 0.98;
    margin: 0 0 1.35rem 0;
    color: var(--ll-text);
    font-weight: 800;
}

.ll-hero-copy {
    max-width: 880px;
    color: #d8b0b3;
    font-size: clamp(1rem, 1.4vw, 1.16rem);
    margin-bottom: 0.9rem;
}

.ll-hero-note {
    max-width: 860px;
    color: var(--ll-muted);
    font-size: 0.92rem;
}

.ll-pill-row {
    display: flex;
    gap: 0.55rem;
    flex-wrap: wrap;
    margin-top: 1.55rem;
}

.ll-pill {
    border: 1px solid var(--ll-border);
    background: rgba(8, 11, 16, 0.52);
    border-radius: 999px;
    padding: 0.37rem 0.7rem;
    color: #d0a0a4;
    font-size: 0.74rem;
    font-weight: 650;
    letter-spacing: 0.035em;
}

.ll-hero-actions {
    position: relative;
    z-index: 2;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 0.8rem;
    flex-wrap: wrap;
    margin-top: 1.8rem;
}

.ll-section-head {
    margin-top: 3.3rem;
    margin-bottom: 1.25rem;
}

.ll-section-head .eyebrow {
    color: var(--ll-accent-soft);
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 750;
    margin-bottom: 0.45rem;
}

.ll-section-head h2 {
    margin: 0;
    font-size: clamp(1.65rem, 2.2vw, 2.25rem);
    color: var(--ll-text);
}

.ll-section-head p {
    color: var(--ll-muted);
    max-width: 840px;
    margin: 0.55rem 0 0 0;
}

/* ── Intent cards: one grid, equal height, integrated CTA shelf ── */
.ll-intent-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 1rem;
    align-items: stretch;
}

.ll-intent-card {
    min-height: 318px;
    border: 1px solid var(--ll-border);
    background: linear-gradient(180deg, rgba(18, 26, 36, 0.97), rgba(13, 19, 27, 0.97));
    border-radius: 14px;
    padding: 1.4rem 1.35rem 1.25rem;
    transition: transform 140ms ease, border-color 140ms ease, box-shadow 140ms ease;
    display: flex;
    flex-direction: column;
}

.ll-intent-card:hover {
    transform: translateY(-2px);
    border-color: #3a4658;
    box-shadow: 0 16px 34px rgba(0, 0, 0, 0.16);
}

.ll-intent-no {
    color: var(--ll-accent);
    font-size: 0.72rem;
    font-weight: 850;
    letter-spacing: 0.12em;
    margin-bottom: 1rem;
}

.ll-intent-card h3 {
    color: var(--ll-text);
    font-size: 1.08rem;
    line-height: 1.2;
    margin: 0 0 0.7rem 0;
}

.ll-intent-card p {
    color: var(--ll-muted);
    font-size: 0.88rem;
    margin: 0;
}

.ll-intent-copy {
    flex: 1 1 auto;
}

.ll-intent-actions {
    min-height: 82px;
    margin-top: 1.2rem;
    padding-top: 1rem;
    border-top: 1px solid var(--ll-border-soft);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.55rem;
}

.ll-intent-actions .ll-cta {
    width: min(100%, 13rem);
}

.ll-spotlight {
    border: 1px solid var(--ll-border);
    border-radius: 16px;
    background: linear-gradient(145deg, rgba(101, 186, 255, 0.045), rgba(225, 6, 0, 0.035));
    padding: 1.7rem 1.75rem;
    min-height: 310px;
}

.ll-spotlight-flex {
    display: flex;
    flex-direction: column;
}

.ll-spotlight h3 {
    font-size: 1.55rem;
    margin: 0 0 0.75rem 0;
}

.ll-spotlight p {
    color: #d0a0a4;
    margin-bottom: 0.9rem;
}

.ll-signal-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.75rem;
}

.ll-signal {
    border: 1px solid var(--ll-border-soft);
    border-radius: 12px;
    padding: 1rem;
    background: rgba(8, 11, 16, 0.42);
}

.ll-signal strong {
    display: block;
    color: var(--ll-text);
    font-size: 0.9rem;
    margin-bottom: 0.25rem;
}

.ll-signal span {
    color: var(--ll-muted);
    font-size: 0.78rem;
    line-height: 1.45;
}

.ll-card-footer {
    margin-top: auto;
    padding-top: 1.25rem;
    display: flex;
    justify-content: center;
    align-items: center;
}

.ll-method-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.75rem;
}

.ll-method-step {
    border-top: 2px solid var(--ll-border);
    padding: 1rem 0.9rem 0.45rem 0;
}

.ll-method-step.active {
    border-top-color: var(--ll-accent);
}

.ll-method-step .num {
    color: var(--ll-muted);
    font-size: 0.68rem;
    letter-spacing: 0.12em;
    margin-bottom: 0.45rem;
}

.ll-method-step strong {
    display: block;
    color: var(--ll-text);
    font-size: 0.95rem;
    margin-bottom: 0.3rem;
}

.ll-method-step span {
    color: var(--ll-muted);
    font-size: 0.8rem;
    line-height: 1.45;
}

.ll-state-card, .ll-pred-card {
    border: 1px solid var(--ll-border);
    border-radius: 14px;
    background: rgba(15, 21, 29, 0.82);
    padding: 1.4rem 1.45rem;
    min-height: 330px;
    display: flex;
    flex-direction: column;
}

.ll-card-copy {
    color: var(--ll-muted);
    margin-top: 0.45rem;
}

.ll-state-grid {
    display: grid;
    grid-template-columns: 0.72fr 1.12fr 1.16fr;
    gap: 0.85rem;
    margin-top: 1rem;
}

.ll-stat {
    border-left: 2px solid var(--ll-border);
    padding-left: 0.8rem;
}

.ll-stat .label {
    color: var(--ll-muted);
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

.ll-stat .value {
    color: var(--ll-text);
    font-weight: 760;
    font-size: 0.98rem;
    line-height: 1.35;
    margin-top: 0.25rem;
}

.ll-pred-row {
    display: grid;
    grid-template-columns: 2.3rem 3.2rem minmax(0, 1fr) auto;
    align-items: center;
    gap: 0.55rem;
    padding: 0.55rem 0;
    border-bottom: 1px solid var(--ll-border-soft);
    font-size: 0.84rem;
}

.ll-pred-row:last-child {
    border-bottom: 0;
}

.ll-pred-pos {
    color: var(--ll-muted);
}

.ll-pred-code {
    font-weight: 800;
    letter-spacing: 0.04em;
}

.ll-pred-gap {
    color: #c7ced8;
    font-variant-numeric: tabular-nums;
}

.ll-disclaimer {
    color: var(--ll-muted);
    font-size: 0.77rem;
    margin-top: 0.8rem;
}

.ll-footer {
    border-top: 1px solid var(--ll-border-soft);
    margin-top: 3.4rem;
    padding-top: 1.15rem;
    color: #687484;
    font-size: 0.75rem;
}

/* ── Equal-height two-card rows ─────────────────────────────── */
.ll-two-card-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 1.4rem;
    align-items: stretch;
}

.ll-two-card-grid > .ll-spotlight,
.ll-two-card-grid > .ll-state-card,
.ll-two-card-grid > .ll-pred-card {
    height: 100%;
    min-height: 100%;
}

/* ── Page-level shells used by migrated analytical pages ───── */
.ll-page-head {
    border-bottom: 1px solid var(--ll-border-soft);
    padding: 0.3rem 0 1.35rem 0;
    margin-bottom: 1.35rem;
}

.ll-page-head .eyebrow {
    color: var(--ll-accent-soft);
    font-size: 0.72rem;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    font-weight: 800;
    margin-bottom: 0.45rem;
}

.ll-page-head h1 {
    margin: 0;
    color: var(--ll-text);
    font-size: clamp(2.15rem, 3.4vw, 3.45rem);
    line-height: 1.03;
}

.ll-page-head p {
    color: var(--ll-muted);
    max-width: 900px;
    margin: 0.65rem 0 0 0;
}

.ll-meta-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.8rem;
    margin: 1rem 0 1.2rem 0;
}

.ll-meta-card {
    border: 1px solid var(--ll-border);
    background: rgba(15, 21, 29, 0.78);
    border-radius: 12px;
    padding: 0.95rem 1rem;
    min-height: 96px;
}

.ll-meta-card .label {
    color: var(--ll-muted);
    font-size: 0.69rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.35rem;
}

.ll-meta-card .value {
    color: var(--ll-text);
    font-weight: 800;
    font-size: 1rem;
    line-height: 1.35;
}

.ll-takeaway {
    border: 1px solid rgba(225, 6, 0, 0.38);
    border-left: 3px solid var(--ll-accent);
    background: linear-gradient(90deg, rgba(225, 6, 0, 0.08), rgba(15, 21, 29, 0.64));
    border-radius: 12px;
    padding: 1rem 1.15rem;
    margin: 0.8rem 0 1.25rem 0;
}

.ll-takeaway .label {
    color: var(--ll-accent-soft);
    font-size: 0.69rem;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-weight: 800;
    margin-bottom: 0.35rem;
}

.ll-takeaway .text {
    color: #d8dee7;
    font-size: 0.96rem;
    line-height: 1.55;
}

.ll-panel {
    border: 1px solid var(--ll-border);
    border-radius: 14px;
    background: rgba(15, 21, 29, 0.68);
    padding: 1.15rem 1.25rem;
    margin-bottom: 1rem;
}

.ll-panel h3 {
    margin-top: 0;
}

.ll-inline-note {
    color: var(--ll-muted);
    font-size: 0.8rem;
    line-height: 1.5;
    margin: 0.35rem 0 0.9rem 0;
}

.ll-ai-hook {
    border: 1px solid var(--ll-border);
    border-radius: 14px;
    background: linear-gradient(135deg, rgba(225, 6, 0, 0.07), rgba(101, 186, 255, 0.035));
    padding: 1.1rem 1.2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 1rem;
    margin: 1.4rem 0 0.5rem 0;
}

.ll-ai-hook strong {
    display: block;
    color: var(--ll-text);
    margin-bottom: 0.25rem;
}

.ll-ai-hook span {
    color: var(--ll-muted);
    font-size: 0.82rem;
}




/* ── Wave 3.4 readability pass ─────────────────────────────── */
.ll-hero-copy {
    font-size: 1.08rem !important;
    line-height: 1.62 !important;
}

.ll-hero-note,
.ll-section-head p,
.ll-card-copy,
.ll-spotlight p {
    font-size: 0.98rem !important;
    line-height: 1.62 !important;
}

.ll-intent-card p {
    font-size: 0.94rem !important;
    line-height: 1.58 !important;
}

.ll-signal strong {
    font-size: 0.98rem !important;
}

.ll-signal span,
.ll-method-step p {
    font-size: 0.88rem !important;
    line-height: 1.55 !important;
}

.ll-method-step strong {
    font-size: 1rem !important;
}

.ll-stat .label,
.ll-pred-pos {
    font-size: 0.76rem !important;
}

.ll-stat .value,
.ll-pred-code {
    font-size: 0.98rem !important;
}

.ll-disclaimer {
    font-size: 0.84rem !important;
    line-height: 1.5 !important;
}

[data-testid="stWidgetLabel"] p {
    font-size: 0.98rem !important;
    font-weight: 750 !important;
}

[data-testid="stCaptionContainer"] p {
    font-size: 0.88rem !important;
    line-height: 1.5 !important;
}

[data-testid="stMetricLabel"] p {
    font-size: 0.9rem !important;
}

[data-testid="stMetricValue"] {
    font-size: 1.55rem !important;
}

/* ── Driver-first analytical view ─────────────────────────── */
.ll-driver-hero {
    --driver-colour: var(--ll-accent);
    border: 1px solid var(--ll-border);
    border-left: 4px solid var(--driver-colour);
    border-radius: 15px;
    background:
        linear-gradient(110deg, rgba(225, 6, 0, 0.055), transparent 46%),
        rgba(15, 21, 29, 0.88);
    padding: 1.35rem 1.45rem;
    margin: 0.8rem 0 1rem 0;
}

.ll-driver-hero .code {
    color: var(--driver-colour);
    font-size: 0.82rem;
    font-weight: 850;
    letter-spacing: 0.14em;
    text-transform: uppercase;
    margin-bottom: 0.35rem;
}

.ll-driver-hero h2 {
    margin: 0;
    font-size: clamp(1.9rem, 3vw, 2.7rem);
    color: var(--ll-text);
    line-height: 1.08;
}

.ll-driver-hero .team {
    color: #d2a4a7;
    font-size: 1.02rem;
    margin-top: 0.32rem;
}

.ll-driver-hero .story {
    color: #d9b2b5;
    font-size: 1rem;
    line-height: 1.62;
    margin-top: 0.9rem;
    max-width: 980px;
}

.ll-driver-metrics,
.ll-highlight-grid {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: 0.85rem;
    margin: 0.9rem 0 1.35rem 0;
}

.ll-driver-metric,
.ll-highlight-card {
    border: 1px solid var(--ll-border);
    background: rgba(15, 21, 29, 0.78);
    border-radius: 12px;
    padding: 1rem 1.05rem;
    min-height: 112px;
}

.ll-driver-metric .label,
.ll-highlight-card .label {
    color: var(--ll-muted);
    font-size: 0.76rem;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    margin-bottom: 0.42rem;
}

.ll-driver-metric .value,
.ll-highlight-card .value {
    color: var(--ll-text);
    font-size: 1.24rem;
    font-weight: 820;
    line-height: 1.28;
}

.ll-driver-metric .note,
.ll-highlight-card .note {
    color: var(--ll-muted);
    font-size: 0.84rem;
    line-height: 1.42;
    margin-top: 0.34rem;
}

.ll-sector-lines {
    display: grid;
    gap: 0.26rem;
}

.ll-sector-line {
    display: grid;
    grid-template-columns: 28px 1fr auto;
    gap: 0.35rem;
    align-items: baseline;
    font-size: 0.92rem;
}

.ll-sector-line .sector {
    color: var(--ll-muted);
}

.ll-sector-line .driver {
    color: var(--ll-text);
    font-weight: 800;
}

.ll-sector-line .time {
    color: #8be6a9;
    font-variant-numeric: tabular-nums;
}

.ll-team-context {
    border: 1px solid var(--ll-border);
    border-radius: 14px;
    background: rgba(15, 21, 29, 0.72);
    padding: 1.2rem 1.25rem;
    margin: 0.8rem 0 1rem 0;
}

.ll-team-context h3 {
    margin: 0 0 0.35rem 0;
    font-size: 1.35rem;
}

.ll-team-context p {
    color: var(--ll-muted);
    font-size: 0.98rem;
    line-height: 1.55;
    margin: 0;
}

/* Existing Streamlit page links, used on pages not yet migrated, also read as actions. */
div[data-testid="stPageLink"] a {
    border: 1px solid rgba(255, 74, 69, 0.58) !important;
    border-radius: 9px !important;
    background: rgba(225, 6, 0, 0.07) !important;
    color: var(--ll-text) !important;
    font-weight: 760 !important;
    min-height: 2.6rem;
    transition: border-color 120ms ease, background 120ms ease, transform 120ms ease;
}

div[data-testid="stPageLink"] a:hover {
    border-color: var(--ll-accent) !important;
    background: rgba(225, 6, 0, 0.14) !important;
    transform: translateY(-1px);
}

@media (max-width: 1100px) {
    .ll-intent-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
}

@media (max-width: 900px) {
    .ll-driver-metrics, .ll-highlight-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .ll-two-card-grid {
        grid-template-columns: 1fr;
    }
    .ll-meta-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .ll-ai-hook {
        align-items: flex-start;
        flex-direction: column;
    }
    .ll-hero {
        padding: 2rem 1.45rem;
    }
    .ll-method-grid {
        grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .ll-state-grid {
        grid-template-columns: 1fr;
    }
    .ll-state-card, .ll-pred-card {
        min-height: 0;
    }
}

@media (max-width: 640px) {
    .ll-driver-metrics, .ll-highlight-grid {
        grid-template-columns: 1fr;
    }
    .ll-meta-grid {
        grid-template-columns: 1fr;
    }
    .block-container {
        padding-top: 1.2rem;
    }
    .ll-method-grid,
    .ll-signal-grid,
    .ll-intent-grid {
        grid-template-columns: 1fr;
    }
    .ll-intent-card {
        min-height: 0;
    }
    .ll-hero-actions {
        flex-direction: column;
        align-items: stretch;
    }
    .ll-hero-actions .ll-cta {
        width: 100%;
    }
}
</style>
        """,
        unsafe_allow_html=True,
    )



def page_header(eyebrow: str, title: str, body: str = "") -> None:
    body_html = f"<p>{html.escape(body)}</p>" if body else ""
    st.markdown(
        f"""
<div class="ll-page-head">
    <div class="eyebrow">{html.escape(eyebrow)}</div>
    <h1>{html.escape(title)}</h1>
    {body_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def section_header(eyebrow: str, title: str, body: str = "") -> None:
    body_html = f"<p>{html.escape(body)}</p>" if body else ""
    st.markdown(
        f"""
<div class="ll-section-head">
    <div class="eyebrow">{html.escape(eyebrow)}</div>
    <h2>{html.escape(title)}</h2>
    {body_html}
</div>
        """,
        unsafe_allow_html=True,
    )


def _cta_html(label: str, href: str, style: str = "primary") -> str:
    css_class = "ll-cta-primary" if style == "primary" else "ll-cta-secondary"
    return (
        f'<a class="ll-cta {css_class}" href="{html.escape(href, quote=True)}" '
        f'target="_self">{html.escape(label)}</a>'
    )


def intent_grid(
    cards: Sequence[
        tuple[str, str, str, Sequence[tuple[str, str, str]]]
    ]
) -> None:
    """Render equal-height intent cards with their actions inside each card."""
    rendered = []
    for number, title, body, actions in cards:
        action_html = "".join(_cta_html(label, href, style) for label, href, style in actions)
        rendered.append(
            f"""
<div class="ll-intent-card">
    <div class="ll-intent-copy">
        <div class="ll-intent-no">{html.escape(number)}</div>
        <h3>{html.escape(title)}</h3>
        <p>{html.escape(body)}</p>
    </div>
    <div class="ll-intent-actions">{action_html}</div>
</div>
            """
        )

    st.markdown(
        '<div class="ll-intent-grid">' + "".join(rendered) + "</div>",
        unsafe_allow_html=True,
    )


def methodology_strip(steps: Iterable[tuple[str, str]]) -> None:
    blocks = []
    for idx, (title, body) in enumerate(steps, start=1):
        cls = "ll-method-step active" if idx == 1 else "ll-method-step"
        blocks.append(
            f"""
<div class="{cls}">
    <div class="num">0{idx}</div>
    <strong>{html.escape(title)}</strong>
    <span>{html.escape(body)}</span>
</div>
            """
        )
    st.markdown(
        '<div class="ll-method-grid">' + "".join(blocks) + "</div>",
        unsafe_allow_html=True,
    )
