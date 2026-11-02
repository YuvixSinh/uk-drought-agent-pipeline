"""
Run State Machine & SSE Event Streamer — Orbital Agronomist (v5)
Manages the lifecycle (`RUNNING` -> `DONE` | `PARTIAL` | `CANCELLED`), enforces single
active run semantics, runs the real Open-Meteo + indicators + crop rules + sequential
Gemini 3 pipeline in a worker thread, and streams replayable Server-Sent Events (SSE).
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from web.backend.adapters import (
    FALLBACK_MODEL,
    PRIMARY_MODEL,
    assemble_result_payload,
    compute_10y_window_stats,
    compute_drought_indicators,
    fetch_10y_baseline,
    fetch_forecast_and_recent,
    fetch_seasonal_ensemble,
    match_uk_crops,
    now_london_str,
    run_sequential_agents,
    validate_point,
)
from web.backend.api_models import ResultPayload, ValidateResponse


@dataclass
class RunSession:
    run_id: str
    lat: float
    lon: float
    force_model_fail: bool
    location: ValidateResponse
    state: str = "RUNNING"  # RUNNING | DONE | PARTIAL | CANCELLED
    cancelled: bool = False
    events: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    feed: list[dict[str, Any]] = field(default_factory=list)
    result: ResultPayload | None = None
    condition: threading.Condition = field(default_factory=threading.Condition)
    created_at: float = field(default_factory=time.time)

    def emit(self, event_type: str, data: dict[str, Any]) -> None:
        with self.condition:
            if self.cancelled and event_type not in ("error",):
                return
            payload = {"ts": now_london_str(include_ms=True), **data}
            self.events.append((event_type, payload))
            self.condition.notify_all()

    def add_feed(self, source: str, ev_type: str, text: str) -> None:
        with self.condition:
            if self.cancelled:
                return
            self.feed.append({
                "ts": now_london_str(include_ms=True),
                "source": source,
                "type": ev_type,
                "text": text,
            })


class RunManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runs: dict[str, RunSession] = {}
        self._active_run_id: str | None = None

    def start_run(self, lat: float, lon: float, force_model_fail: bool = False) -> RunSession:
        loc = validate_point(lat, lon)
        if not loc.valid:
            raise ValueError("Not UK land. No data requested.")

        with self._lock:
            # Cancel any previous active run per Section 3.3 & Section 5
            if self._active_run_id and self._active_run_id in self._runs:
                prev = self._runs[self._active_run_id]
                if prev.state == "RUNNING":
                    prev.cancelled = True
                    prev.state = "CANCELLED"
                    with prev.condition:
                        prev.events.append(("error", {"ts": now_london_str(True), "run_id": prev.run_id, "message": "Superseded by new run"}))
                        prev.condition.notify_all()

            run_id = f"run-{uuid.uuid4().hex[:8]}"
            session = RunSession(
                run_id=run_id,
                lat=lat,
                lon=lon,
                force_model_fail=force_model_fail,
                location=loc,
            )
            self._runs[run_id] = session
            self._active_run_id = run_id

        t = threading.Thread(target=self._execute_pipeline, args=(session,), daemon=True)
        t.start()
        return session

    def get_run(self, run_id: str) -> RunSession | None:
        with self._lock:
            return self._runs.get(run_id)

    def cancel_run(self, run_id: str) -> bool:
        with self._lock:
            session = self._runs.get(run_id)
            if not session:
                return False
            session.cancelled = True
            session.state = "CANCELLED"
            with session.condition:
                session.events.append((
                    "error",
                    {"ts": now_london_str(True), "run_id": run_id, "message": "Run cancelled by user"},
                ))
                session.condition.notify_all()
            return True

    def _execute_pipeline(self, session: RunSession) -> None:
        run_id = session.run_id
        lat = session.lat
        lon = session.lon
        loc = session.location
        is_cancelled = lambda: session.cancelled

        selection = {
            "lat": lat,
            "lon": lon,
            "is_valid_uk_land": True,
            "admin_area": loc.nation or "England",
            "land_status": loc.label,
            "grid_cell": loc.grid_cell,
        }

        try:
            # Phase 1: Outer Ring Data Sources (Forecast, Soil Layers, 10-year Baseline, Seasonal Ensemble)
            session.emit("progress", {"pct": 6, "word": "Gathering", "ticker": "Fetching forecast and soil profile"})
            session.emit("source", {"id": "forecast", "state": "fetching", "summary": "GET /v1/forecast (30d past + 15d ahead)"})
            session.emit("source", {"id": "soil", "state": "fetching", "summary": "Reading 3-depth volumetric soil moisture"})

            if is_cancelled():
                return

            forecast_res = fetch_forecast_and_recent(lat, lon, run_id)
            if is_cancelled():
                return

            fc_st = "cached" if forecast_res.get("source_state") != "LIVE" else "done"
            fc_lat = int(forecast_res.get("latency_ms", 15))
            session.add_feed("OPEN-METEO", "SOURCE", f"Forecast & 3-depth soil moisture ({forecast_res.get('source_state')}) in {fc_lat} ms")
            session.emit("source", {"id": "forecast", "state": fc_st, "latency_ms": fc_lat, "summary": f"45 days loaded ({fc_lat} ms)"})

            session.emit("progress", {"pct": 18, "word": "Reading soil", "ticker": "Sampling 0–100 cm soil layers"})
            session.emit("source", {"id": "soil", "state": fc_st, "latency_ms": fc_lat, "summary": "3 soil layers (0–7, 7–28, 28–100 cm)"})

            # 10-year baseline
            session.emit("progress", {"pct": 28, "word": "Gathering", "ticker": "Loading 10-year climate baseline"})
            session.emit("source", {"id": "baseline", "state": "fetching", "summary": "2016–2025 daily archive"})
            baseline_res = fetch_10y_baseline(lat, lon, run_id)
            if is_cancelled():
                return

            base_stats = compute_10y_window_stats(baseline_res["payload"])
            base_st = "cached" if baseline_res.get("source_state") != "LIVE" else "done"
            base_lat = int(baseline_res.get("latency_ms", 5))
            session.add_feed("BASELINE", "SOURCE", f"10-year baseline 30d mean = {base_stats['mean_30d_rain_mm']} mm ({base_lat} ms)")
            session.emit("source", {"id": "baseline", "state": base_st, "latency_ms": base_lat, "summary": f"10y mean {base_stats['mean_30d_rain_mm']} mm ({base_lat} ms)"})

            # Seasonal ensemble
            session.emit("progress", {"pct": 38, "word": "Gathering", "ticker": "Querying 50-member seasonal ensemble"})
            session.emit("source", {"id": "seasonal", "state": "fetching", "summary": "GET /v1/seasonal (50 members)"})
            seasonal_res = fetch_seasonal_ensemble(
                lat,
                lon,
                run_id,
                baseline_90d_mm=float(base_stats.get("mean_90d_rain_mm", 165.0)),
            )
            if is_cancelled():
                return

            seas_avail = bool(seasonal_res.get("available"))
            seas_st = "failed" if not seas_avail else ("cached" if seasonal_res.get("source_state") != "LIVE" else "done")
            seas_lat = int(seasonal_res.get("latency_ms", 20))
            s_anom = seasonal_res.get("stats", {}).get("median_anomaly_pct", 0)
            session.add_feed(
                "SEASONAL",
                "SOURCE" if seas_avail else "FALLBACK",
                f"50-member seasonal ensemble: {s_anom:+d}% median anomaly ({seas_lat} ms)" if seas_avail else "Seasonal endpoint unavailable; 1–3m marked INCONCLUSIVE",
            )
            session.emit(
                "source",
                {
                    "id": "seasonal",
                    "state": seas_st,
                    "latency_ms": seas_lat,
                    "summary": f"50 members · {s_anom:+d}% median" if seas_avail else "Unavailable (INCONCLUSIVE)",
                },
            )

            # Phase 2: Deterministic Indicators & UK Crop Rule Matching
            session.emit("progress", {"pct": 46, "word": "Assessing", "ticker": "Computing water balance and horizons"})
            indicators = compute_drought_indicators(
                forecast_res=forecast_res,
                baseline_stats=base_stats,
                seasonal_res=seasonal_res,
                run_id=run_id,
                what_if=False,
                emit_events=False,
            )
            session.add_feed(
                "INDICATORS",
                "INDICATOR",
                f"30d rain {indicators['rain_30d_mm']} mm ({indicators['rain_30d_anom_pct']:+d}% vs 10y); SM 7–28cm {indicators['sm_7_28_now']:.2f} m³/m³ ({indicators['root_zone_pct']}th pct)",
            )
            session.emit(
                "compute",
                {
                    "id": "indicators",
                    "state": "done",
                    "summary": f"NOW={indicators['chip_current']} · 7–15d={indicators['chip_15d']} · 1–3m={indicators['chip_13m']}",
                },
            )

            crops_res = match_uk_crops(
                indicators=indicators,
                selection=selection,
                run_id=run_id,
                emit_events=False,
            )
            crop_names = ", ".join(c["name"].split(" (")[0] for c in crops_res.get("candidates_ui", []))
            session.add_feed("CROP-RULES", "INDICATOR", f"Matched UK candidates for {crops_res.get('admin')}: {crop_names}")
            session.emit("compute", {"id": "crops", "state": "done", "summary": f"Matched: {crop_names}"})

            if is_cancelled():
                return

            # Phase 3: Sequential Gemini 3 Agents (Meteorologist -> Hydrologist -> Agronomist)
            role_by_id = {
                "A1": "meteorologist",
                "A2": "hydrologist",
                "A3": "agronomist",
            }
            word_by_id = {
                "A1": ("Assessing", 58, "Meteorologist analysing soil moisture"),
                "A2": ("Assessing", 74, "Hydrologist evaluating drought horizons"),
                "A3": ("Planning", 88, "Agronomist matching UK crop windows"),
            }
            active_announced: set[str] = set()

            def _on_chunk(agent_code: str, model_id: str, status_str: str, preview_text: str) -> None:
                if is_cancelled():
                    return
                role = role_by_id.get(agent_code, "meteorologist")
                if agent_code not in active_announced:
                    active_announced.add(agent_code)
                    w_word, pct_val, tick_txt = word_by_id.get(agent_code, ("Assessing", 60, "Streaming agent analysis"))
                    session.emit("progress", {"pct": pct_val, "word": w_word, "ticker": tick_txt})
                    session.emit(
                        "agent",
                        {
                            "id": role,
                            "state": "active",
                            "model": model_id,
                            "mode": "LIVE",
                            "summary": f"Streaming {model_id}",
                        },
                    )
                session.emit(
                    "token",
                    {
                        "agent": role,
                        "model": model_id,
                        "text": preview_text,
                    },
                )

            def _on_agent_done(agent_code: str, res_dict: dict[str, Any]) -> None:
                if is_cancelled():
                    return
                role = role_by_id.get(agent_code, "meteorologist")
                st_str = "fallback" if res_dict.get("status") == "fallback" else "done"
                model_used = res_dict.get("model_used", PRIMARY_MODEL)
                mode_used = "FALLBACK" if st_str == "fallback" else "LIVE"
                out_obj = res_dict.get("output")
                takeaway = getattr(out_obj, "handoff_note", getattr(out_obj, "parcel_qualification", "Completed"))
                elapsed = int(res_dict.get("elapsed_ms", 0))

                session.add_feed(
                    f"{role.upper()} ({model_used})",
                    "FALLBACK" if st_str == "fallback" else "AGENT",
                    f"Completed in {elapsed} ms [{mode_used}] — {takeaway}",
                )
                session.emit(
                    "agent",
                    {
                        "id": role,
                        "state": st_str,
                        "model": model_used,
                        "mode": mode_used,
                        "latency_ms": elapsed,
                        "summary": takeaway,
                    },
                )

                if agent_code == "A1":
                    session.add_feed("HANDOFF", "HANDOFF", f"Meteorologist -> Hydrologist: {takeaway}")
                    session.emit(
                        "handoff",
                        {
                            "from": "meteorologist",
                            "to": "hydrologist",
                            "takeaway": takeaway,
                        },
                    )
                elif agent_code == "A2":
                    session.add_feed("HANDOFF", "HANDOFF", f"Hydrologist -> Agronomist: {takeaway}")
                    session.emit(
                        "handoff",
                        {
                            "from": "hydrologist",
                            "to": "agronomist",
                            "takeaway": takeaway,
                        },
                    )

            agents_res = run_sequential_agents(
                indicators=indicators,
                crops_res=crops_res,
                selection=selection,
                run_id=run_id,
                primary_model=PRIMARY_MODEL,
                fallback_model=FALLBACK_MODEL,
                force_model_fail=session.force_model_fail,
                use_cache=False,
                on_chunk=_on_chunk,
                on_agent_done=_on_agent_done,
                is_cancelled=is_cancelled,
            )

            if is_cancelled() or agents_res.get("cancelled"):
                session.state = "CANCELLED"
                return

            result_payload = assemble_result_payload(
                run_id=run_id,
                selection=selection,
                forecast_res=forecast_res,
                baseline_res=baseline_res,
                baseline_stats=base_stats,
                seasonal_res=seasonal_res,
                indicators=indicators,
                crops_res=crops_res,
                agents_res=agents_res,
                feed_events=list(session.feed),
                is_demo=False,
            )

            with session.condition:
                if session.cancelled:
                    return
                session.result = result_payload
                session.state = result_payload.state

            session.emit("progress", {"pct": 100, "word": "Done", "ticker": "Analysis complete"})
            session.emit("done", {"run_id": run_id, "state": result_payload.state})

        except Exception as exc:
            if not session.cancelled:
                session.state = "CANCELLED"
                session.emit("error", {"run_id": run_id, "message": f"Pipeline error: {type(exc).__name__}: {exc}"})


RUN_MANAGER = RunManager()


async def sse_event_generator(session: RunSession):
    """
    Async generator yielding formatted Server-Sent Events (SSE) for a RunSession.
    Replays any events already emitted since run start so fast sources are never missed.
    """
    idx = 0
    while True:
        batch: list[tuple[str, dict[str, Any]]] = []
        with session.condition:
            while idx < len(session.events):
                batch.append(session.events[idx])
                idx += 1
            is_terminal = session.state in ("DONE", "PARTIAL", "CANCELLED") and idx >= len(session.events)

        for ev_type, ev_data in batch:
            yield f"event: {ev_type}\ndata: {json.dumps(ev_data)}\n\n"
            if ev_type in ("done", "error"):
                return

        if is_terminal:
            return

        await asyncio.sleep(0.06)
