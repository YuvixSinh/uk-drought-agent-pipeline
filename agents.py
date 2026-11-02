"""
Three Sequential Streamed Gemini Agents (Stage 4 & Section 1/2/3/6/8/10) — Orbital Agronomist (v2)
Implements:
- Agent 1: Weather & Soil Moisture Analyst -> validates against Agent1Output
- Agent 2: Drought & Horizon Analyst       -> validates against Agent2Output
- Agent 3: UK Crop & Planting Advisor      -> validates against Agent3Output
- Verified Gemini 3 config:
  * Primary model  : gemini-3-flash-preview
  * Fallback model : gemini-3.1-flash-lite-preview
  * NEVER uses Gemini 1.5, Gemini 2.5, or Argon 4.
  * ThinkingConfig(thinking_level=ThinkingLevel.LOW, include_thoughts=False)
  * HttpOptions(timeout=20000) (>= 10,000 ms minimum deadline)
- 3-tier resilience chain per agent:
  Primary Gemini -> Fallback Gemini -> Deterministic Heuristic Template
- Real-time streaming callbacks (`on_chunk`, `on_status`) and `is_cancelled` check
  so Screen 2 updates inside a single Streamlit script run without reruns.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from dotenv import load_dotenv
from google import genai
from google.genai import types

from events import append_feed_event, log_outbound_call
from schemas import Agent1Output, Agent2Output, Agent3Output, ProtectPrepareCard

load_dotenv()

PRIMARY_MODEL = "gemini-3-flash-preview"
FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"
FORBIDDEN_SUBSTRINGS = ("1.5", "2.5", "argon")

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _assert_allowed_model(model_id: str) -> None:
    low = model_id.lower()
    for bad in FORBIDDEN_SUBSTRINGS:
        if bad in low:
            raise ValueError(f"Forbidden model ID blocked by policy: {model_id}")


def _build_client() -> genai.Client | None:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        return None
    return genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=20000),
    )


def _extract_narrative_preview(raw_json_buffer: str) -> str:
    """
    Extract readable streaming text from partial JSON while `public_narrative` is streaming,
    so the user sees clean prose in the War Room card rather than raw JSON braces.
    """
    marker = '"public_narrative"'
    idx = raw_json_buffer.find(marker)
    if idx == -1:
        return raw_json_buffer.strip()[:360]
    after = raw_json_buffer[idx + len(marker) :]
    colon = after.find(":")
    if colon == -1:
        return "Generating structured agronomic assessment…"
    after_colon = after[colon + 1 :].lstrip()
    if not after_colon.startswith('"'):
        return after_colon[:360]
    content = after_colon[1:]
    # Read until unescaped quote if present
    out_chars: list[str] = []
    escaped = False
    for ch in content:
        if escaped:
            out_chars.append(ch)
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            break
        else:
            out_chars.append(ch)
    return "".join(out_chars).strip()


# ---------------------------------------------------------------------------
# Deterministic Tier-3 Heuristic Fallbacks (Schema-Valid)
# ---------------------------------------------------------------------------
def build_deterministic_a1(ind: dict[str, Any], sel: dict[str, Any]) -> Agent1Output:
    grid = ind.get("grid_cell", sel.get("grid_cell", "52.20°N, 0.10°E"))
    admin = sel.get("admin_area", "England")
    r30 = ind["rain_30d_mm"]
    m30 = ind["mean_10y_30d_mm"]
    anom = ind["rain_30d_anom_pct"]
    et0 = ind["et0_30d_mm"]
    pet = ind["p_minus_et0_30d_mm"]
    dry14 = ind["dry_days_14d"]
    sm0 = ind["sm_0_7_now"]
    sm7 = ind["sm_7_28_now"]
    sm28 = ind["sm_28_100_now"]
    pct = ind["root_zone_pct"]
    chip = ind["chip_current"]

    narrative = (
        f"Across the past 30 days at UK grid {grid} ({admin}), modelled precipitation totalled {r30:.1f} mm "
        f"({anom:+d}% vs the 2016–2025 baseline mean of {m30:.1f} mm) against {et0:.1f} mm of FAO reference "
        f"evapotranspiration (net P−ET₀ balance {pet:+.1f} mm), with {dry14} dry days (<1 mm) in the last 14 days. "
        f"Open-Meteo volumetric soil moisture stands at {sm0:.2f} m³/m³ in topsoil (0–7 cm), {sm7:.2f} m³/m³ in the "
        f"root zone (7–28 cm, {pct}th percentile), and {sm28:.2f} m³/m³ in deep subsoil (28–100 cm), placing "
        f"current dryness at {chip}. These values represent ~1–25 km grid model outputs rather than satellite or in-situ sensor data."
    )
    return Agent1Output(
        public_narrative=narrative,
        surface_moisture_state=f"0–7 cm at {sm0:.2f} m³/m³ ({chip})",
        deep_moisture_state=f"28–100 cm at {sm28:.2f} m³/m³ (root-zone {pct}th pct)",
        missing_facts_noted=[
            "In-situ soil texture, field capacity, and wilting point",
            "Local field drainage class and compaction profile",
        ],
        handoff_note=f"Takeaway: Current dryness is {chip} (30d rain {r30:.1f} mm, {anom:+d}% vs 10y mean; 7–28 cm soil moisture {sm7:.2f} m³/m³ at {pct}th pct).",
    )


def build_deterministic_a2(ind: dict[str, Any], a1_out: Agent1Output) -> Agent2Output:
    r15 = ind["rain_15d_mm"]
    e15 = ind["et0_15d_mm"]
    pet15 = ind["p_minus_et0_15d_mm"]
    sm_dir = ind["sm_15d_dir"]
    c15 = ind["chip_15d"]
    c13m = ind["chip_13m"]
    s_avail = ind["seasonal_available"]
    s_stats = ind.get("seasonal_stats", {})
    med_anom = ind.get("seasonal_med_anom_pct", 0)

    if s_avail:
        p25_a = s_stats.get("p25_anomaly_pct", -15)
        p75_a = s_stats.get("p75_anomaly_pct", 12)
        seasonal_sentence = (
            f"Over the 1–3 month horizon, the 50-member seasonal ensemble indicates {c13m} with a "
            f"{med_anom:+d}% median rainfall anomaly and interquartile range spanning {p25_a:+d}% to {p75_a:+d}% (low-to-moderate skill)."
        )
        sig_tag = f"1–3m {c13m} (median {med_anom:+d}%, IQR {p25_a:+d}..{p75_a:+d}%)"
        handoff = f"Takeaway: 7–15d {c15} (P−ET₀ {pet15:+.1f} mm, {sm_dir.lower()}); 1–3m {c13m} (ensemble median {med_anom:+d}%, wide IQR spread)."
    else:
        seasonal_sentence = (
            "The 1–3 month horizon is marked INCONCLUSIVE because the seasonal ensemble endpoint did not return data."
        )
        sig_tag = "1–3m INCONCLUSIVE (seasonal endpoint unavailable)"
        handoff = f"Takeaway: 7–15d {c15} (P−ET₀ {pet15:+.1f} mm, {sm_dir.lower()}); 1–3m INCONCLUSIVE (seasonal endpoint unavailable)."

    narrative = (
        f"Building on Agent 1 ({a1_out.surface_moisture_state}), the next 7–15 days project {r15:.1f} mm of rainfall "
        f"against {e15:.1f} mm of FAO ET₀ (net P−ET₀ {pet15:+.1f} mm), placing the short-term horizon at {c15} "
        f"with root-zone moisture trajectory rated as {sm_dir.lower()}. {seasonal_sentence}"
    )
    return Agent2Output(
        public_narrative=narrative,
        evidence_for_concern=f"30d anomaly {ind['rain_30d_anom_pct']:+d}% and 15d P−ET₀ of {pet15:+.1f} mm.",
        evidence_against_concern=f"Subsoil 28–100 cm holds {ind['sm_28_100_now']:.2f} m³/m³ and autumn ET₀ demand is seasonally low.",
        seasonal_signal_tag=sig_tag,
        handoff_note=handoff,
    )


def build_deterministic_a3(
    ind: dict[str, Any],
    crops_res: dict[str, Any],
    sel: dict[str, Any],
    a2_out: Agent2Output,
) -> Agent3Output:
    admin = crops_res.get("admin", sel.get("admin_area", "England"))
    month_name = crops_res.get("month_name", "October")
    stemp = crops_res.get("soil_temp_c", 9.8)
    c_list = crops_res.get("candidates_ui", [])
    names = [c["name"] for c in c_list]
    names_joined = ", ".join(names)

    narrative = (
        f"Given {admin}'s {month_name} photoperiod, modelled 0–7 cm soil temperature ({stemp:.1f} °C), and "
        f"horizon status ({ind['chip_current']} current / {ind['chip_15d']} 7–15d), plausible weather-based regional "
        f"candidates are {names_joined}. Deep-rooting and hardy autumn options match current subsoil moisture "
        f"({ind['sm_28_100_now']:.2f} m³/m³), provided seedbed consolidation preserves surface moisture. "
        f"Crucially, Open-Meteo grid data cannot verify whether the selected coordinate is arable land, urban, "
        f"parkland, peat, or upland — verify actual land cover, soil texture, pH, and drainage on the ground."
    )
    return Agent3Output(
        public_narrative=narrative,
        crop_tags=[f"{c['name']}: {c['tag']}" for c in c_list],
        parcel_qualification="Weather-based regional candidates only; parcel land cover, soil type, drainage, and pH must be verified on the ground.",
        protect_actions=crops_res.get(
            "protect_card",
            ProtectPrepareCard(
                action_24_72h="Consolidate seedbeds lightly after drilling to conserve capillary moisture.",
                action_7d="Avoid high-axle-load passes on headlands where compaction limits root depth.",
                action_1_3m="Check winter water-storage / ditch capture capacity ahead of winter recharge.",
            ),
        ),
    )


# ---------------------------------------------------------------------------
# Single-Agent Streaming Runner with Primary -> Fallback -> Heuristic Chain
# ---------------------------------------------------------------------------
def _stream_single_agent(
    agent_id: str,
    prompt: str,
    schema_cls: type[Agent1Output] | type[Agent2Output] | type[Agent3Output],
    deterministic_builder: Callable[[], Any],
    grid_cell: str,
    run_id: str,
    primary_model: str = PRIMARY_MODEL,
    fallback_model: str = FALLBACK_MODEL,
    force_primary_fail: bool = False,
    on_chunk: Callable[[str, str, str, str], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Stream structured JSON from Gemini using `generate_content_stream`, validate with Pydantic,
    and automatically fall back to `fallback_model` and then `deterministic_builder` on error.
    """
    _assert_allowed_model(primary_model)
    _assert_allowed_model(fallback_model)

    client = _build_client()
    models_to_try: list[tuple[str, str]] = []
    if client is not None:
        if not force_primary_fail:
            models_to_try.append((primary_model, "LIVE"))
        else:
            append_feed_event(
                run_id,
                f"{agent_id} {primary_model}",
                "Fault-injection active: simulating primary model deadline exceeded -> switching to fallback model...",
                "warn",
            )
        models_to_try.append((fallback_model, "FALLBACK" if force_primary_fail else "LIVE"))

    for idx, (model_id, tier_badge) in enumerate(models_to_try):
        if is_cancelled and is_cancelled():
            return {"status": "cancelled", "model_used": model_id, "output": None, "elapsed_ms": 0}

        t0 = time.perf_counter()
        append_feed_event(
            run_id,
            f"{agent_id} {model_id}",
            f"Streaming structured {schema_cls.__name__} analysis...",
            "ai",
        )
        if on_chunk:
            on_chunk(agent_id, model_id, "streaming", "Connecting to Gemini stream…")

        buffer = ""
        try:
            assert client is not None
            cfg = types.GenerateContentConfig(
                temperature=0.2,
                max_output_tokens=2048,
                response_mime_type="application/json",
                response_schema=schema_cls,
                thinking_config=types.ThinkingConfig(
                    thinking_level=types.ThinkingLevel.LOW,
                    include_thoughts=False,
                ),
            )
            stream = client.models.generate_content_stream(
                model=model_id,
                contents=prompt,
                config=cfg,
            )
            for chunk in stream:
                if is_cancelled and is_cancelled():
                    append_feed_event(
                        run_id,
                        f"{agent_id} {model_id}",
                        "Run cancelled by user during streaming; discarding late chunks.",
                        "err",
                    )
                    return {"status": "cancelled", "model_used": model_id, "output": None, "elapsed_ms": int((time.perf_counter() - t0) * 1000)}
                txt = getattr(chunk, "text", None) or ""
                if txt:
                    buffer += txt
                    preview = _extract_narrative_preview(buffer)
                    if on_chunk and preview:
                        on_chunk(agent_id, model_id, "streaming", preview)

            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            validated = schema_cls.model_validate_json(buffer)
            log_outbound_call(
                endpoint=f"Gemini {model_id} ({agent_id})",
                grid_cell=grid_cell,
                run_id=run_id,
                status="200 OK (STREAM)" if idx == 0 and not force_primary_fail else "200 OK (FALLBACK STREAM)",
                latency_ms=elapsed_ms,
            )
            status_code = "fallback" if (idx > 0 or force_primary_fail) else "done"
            append_feed_event(
                run_id,
                f"{agent_id} {model_id}",
                f"Completed in {elapsed_ms} ms (schema validated: {schema_cls.__name__})",
                "ok",
            )
            return {
                "status": status_code,
                "source_state": "FALLBACK" if status_code == "fallback" else "LIVE",
                "product_kind": "AI-GENERATED",
                "model_used": model_id,
                "output": validated,
                "elapsed_ms": elapsed_ms,
            }
        except Exception as exc:
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            log_outbound_call(
                endpoint=f"Gemini {model_id} ({agent_id})",
                grid_cell=grid_cell,
                run_id=run_id,
                status=f"ERR ({type(exc).__name__})",
                latency_ms=elapsed_ms,
            )
            append_feed_event(
                run_id,
                f"{agent_id} {model_id}",
                f"Model stream error ({type(exc).__name__}) after {elapsed_ms} ms; escalating to next fallback tier...",
                "warn",
            )

    # Tier 3: Deterministic schema-valid fallback
    t0 = time.perf_counter()
    det_output = deterministic_builder()
    elapsed_ms = max(2, int((time.perf_counter() - t0) * 1000))
    append_feed_event(
        run_id,
        f"{agent_id} HEURISTIC",
        f"Rendered deterministic rule-based {schema_cls.__name__} fallback in {elapsed_ms} ms",
        "warn",
    )
    return {
        "status": "fallback",
        "source_state": "FALLBACK",
        "product_kind": "HEURISTIC",
        "model_used": f"{fallback_model} (heuristic-fallback)",
        "output": det_output,
        "elapsed_ms": elapsed_ms,
    }


