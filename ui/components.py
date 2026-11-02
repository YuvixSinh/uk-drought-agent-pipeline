"""
Reusable UI Components (Section 3, 4, 5, 6) — Orbital Agronomist (v2)
Includes Global Header with 3-step stepper, Provenance Badges, Risk Chips,
Inline SVG UK Locator, Inline SVG Crop Icons, KPI Tiles, and Diagnostics Drawer.
"""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

import streamlit as st

from events import get_outbound_calls, now_london_str
from ui.state import SCREEN2_PREVIEW_STATES, SCREEN3_PREVIEW_STATES

THEME_CSS_PATH = Path(__file__).parent / "theme.css"


def clean_html(raw: str) -> str:
    """Strip per-line leading spaces and blank lines so CommonMark never treats HTML as a code block."""
    return "\n".join(line.strip() for line in raw.splitlines() if line.strip())


def inject_theme_css() -> None:
    """Load and inject ui/theme.css into the Streamlit page."""
    if THEME_CSS_PATH.exists():
        css_text = THEME_CSS_PATH.read_text(encoding="utf-8")
        st.markdown(f"<style>{css_text}</style>", unsafe_allow_html=True)


def render_global_header() -> None:
    """
    Render the 64px global header across all screens (Section 3):
    - Left: mark · “Orbital Agronomist” · “UK drought & crop outlook · model data”
    - Centre: 3-step stepper (1 Choose location, 2 Live analysis, 3 Outlook)
      with number + check icon for completed steps, cyan glow on current step, dim on future steps.
    - Right: [ONLINE | OFFLINE-CACHE] badge, London time (Europe/London), and
      Model IDs on Screens 2 and 3 only.
    """
    phase = st.session_state.get("phase", "pick")
    data_mode = st.session_state.get("data_mode", "ONLINE")
    # Override data_mode badge in preview states if offline preview is active
    if phase == "analyse" and st.session_state.get("dev_screen2_state") == "offline cached replay":
        data_mode = "OFFLINE-CACHE"
    elif phase == "outlook" and st.session_state.get("dev_screen3_state") == "offline":
        data_mode = "OFFLINE-CACHE"

    london_time = now_london_str()
    primary_model = st.session_state.get("primary_model_id", "gemini-3-flash-preview")
    fallback_model = st.session_state.get("fallback_model_id", "gemini-3.1-flash-lite-preview")

    # Determine step states: ("done" | "active" | "future")
    if phase == "pick":
        s1, s2, s3 = "active", "future", "future"
    elif phase == "analyse":
        s1, s2, s3 = "done", "active", "future"
    else:
        s1, s2, s3 = "done", "done", "active"

    def _step_html(num: int, label: str, state: str) -> str:
        check_svg = (
            '<svg width="11" height="11" viewBox="0 0 16 16" fill="none" '
            'style="margin-right:2px;vertical-align:middle;">'
            '<path d="M13.5 4.5L6.5 11.5L2.5 7.5" stroke="#10B981" stroke-width="2.2" '
            'stroke-linecap="round" stroke-linejoin="round"/></svg>'
            if state == "done"
            else ""
        )
        num_content = f"{check_svg}{num}"
        return (
            f'<div class="oa-step {state}" aria-current="{"step" if state == "active" else "false"}">'
            f'<span class="oa-step-num">{num_content}</span>'
            f'<span>{html.escape(label)}</span>'
            f"</div>"
        )

    mode_cls = "online" if data_mode == "ONLINE" else "offline"
    mode_dot = "●" if data_mode == "ONLINE" else "◆"

    model_pill_html = ""
    if phase in ("analyse", "outlook"):
        model_pill_html = (
            f'<div class="oa-model-pill" title="Primary & Fallback Gemini Model IDs">'
            f"<span>A1–A3: <b>{html.escape(primary_model)}</b></span>"
            f'<span style="color:#5B6B82;">|</span>'
            f'<span>FB: <b style="color:#9AA8BC;">{html.escape(fallback_model)}</b></span>'
            f"</div>"
        )

    header_html = f"""
    <header class="oa-global-header" role="banner">
      <div class="oa-brand-group">
        <div class="oa-brand-mark" aria-hidden="true">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="9" stroke="#22D3EE" stroke-width="1.8"/>
            <ellipse cx="12" cy="12" rx="9" ry="3.8" stroke="#38BDF8" stroke-width="1.3" stroke-dasharray="2 2"/>
            <path d="M12 3V21" stroke="#10B981" stroke-width="1.4"/>
            <circle cx="14.5" cy="8.5" r="2.2" fill="#22D3EE"/>
          </svg>
        </div>
        <div>
          <span class="oa-brand-title">Orbital Agronomist</span>
          <span class="oa-brand-sub">· UK drought &amp; crop outlook · model data</span>
        </div>
      </div>

      <nav class="oa-stepper" aria-label="Analysis workflow steps">
        {_step_html(1, "Choose location", s1)}
        <div class="oa-step-connector {'done' if s1 == 'done' else ''}"></div>
        {_step_html(2, "Live analysis", s2)}
        <div class="oa-step-connector {'done' if s2 == 'done' else ''}"></div>
        {_step_html(3, "Outlook", s3)}
      </nav>

      <div class="oa-header-right">
        {model_pill_html}
        <span class="oa-mode-badge {mode_cls}">{mode_dot} {html.escape(data_mode)}</span>
        <span class="oa-time-pill" title="Europe/London timezone">🇬🇧 {html.escape(london_time)}</span>
      </div>
    </header>
    """
    st.markdown(clean_html(header_html), unsafe_allow_html=True)


