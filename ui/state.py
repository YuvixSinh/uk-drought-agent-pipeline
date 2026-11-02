"""
Session State & Phase State Machine (Section 2 & F13) — Orbital Agronomist (v2)
Implements the strict 3-screen phase machine: pick -> analyse -> outlook -> pick.
Keeps pending_selection, confirmed_selection, run_id, camera_pov, and results_history (max 3).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

import streamlit as st

from events import ensure_event_stores, now_london_str
from globe_component import validate_uk_coordinate

PRIMARY_MODEL_ID = "gemini-3-flash-preview"
FALLBACK_MODEL_ID = "gemini-3.1-flash-lite-preview"

SCREEN2_PREVIEW_STATES = [
    "live_or_default",
    "queued",
    "fetching",
    "indicators done",
    "agents running",
    "partial data",
    "offline cached replay",
    "cancelled",
    "error",
    "complete with countdown",
]

SCREEN3_PREVIEW_STATES = [
    "complete",
    "partial data",
    "offline",
    "unavailable panel area",
    "scenario active",
    "empty history",
]


def init_session_state() -> None:
    """Initialize all session state variables required by the PhaseState contract."""
    ensure_event_stores()

    defaults: dict[str, Any] = {
        "phase": "pick",
        "pending_selection": None,
        "confirmed_selection": None,
        "rejected_notice": None,
        "run_id": None,
        "cancelled_runs": set(),
        "camera_pov": {"lat": 54.5, "lng": -3.0, "altitude": 1.6},
        "results_history": [],
        "globe_sync_token": "init",
        "last_globe_event_ts": 0,
        "data_mode": "ONLINE",  # "ONLINE" or "OFFLINE-CACHE"
        "what_if_active": False,
        "replay_feed_open": False,
        "stay_on_analyse": False,
        "force_model_fail": False,
        "dev_screen2_state": "live_or_default",
        "dev_screen3_state": "complete",
        "active_run_bundle": None,
        "primary_model_id": PRIMARY_MODEL_ID,
        "fallback_model_id": FALLBACK_MODEL_ID,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

    # Handle URL query params for automated testing / deep-link preview in Stage 1
    qp = st.query_params
    if "preview_phase" in qp and st.session_state.get("_applied_qp") != dict(qp):
        st.session_state["_applied_qp"] = dict(qp)
        target_phase = qp.get("preview_phase", "pick")
        if target_phase in ("pick", "analyse", "outlook"):
            st.session_state.phase = target_phase
            if target_phase in ("analyse", "outlook") and not st.session_state.confirmed_selection:
                check = validate_uk_coordinate(52.2053, 0.1218)
                sel = {
                    "run_id": "run_demo01",
                    "lat": 52.2053,
                    "lon": 0.1218,
                    "local_time": now_london_str(),
                    "source": "chip:Cambridge",
                    **check,
                }
                st.session_state.pending_selection = sel
                st.session_state.confirmed_selection = sel
                st.session_state.run_id = "run_demo01"
        if "s2_state" in qp and qp["s2_state"] in SCREEN2_PREVIEW_STATES:
            st.session_state.dev_screen2_state = qp["s2_state"]
        if "s3_state" in qp and qp["s3_state"] in SCREEN3_PREVIEW_STATES:
            st.session_state.dev_screen3_state = qp["s3_state"]


def set_pending_coordinate(lat: float, lon: float, source: str = "globe_click") -> dict[str, Any]:
    """Validate a coordinate against UK 1:10m land polygons and update pending_selection."""
    check = validate_uk_coordinate(lat, lon)
    if check["valid"]:
        sel = {
            "run_id": None,
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "local_time": now_london_str(),
            "source": source,
            **check,
        }
        st.session_state.pending_selection = sel
        st.session_state["rejected_notice"] = None
        return sel
    else:
        st.session_state.pending_selection = None
        st.session_state["rejected_notice"] = {
            "lat": round(float(lat), 4),
            "lon": round(float(lon), 4),
            "message": "Not UK land. No data requested.",
            "ts": now_london_str(),
        }
        return check


def confirm_pending_selection() -> bool:
    """Transition from pick -> analyse ONLY if a valid UK-land pending selection exists."""
    pending = st.session_state.get("pending_selection")
    if not pending or not pending.get("valid"):
        return False
    new_run_id = f"run_{uuid.uuid4().hex[:8]}"
    confirmed = dict(pending)
    confirmed["run_id"] = new_run_id
    confirmed["local_time"] = now_london_str()
    st.session_state.confirmed_selection = confirmed
    st.session_state.run_id = new_run_id
    st.session_state.stay_on_analyse = False
    st.session_state.active_run_bundle = None
    st.session_state.dev_screen2_state = "live_or_default"
    st.session_state.phase = "analyse"
    return True


def cancel_active_analysis() -> None:
    """Transition from analyse -> pick, marking active run_id cancelled and keeping selection as pending."""
    rid = st.session_state.get("run_id")
    if rid:
        st.session_state.cancelled_runs.add(rid)
    if st.session_state.get("confirmed_selection") and not st.session_state.get("pending_selection"):
        st.session_state.pending_selection = dict(st.session_state.confirmed_selection)
    st.session_state.phase = "pick"
    st.session_state.globe_sync_token = f"cancel_restore_{time.time()}"


def advance_to_outlook() -> None:
    """Transition from analyse -> outlook."""
    st.session_state.phase = "outlook"


def return_to_pick() -> None:
    """Transition from outlook -> pick, preserving camera_pov and results_history (last 3)."""
    st.session_state.phase = "pick"
    st.session_state.what_if_active = False
    st.session_state.replay_feed_open = False
    st.session_state.globe_sync_token = f"return_restore_{time.time()}"
