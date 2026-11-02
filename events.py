"""
Event Queue, London Time & Outbound Call Logger (F3, F12) — Orbital Agronomist (v2)
Every outbound call is logged with timestamp, endpoint, grid cell, and run ID (never secrets).
No outbound call may happen while phase == 'pick'.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import streamlit as st

from schemas import FeedEvent, FeedEventType

LONDON_TZ = ZoneInfo("Europe/London")


def now_london_str(include_ms: bool = False) -> str:
    """Return current Europe/London time formatted for header or millisecond live feed."""
    dt = datetime.now(LONDON_TZ)
    if include_ms:
        return dt.strftime("%H:%M:%S.") + f"{int(dt.microsecond / 1000):03d}"
    return dt.strftime("%H:%M:%S %Z")


def now_london_iso() -> str:
    return datetime.now(LONDON_TZ).isoformat(timespec="seconds")


def ensure_event_stores() -> None:
    if "outbound_call_log" not in st.session_state:
        st.session_state.outbound_call_log = []
    if "feed_events_by_run" not in st.session_state:
        st.session_state.feed_events_by_run = {}


def log_outbound_call(
    endpoint: str,
    grid_cell: str,
    run_id: str,
    status: str = "OK",
    latency_ms: float | None = None,
) -> dict[str, Any]:
    """Record an outbound network or model call in the Diagnostics call log (never secrets)."""
    ensure_event_stores()
    ts_str = now_london_str(include_ms=True)
    entry = {
        "ts": ts_str,
        "timestamp": ts_str,
        "phase": st.session_state.get("phase", "pick"),
        "run_id": run_id,
        "endpoint": endpoint,
        "grid_cell": grid_cell,
        "status": status,
        "latency_ms": round(latency_ms, 1) if latency_ms is not None else 0,
    }
    st.session_state.outbound_call_log.append(entry)
    return entry


def get_outbound_calls() -> list[dict[str, Any]]:
    ensure_event_stores()
    return list(st.session_state.outbound_call_log)


def publish_feed_event(
    run_id: str,
    event_type: FeedEventType,
    source: str,
    text: str,
    payload: dict[str, Any] | None = None,
) -> FeedEvent:
    """Append a real-time FeedEvent to the run's feed log."""
    ensure_event_stores()
    ev = FeedEvent(
        run_id=run_id,
        ts=now_london_str(include_ms=True),
        type=event_type,
        source=source,
        text=text,
        payload=payload,
    )
    if run_id not in st.session_state.feed_events_by_run:
        st.session_state.feed_events_by_run[run_id] = []
    st.session_state.feed_events_by_run[run_id].append(ev.model_dump())
    return ev


def append_feed_event(
    run_id: str,
    source_or_type: str = "SOURCE",
    text: str = "",
    level: str = "info",
    *,
    event_type: FeedEventType | None = None,
    source: str | None = None,
    payload: dict[str, Any] | None = None,
) -> FeedEvent:
    """
    Flexible helper that accepts either:
      append_feed_event(run_id, "OPEN-METEO", "GET /v1/forecast...", "ok")
    or keyword arguments:
      append_feed_event(run_id=..., event_type="INDICATOR", source="CROP-RULES", text=...)
    """
    actual_source = source or source_or_type
    if event_type is not None:
        actual_type: FeedEventType = event_type
    elif actual_source in ("SOURCE", "INDICATOR", "AGENT", "HANDOFF", "FALLBACK", "ERROR"):
        actual_type = actual_source  # type: ignore[assignment]
    elif "INDICAT" in actual_source or "HORIZON" in actual_source or "CROP" in actual_source:
        actual_type = "INDICATOR"
    elif actual_source.startswith("A1") or actual_source.startswith("A2") or actual_source.startswith("A3"):
        actual_type = "AGENT"
    elif level == "err":
        actual_type = "ERROR"
    elif level == "warn":
        actual_type = "FALLBACK"
    else:
        actual_type = "SOURCE"

    merged_payload = dict(payload or {})
    merged_payload.setdefault("level", level)
    return publish_feed_event(
        run_id=run_id,
        event_type=actual_type,
        source=actual_source,
        text=text,
        payload=merged_payload,
    )


def get_feed_events(run_id: str | None) -> list[dict[str, Any]]:
    ensure_event_stores()
    if not run_id:
        return []
    return list(st.session_state.feed_events_by_run.get(run_id, []))