def provenance_badge_html(
    source_state: str = "LIVE",
    product_kind: str = "MODELLED",
    tooltip: str = "Open-Meteo weather & soil-water model output (not satellite or field sensor measurement)",
) -> str:
    """
    Render the dual-tag provenance badge (Section 4 & 6):
    [source_state] · [product_kind]
    Allowed source_state: LIVE | CACHED | FALLBACK | DEMO FIXTURE | UNAVAILABLE
    Allowed product_kind: MODELLED | SEASONAL ENSEMBLE | DERIVED | SIMULATED | AI-GENERATED | HEURISTIC | USER-ENTERED
    """
    s_clean = source_state.strip().upper()
    p_clean = product_kind.strip().upper()
    s_cls = "live"
    if "CACHE" in s_clean or "FIXTURE" in s_clean:
        s_cls = "cached"
    elif "FALLBACK" in s_clean:
        s_cls = "fallback"
    elif "UNAVAILABLE" in s_clean:
        s_cls = "unavailable"

    p_cls = "simulated" if "SIMULATED" in p_clean else ""
    safe_tip = html.escape(tooltip)
    return (
        f'<span class="oa-prov-badge" title="{safe_tip}">'
        f'<span class="oa-prov-source {s_cls}">{html.escape(s_clean)}</span>'
        f'<span class="oa-prov-kind {p_cls}">{html.escape(p_clean)}</span>'
        f"</span>"
    )