def run_sequential_agents(
    indicators: dict[str, Any],
    crops_res: dict[str, Any],
    selection: dict[str, Any],
    run_id: str,
    primary_model: str = PRIMARY_MODEL,
    fallback_model: str = FALLBACK_MODEL,
    force_model_fail: bool = False,
    use_cache: bool = True,
    on_chunk: Callable[[str, str, str, str], None] | None = None,
    on_agent_done: Callable[[str, dict[str, Any]], None] | None = None,
    is_cancelled: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    """
    Execute Agent 1 -> Agent 2 -> Agent 3 sequentially.
    Each agent receives the previous agent's validated structured output (`handoff_note`).
    Caches validated outputs to disk so offline cached replay works without network calls.
    """
    grid = indicators.get("grid_cell", selection.get("grid_cell", "52.20°N, 0.10°E"))
    admin = crops_res.get("admin", selection.get("admin_area", "England"))
    cache_sig = f"{grid}_{indicators['rain_30d_mm']}_{indicators['rain_15d_mm']}_{indicators['chip_current']}_{indicators['chip_13m']}_{force_model_fail}"
    cache_hash = hashlib.sha256(cache_sig.encode("utf-8")).hexdigest()[:12]
    cpath = CACHE_DIR / f"agents_{cache_hash}.json"

    # Prompt 1: Agent 1 (Weather & Soil Moisture Analyst)
    p1 = (
        f"You are Agent 1 (Weather & Soil Moisture Analyst) for Orbital Agronomist UK.\n"
        f"Location: {selection.get('land_status', admin)} (coordinate {selection.get('lat')}, {selection.get('lon')}, model grid {grid}).\n"
        f"Modelled Open-Meteo Evidence:\n"
        f"- Past 30-day rainfall: {indicators['rain_30d_mm']} mm ({indicators['rain_30d_anom_pct']:+d}% vs 2016–2025 mean of {indicators['mean_10y_30d_mm']} mm)\n"
        f"- Past 30-day FAO ET0: {indicators['et0_30d_mm']} mm (P - ET0 = {indicators['p_minus_et0_30d_mm']:+.1f} mm)\n"
        f"- Dry days (<1 mm) in last 14 days: {indicators['dry_days_14d']}/14 (longest spell {indicators['longest_dry_14d']}d)\n"
        f"- Volumetric soil moisture: 0-7cm = {indicators['sm_0_7_now']:.2f} m3/m3, 7-28cm = {indicators['sm_7_28_now']:.2f} m3/m3 ({indicators['root_zone_pct']}th pct), 28-100cm = {indicators['sm_28_100_now']:.2f} m3/m3\n"
        f"- Current Horizon Chip: {indicators['chip_current']}\n"
        f"Rules: Be concise (85-125 words in public_narrative). Never claim satellite NDVI/NDRE or in-situ sensor measurements. "
        f"Start handoff_note with 'Takeaway: '."
    )

    a1_res = _stream_single_agent(
        agent_id="A1",
        prompt=p1,
        schema_cls=Agent1Output,
        deterministic_builder=lambda: build_deterministic_a1(indicators, selection),
        grid_cell=grid,
        run_id=run_id,
        primary_model=primary_model,
        fallback_model=fallback_model,
        force_primary_fail=False,
        on_chunk=on_chunk,
        is_cancelled=is_cancelled,
    )
    if a1_res["status"] == "cancelled":
        return {"cancelled": True, "a1": a1_res, "a2": None, "a3": None}
    a1_out: Agent1Output = a1_res["output"]
    if on_agent_done:
        on_agent_done("A1", a1_res)

    # Prompt 2: Agent 2 (Drought & Horizon Analyst)
    p2 = (
        f"You are Agent 2 (Drought & Horizon Analyst) for Orbital Agronomist UK.\n"
        f"Agent 1 Handoff: {a1_out.handoff_note}\n"
        f"Next 15-Day Forecast & 1-3 Month Seasonal Ensemble for grid {grid}:\n"
        f"- Next 15-day rain: {indicators['rain_15d_mm']} mm vs FAO ET0 {indicators['et0_15d_mm']} mm (net P-ET0 {indicators['p_minus_et0_15d_mm']:+.1f} mm)\n"
        f"- 15-day 7-28cm soil moisture direction: {indicators['sm_15d_dir']} (projected {indicators['sm_7_28_end']:.2f} m3/m3)\n"
        f"- 7-15d Horizon Chip: {indicators['chip_15d']}\n"
        f"- 1-3m Seasonal Ensemble available: {indicators['seasonal_available']}, 1-3m Chip: {indicators['chip_13m']}, "
        f"median anomaly: {indicators['seasonal_med_anom_pct']:+d}%, stats: {json.dumps(indicators.get('seasonal_stats', {}) | {'member_totals_90d': []})}\n"
        f"Rules: Be concise (85-125 words in public_narrative). Separate 7-15d weather forecast from 1-3m low-to-moderate skill seasonal ensemble. "
        f"Start handoff_note with 'Takeaway: '."
    )

    a2_res = _stream_single_agent(
        agent_id="A2",
        prompt=p2,
        schema_cls=Agent2Output,
        deterministic_builder=lambda: build_deterministic_a2(indicators, a1_out),
        grid_cell=grid,
        run_id=run_id,
        primary_model=primary_model,
        fallback_model=fallback_model,
        force_primary_fail=force_model_fail,
        on_chunk=on_chunk,
        is_cancelled=is_cancelled,
    )
    if a2_res["status"] == "cancelled":
        return {"cancelled": True, "a1": a1_res, "a2": a2_res, "a3": None}
    a2_out: Agent2Output = a2_res["output"]
    if on_agent_done:
        on_agent_done("A2", a2_res)

    # Prompt 3: Agent 3 (UK Crop & Planting Advisor)
    cand_summary = [
        {"name": c["name"], "tag": c["tag"], "window": c["window"], "watch": c["watch"]}
        for c in crops_res.get("candidates_ui", [])
    ]
    p3 = (
        f"You are Agent 3 (UK Crop & Planting Advisor) for Orbital Agronomist UK.\n"
        f"Agent 1 Handoff: {a1_out.handoff_note}\n"
        f"Agent 2 Handoff: {a2_out.handoff_note}\n"
        f"Region: {admin}, Month: {crops_res.get('month_name')}, Modelled 0-7cm Soil Temp: {crops_res.get('soil_temp_c')} C.\n"
        f"Deterministic Rule-Table Candidates: {json.dumps(cand_summary)}\n"
        f"Rules: Be concise (85-125 words in public_narrative). Explicitly state that these are regional weather-based candidates "
        f"and never assert that the clicked coordinate is farmable without ground verification of land cover, soil texture, drainage, and pH."
    )

    a3_res = _stream_single_agent(
        agent_id="A3",
        prompt=p3,
        schema_cls=Agent3Output,
        deterministic_builder=lambda: build_deterministic_a3(indicators, crops_res, selection, a2_out),
        grid_cell=grid,
        run_id=run_id,
        primary_model=primary_model,
        fallback_model=fallback_model,
        force_primary_fail=False,
        on_chunk=on_chunk,
        is_cancelled=is_cancelled,
    )
    if a3_res["status"] == "cancelled":
        return {"cancelled": True, "a1": a1_res, "a2": a2_res, "a3": a3_res}
    if on_agent_done:
        on_agent_done("A3", a3_res)

    # Save to disk cache for offline replay
    try:
        cpath.write_text(
            json.dumps({
                "saved_at": time.time(),
                "a1": {**a1_res, "output": a1_res["output"].model_dump()},
                "a2": {**a2_res, "output": a2_res["output"].model_dump()},
                "a3": {**a3_res, "output": a3_res["output"].model_dump()},
            }),
            encoding="utf-8",
        )
    except Exception:
        pass

    return {
        "cancelled": False,
        "a1": a1_res,
        "a2": a2_res,
        "a3": a3_res,
    }