def risk_chip_html(label: str, prefix: str = "") -> str:
    """
    Render a risk chip with colour, distinct SVG icon shape, and text (never colour alone):
    - LOW: emerald circle check
    - WATCH: amber diamond
    - ELEVATED: coral triangle warning
    - INCONCLUSIVE: violet square-dot
    - UNAVAILABLE: slate slash-circle
    """
    u = label.strip().upper()
    if u == "LOW":
        cls = "low"
        icon = (
            '<svg width="12" height="12" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="6.5" stroke="#10B981" stroke-width="1.8"/>'
            '<path d="M5.2 8.2L7.1 10.1L11.0 6.2" stroke="#10B981" stroke-width="1.8" stroke-linecap="round"/>'
            "</svg>"
        )
    elif u == "WATCH":
        cls = "watch"
        icon = (
            '<svg width="12" height="12" viewBox="0 0 16 16" fill="none">'
            '<path d="M8 1.5L14.5 8L8 14.5L1.5 8L8 1.5Z" stroke="#F59E0B" stroke-width="1.8"/>'
            '<circle cx="8" cy="8" r="1.6" fill="#F59E0B"/>'
            "</svg>"
        )
    elif u == "ELEVATED":
        cls = "elevated"
        icon = (
            '<svg width="12" height="12" viewBox="0 0 16 16" fill="none">'
            '<path d="M8 2L14.8 13.8H1.2L8 2Z" stroke="#F43F5E" stroke-width="1.7" stroke-linejoin="round"/>'
            '<path d="M8 6.5V9.8" stroke="#F43F5E" stroke-width="1.8" stroke-linecap="round"/>'
            '<circle cx="8" cy="11.8" r="0.9" fill="#F43F5E"/>'
            "</svg>"
        )
    elif u == "INCONCLUSIVE":
        cls = "inconclusive"
        icon = (
            '<svg width="12" height="12" viewBox="0 0 16 16" fill="none">'
            '<rect x="2.2" y="2.2" width="11.6" height="11.6" rx="2.5" stroke="#A78BFA" stroke-width="1.7"/>'
            '<path d="M5 8H11" stroke="#A78BFA" stroke-width="1.8" stroke-linecap="round"/>'
            "</svg>"
        )
    else:
        cls = "unavailable"
        u = "UNAVAILABLE"
        icon = (
            '<svg width="12" height="12" viewBox="0 0 16 16" fill="none">'
            '<circle cx="8" cy="8" r="6.2" stroke="#9AA8BC" stroke-width="1.6" stroke-dasharray="2 2"/>'
            '<path d="M4.2 11.8L11.8 4.2" stroke="#9AA8BC" stroke-width="1.6"/>'
            "</svg>"
        )

    prefix_html = f'<span style="opacity:0.8;font-weight:500;">{html.escape(prefix)} ·</span>' if prefix else ""
    return f'<span class="oa-risk-chip {cls}">{icon}{prefix_html}<span>{html.escape(u)}</span></span>'


def kpi_tile_html(
    label: str,
    value_str: str,
    unit: str = "",
    delta_str: str = "",
    source_state: str = "LIVE",
    product_kind: str = "MODELLED",
    tooltip: str = "",
) -> str:
    """Render a compact KPI card with provenance badge, mono value, and delta line."""
    badge = provenance_badge_html(source_state, product_kind, tooltip or f"{label} ({source_state} · {product_kind})")
    unit_html = f'<span class="oa-kpi-unit">{html.escape(unit)}</span>' if unit else ""
    delta_html = f'<div class="oa-kpi-delta">{html.escape(delta_str)}</div>' if delta_str else ""
    return clean_html(f"""
    <div class="oa-kpi-tile">
      <div class="oa-kpi-top">
        <span class="oa-kpi-label">{html.escape(label)}</span>
        {badge}
      </div>
      <div>
        <span class="oa-kpi-val">{html.escape(value_str)}</span>
        {unit_html}
      </div>
      {delta_html}
    </div>
    """)


def uk_locator_svg_html(lat: float, lon: float) -> str:
    """
    Render a compact 38x46 inline SVG UK silhouette with a glowing cyan dot
    at the selected (lat, lon) coordinate (used on Screen 2 context bar).
    UK bounds approx: lat 49.8..60.9, lon -8.6..1.8.
    """
    norm_x = max(0.08, min(0.92, (lon - (-8.6)) / (1.8 - (-8.6))))
    norm_y = max(0.08, min(0.92, 1.0 - (lat - 49.8) / (60.9 - 49.8)))
    cx = round(4 + norm_x * 30, 1)
    cy = round(4 + norm_y * 38, 1)

    return clean_html(f"""
    <svg width="38" height="46" viewBox="0 0 38 46" fill="none"
         style="background:#0B111E;border:1px solid rgba(148,163,184,0.22);border-radius:6px;flex-shrink:0;"
         title="UK Locator ({lat:.4f}, {lon:.4f})">
      <path d="M18 5 L23 7 L21 13 L25 17 L24 23 L28 29 L29 36 L26 39 L15 41 L12 38 L16 33 L14 27 L17 21 L14 14 Z"
            fill="#132235" stroke="#38BDF8" stroke-opacity="0.55" stroke-width="1.1"/>
      <path d="M7 22 L12 21 L13 26 L8 27 Z"
            fill="#132235" stroke="#38BDF8" stroke-opacity="0.55" stroke-width="1.1"/>
      <circle cx="{cx}" cy="{cy}" r="5.0" fill="rgba(34,211,238,0.25)"/>
      <circle cx="{cx}" cy="{cy}" r="2.6" fill="#22D3EE" stroke="#F8FAFC" stroke-width="1.0"/>
    </svg>
    """)


def crop_icon_svg(icon_type: str) -> str:
    """Return a clean inline SVG icon for a crop category."""
    t = icon_type.lower().strip()
    if t == "legume":
        return (
            '<svg width="16" height="16" viewBox="0 0 20 20" fill="none">'
            '<path d="M5 15C5 9 9 5 15 5C15 11 11 15 5 15Z" stroke="#10B981" stroke-width="1.7"/>'
            '<circle cx="8.5" cy="11.5" r="1.3" fill="#10B981"/>'
            '<circle cx="11.5" cy="8.5" r="1.3" fill="#10B981"/>'
            "</svg>"
        )
    if t == "root":
        return (
            '<svg width="16" height="16" viewBox="0 0 20 20" fill="none">'
            '<path d="M10 4V7M7 5L10 7L13 5" stroke="#10B981" stroke-width="1.5" stroke-linecap="round"/>'
            '<path d="M6.5 7.5H13.5L10 16.5L6.5 7.5Z" stroke="#F59E0B" stroke-width="1.6" stroke-linejoin="round"/>'
            "</svg>"
        )
    if t == "forage":
        return (
            '<svg width="16" height="16" viewBox="0 0 20 20" fill="none">'
            '<path d="M6 16V8M10 16V5M14 16V9" stroke="#10B981" stroke-width="1.8" stroke-linecap="round"/>'
            "</svg>"
        )
    if t == "brassica":
        return (
            '<svg width="16" height="16" viewBox="0 0 20 20" fill="none">'
            '<circle cx="10" cy="10" r="5.5" stroke="#22D3EE" stroke-width="1.6"/>'
            '<circle cx="10" cy="10" r="2.2" fill="#10B981"/>'
            "</svg>"
        )
    # Default: grain
    return (
        '<svg width="16" height="16" viewBox="0 0 20 20" fill="none">'
        '<path d="M10 17V4M10 6L7 4M10 6L13 4M10 10L7 8M10 10L13 8M10 14L7 12M10 14L13 12" '
        'stroke="#F59E0B" stroke-width="1.6" stroke-linecap="round"/>'
        "</svg>"
    )


def render_diagnostics_drawer(key_prefix: str = "diag") -> None:
    """
    Render the Diagnostics drawer containing:
    1. Outbound Call Log (timestamp, endpoint, grid cell, run ID, status — never secrets).
       Proves 0 outbound calls occur while phase == 'pick' (and in Stage 1).
    2. Dev-only Preview Switches (Section 7 Stage 1 requirement: every state from Section 5
       reachable via a dev-only preview switch in Diagnostics).
    3. Fault-injection toggle (Force primary model fail to test fallback).
    """
    calls = get_outbound_calls()
    phase = st.session_state.get("phase", "pick")

    with st.expander(
        f"Diagnostics & Outbound Call Log ({len(calls)} outbound calls recorded · phase={phase})",
        expanded=False,
    ):
        c1, c2, c3 = st.columns([1.4, 1.3, 1.3])
        with c1:
            st.markdown(
                '<div class="oa-label">OUTBOUND API CALL LOG (PROVES CONFIRM GATING)</div>',
                unsafe_allow_html=True,
            )
            if not calls:
                st.markdown(
                    '<div style="font-family:var(--font-mono);font-size:12px;color:#10B981;'
                    'background:#0B111E;padding:8px 10px;border-radius:6px;border:1px solid rgba(16,185,129,0.28);">'
                    "0 outbound calls recorded (No Open-Meteo or Gemini calls made)."
                    "</div>",
                    unsafe_allow_html=True,
                )
            else:
                rows_html = ""
                for entry in reversed(calls[-12:]):
                    rows_html += (
                        f"<div style='font-family:var(--font-mono);font-size:11px;color:#9AA8BC;"
                        f"padding:3px 0;border-bottom:1px solid rgba(148,163,184,0.1);'>"
                        f"<span style='color:#22D3EE;'>{html.escape(entry['ts'])}</span> · "
                        f"<b>{html.escape(entry['endpoint'])}</b> · "
                        f"grid={html.escape(entry['grid_cell'])} · "
                        f"run={html.escape(entry['run_id'])} · "
                        f"<span style='color:#10B981;'>{html.escape(entry['status'])}</span> "
                        f"({entry['latency_ms']}ms)"
                        f"</div>"
                    )
                st.markdown(
                    f"<div style='max-height:130px;overflow-y:auto;background:#0B111E;padding:6px 10px;"
                    f"border-radius:6px;border:1px solid rgba(148,163,184,0.16);'>{rows_html}</div>",
                    unsafe_allow_html=True,
                )

        with c2:
            st.markdown(
                '<div class="oa-label">DEV PREVIEW: SCREEN &amp; SECTION 5 STATES</div>',
                unsafe_allow_html=True,
            )
            nav_cols = st.columns(3)
            if nav_cols[0].button("Screen 1: Pick", key=f"{key_prefix}_go_pick", use_container_width=True):
                st.session_state.phase = "pick"
                st.rerun()
            if nav_cols[1].button("Screen 2: Analyse", key=f"{key_prefix}_go_analyse", use_container_width=True):
                if not st.session_state.get("confirmed_selection"):
                    from globe_component import validate_uk_coordinate
                    chk = validate_uk_coordinate(52.2053, 0.1218)
                    st.session_state.confirmed_selection = {
                        "run_id": "run_preview",
                        "lat": 52.2053,
                        "lon": 0.1218,
                        "local_time": now_london_str(),
                        "source": "dev_preview",
                        **chk,
                    }
                    st.session_state.run_id = "run_preview"
                st.session_state.phase = "analyse"
                st.rerun()
            if nav_cols[2].button("Screen 3: Outlook", key=f"{key_prefix}_go_outlook", use_container_width=True):
                if not st.session_state.get("confirmed_selection"):
                    from globe_component import validate_uk_coordinate
                    chk = validate_uk_coordinate(52.2053, 0.1218)
                    st.session_state.confirmed_selection = {
                        "run_id": "run_preview",
                        "lat": 52.2053,
                        "lon": 0.1218,
                        "local_time": now_london_str(),
                        "source": "dev_preview",
                        **chk,
                    }
                    st.session_state.run_id = "run_preview"
                st.session_state.phase = "outlook"
                st.rerun()

        with c3:
            s2_idx = (
                SCREEN2_PREVIEW_STATES.index(st.session_state.dev_screen2_state)
                if st.session_state.dev_screen2_state in SCREEN2_PREVIEW_STATES
                else 0
            )
            new_s2 = st.selectbox(
                "Screen 2 State (Section 5)",
                options=SCREEN2_PREVIEW_STATES,
                index=s2_idx,
                key=f"{key_prefix}_s2_sel",
            )
            if new_s2 != st.session_state.dev_screen2_state:
                st.session_state.dev_screen2_state = new_s2
                st.rerun()

            s3_idx = (
                SCREEN3_PREVIEW_STATES.index(st.session_state.dev_screen3_state)
                if st.session_state.dev_screen3_state in SCREEN3_PREVIEW_STATES
                else 0
            )
            new_s3 = st.selectbox(
                "Screen 3 State (Section 5)",
                options=SCREEN3_PREVIEW_STATES,
                index=s3_idx,
                key=f"{key_prefix}_s3_sel",
            )
            if new_s3 != st.session_state.dev_screen3_state:
                st.session_state.dev_screen3_state = new_s3
                st.rerun()

            force_fail = st.checkbox(
                "Force primary model fail (test fallback)",
                value=bool(st.session_state.get("force_model_fail", False)),
                key=f"{key_prefix}_force_fail_chk",
                help="Simulates primary Gemini model failure on Screen 2 to demonstrate automatic fallback to secondary model / deterministic rules.",
            )
            if force_fail != bool(st.session_state.get("force_model_fail", False)):
                st.session_state.force_model_fail = force_fail
                st.rerun()
