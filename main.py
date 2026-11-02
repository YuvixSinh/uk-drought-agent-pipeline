"""
Orbital Agronomist — National Food Security Early Warning System
==================================================================
Hackathon: Google DeepMind - Halloween at Imperial (Gemini Edition)
Track:     Sustainability & Agriculture

WHAT THIS SCRIPT DOES
----------------------
Simulates a fleet of satellite-telemetry feeds (structured to mirror what
Google's Agricultural Understanding Platform would return — ALU for land/
water boundaries, AMED for crop + growth-stage monitoring) PLUS a simulated
climate/weather feed (structured like a Google Earth Engine climate dataset
pull). It fuses crop-growth-curve deviation, vegetation index (NDVI) decay,
soil moisture depletion and rainfall/temperature forecasts into a
deterministic risk model, then hands that structured evidence to a 4-agent
Gemini pipeline that reasons about WHEN a region will hit critical drought
stress and WHAT to do about it — all the way up to a national food-shortage
early warning report.

Design principle: maths is done in Python (numpy/pandas), LANGUAGE and
JUDGEMENT is done by Gemini. The LLM is never asked to invent numbers —
it is only asked to interpret, forecast in natural language, and advise,
using figures we calculated ourselves. This keeps the numeric forecast
reliable and keeps Gemini's job to what it's best at: synthesis & reasoning.

SETUP
-----
pip install streamlit google-genai python-dotenv pandas numpy
.env file in the same folder containing:  GEMINI_API_KEY=your_key_here

RUN (Windows)
-------------
py -m streamlit run app_v2.py

RUN (Mac/Linux)
---------------
streamlit run app_v2.py
"""

import os
import time
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

# ---------------------------------------------------------------------------
# 0. APP / CLIENT SETUP
# ---------------------------------------------------------------------------
load_dotenv()

st.set_page_config(
    page_title="Orbital Agronomist | Food Security EWS",
    page_icon="🛰️",
    layout="wide",
)

MODEL_PRIMARY = "gemini-2.5-pro"
MODEL_FALLBACK = "gemini-2.5-flash"
TODAY = datetime(2026, 10, 31)          # fixed "satellite pass" date for reproducible demo
CRITICAL_SOIL_MOISTURE = 12.0           # % volumetric water content considered "critical"
BASELINE_WEEKLY_RAINFALL_MM = 28.0      # 30-yr seasonal average used as the deficit benchmark


@st.cache_resource
def get_client():
    """Cached Gemini client — avoids re-authenticating on every Streamlit rerun."""
    return genai.Client()


client = get_client()

# ---------------------------------------------------------------------------
# 1. REGION CONFIG  (stand-ins for real ALU/AMED field IDs)
# ---------------------------------------------------------------------------
REGIONS_CONFIG = [
    {
        "id": "RGN-01", "name": "North Punjab Wheat Belt", "country": "India",
        "crop": "Wheat", "hectares": 1280, "max_height_cm": 95,
        "sowing_date": "2026-09-05", "stress_level": "severe",
        "water_bodies": ["Canal Irrigation Network", "Dug Wells (x14)"],
    },
    {
        "id": "RGN-02", "name": "Deccan Plateau Cotton Zone", "country": "India",
        "crop": "Cotton", "hectares": 860, "max_height_cm": 140,
        "sowing_date": "2026-08-20", "stress_level": "moderate",
        "water_bodies": ["Farm Ponds (x6)"],
    },
    {
        "id": "RGN-03", "name": "Nile Delta Rice Region", "country": "Egypt",
        "crop": "Rice", "hectares": 2100, "max_height_cm": 110,
        "sowing_date": "2026-09-10", "stress_level": "low",
        "water_bodies": ["River Irrigation Channel", "Reservoir"],
    },
    {
        "id": "RGN-04", "name": "Great Plains Corn Belt", "country": "USA",
        "crop": "Corn (Maize)", "hectares": 3400, "max_height_cm": 260,
        "sowing_date": "2026-08-15", "stress_level": "severe",
        "water_bodies": ["Center-Pivot Aquifer Wells"],
    },
]

# Rough typical yield benchmarks (tonnes/hectare) — used only to translate
# a % stress/yield-loss estimate into a tangible tonnage figure for the UI.
TYPICAL_YIELD_T_PER_HA = {
    "Wheat": 3.2, "Cotton": 0.5, "Rice": 4.0, "Corn (Maize)": 6.0,
}

STRESS_PARAMS = {
    "severe":   {"decline_rate": 0.012, "noise": 0.03, "ndvi_penalty": 0.35,
                 "rain_mult": 0.45, "temp_anom": 3.5, "moisture_drop": 34},
    "moderate": {"decline_rate": 0.006, "noise": 0.02, "ndvi_penalty": 0.18,
                 "rain_mult": 0.70, "temp_anom": 1.8, "moisture_drop": 18},
    "low":      {"decline_rate": 0.001, "noise": 0.015, "ndvi_penalty": 0.05,
                 "rain_mult": 0.95, "temp_anom": 0.5, "moisture_drop": 6},
}

# ---------------------------------------------------------------------------
# 2. SIMULATED SATELLITE + WEATHER TELEMETRY  (mock Google Cloud feed)
# ---------------------------------------------------------------------------

def _sigmoid_growth(days_since_sowing, max_height, growth_rate=0.08, midpoint=55):
    """Idealised crop-height growth curve (what the crop SHOULD look like)."""
    return max_height / (1 + np.exp(-growth_rate * (days_since_sowing - midpoint)))


def generate_region_telemetry(cfg, seed):
    """Builds 90 days of mock ALU/AMED satellite history + a 90-day weather
    forecast for one region, structured like a Google Agricultural
    Understanding Platform + climate-dataset payload."""
    rng = np.random.default_rng(seed)
    sp = STRESS_PARAMS[cfg["stress_level"]]

    hist_days = 90
    dates_hist = [TODAY - timedelta(days=hist_days - 1 - i) for i in range(hist_days)]
    sowing = datetime.strptime(cfg["sowing_date"], "%Y-%m-%d")
    days_since_sowing = np.clip(np.array([(d - sowing).days for d in dates_hist]), 0, None)

    # --- crop growth (AMED-style) ---
    expected_height = _sigmoid_growth(days_since_sowing, cfg["max_height_cm"])
    stress_curve = np.clip(
        1 - sp["decline_rate"] * np.arange(hist_days) + rng.normal(0, sp["noise"], hist_days),
        0.3, 1.05,
    )
    actual_height = np.clip(expected_height * stress_curve, 0, cfg["max_height_cm"])

    ndvi_healthy = 0.85 / (1 + np.exp(-0.07 * (days_since_sowing - 50)))
    ndvi = np.clip(
        ndvi_healthy - sp["ndvi_penalty"] * (np.arange(hist_days) / hist_days)
        + rng.normal(0, 0.02, hist_days),
        0.05, 0.9,
    )

    # --- soil moisture (AMED-style 30/90-day trend array) ---
    soil_moisture = np.clip(
        46 - sp["moisture_drop"] * (np.arange(hist_days) / (hist_days - 1))
        + rng.normal(0, 1.2, hist_days),
        2, 60,
    )

    # --- weather history + forecast (mock climate feed) ---
    n_weeks = 13  # ~90 days
    hist_rainfall = np.clip(
        BASELINE_WEEKLY_RAINFALL_MM * sp["rain_mult"] + rng.normal(0, 4, n_weeks), 0, None
    )
    forecast_rainfall = np.clip(
        BASELINE_WEEKLY_RAINFALL_MM * sp["rain_mult"] * 0.85 + rng.normal(0, 3, n_weeks), 0, None
    )
    hist_temp = 26 + sp["temp_anom"] * 0.6 + rng.normal(0, 1, n_weeks)
    forecast_temp = 26 + sp["temp_anom"] + rng.normal(0, 1, n_weeks)

    week_dates_hist = [TODAY - timedelta(weeks=n_weeks - 1 - i) for i in range(n_weeks)]
    week_dates_fcst = [TODAY + timedelta(weeks=i + 1) for i in range(n_weeks)]

    raw_json = {
        "alu_landscape_understanding": {
            "field_id": cfg["id"],
            "region_name": cfg["name"],
            "country": cfg["country"],
            "boundary_hectares": cfg["hectares"],
            "water_bodies_detected": cfg["water_bodies"],
            "class_confidence": round(float(rng.uniform(0.90, 0.98)), 2),
        },
        "amed_crop_monitoring": {
            "predicted_crop": cfg["crop"],
            "sowing_date": cfg["sowing_date"],
            "current_height_cm": round(float(actual_height[-1]), 1),
            "expected_height_cm": round(float(expected_height[-1]), 1),
            "ndvi_latest": round(float(ndvi[-1]), 2),
            "soil_moisture_trend_30_days": [round(float(v), 1) for v in soil_moisture[-30:]],
        },
        "climate_feed": {
            "baseline_weekly_rainfall_mm": BASELINE_WEEKLY_RAINFALL_MM,
            "last_4_weeks_rainfall_mm": [round(float(v), 1) for v in hist_rainfall[-4:]],
            "next_12_weeks_forecast_rainfall_mm": [round(float(v), 1) for v in forecast_rainfall],
            "next_12_weeks_forecast_temp_c": [round(float(v), 1) for v in forecast_temp],
        },
    }

    return {
        "cfg": cfg,
        "dates_hist": dates_hist,
        "expected_height": expected_height,
        "actual_height": actual_height,
        "ndvi": ndvi,
        "soil_moisture": soil_moisture,
        "week_dates_hist": week_dates_hist,
        "week_dates_fcst": week_dates_fcst,
        "hist_rainfall": hist_rainfall,
        "forecast_rainfall": forecast_rainfall,
        "hist_temp": hist_temp,
        "forecast_temp": forecast_temp,
        "raw_json": raw_json,
    }


def load_all_regions(seeds):
    return {cfg["id"]: generate_region_telemetry(cfg, seeds[cfg["id"]]) for cfg in REGIONS_CONFIG}


# ---------------------------------------------------------------------------
# 3. DETERMINISTIC RISK MODEL  (numpy does the maths, not the LLM)
# ---------------------------------------------------------------------------

def analyze_region(region_data):
    cfg = region_data["cfg"]
    last30 = region_data["soil_moisture"][-30:]
    x = np.arange(len(last30))
    slope, intercept = np.polyfit(x, last30, 1)

    days_to_critical = None
    if slope < -1e-6 and last30[-1] > CRITICAL_SOIL_MOISTURE:
        projected = max(0.0, (CRITICAL_SOIL_MOISTURE - last30[-1]) / slope)
        # Beyond ~6 months the linear extrapolation is no longer meaningful —
        # treat the region as "stable" rather than showing a speculative date.
        days_to_critical = projected if projected <= 180 else None

    rainfall_deficit_pct = float(
        (BASELINE_WEEKLY_RAINFALL_MM - np.mean(region_data["forecast_rainfall"]))
        / BASELINE_WEEKLY_RAINFALL_MM * 100
    )
    height_deficit_pct = float(
        (region_data["expected_height"][-1] - region_data["actual_height"][-1])
        / region_data["expected_height"][-1] * 100
    )

    score = 0.0
    score += 5 if days_to_critical is None else max(0.0, 40 - days_to_critical * 0.6)
    score += min(30.0, max(0.0, rainfall_deficit_pct) * 0.5)
    score += min(30.0, max(0.0, height_deficit_pct) * 0.8)
    score = float(np.clip(score, 0, 100))

    if score >= 70:
        category, color = "CRITICAL", "🔴"
    elif score >= 45:
        category, color = "HIGH", "🟠"
    elif score >= 25:
        category, color = "MODERATE", "🟡"
    else:
        category, color = "LOW", "🟢"

    yield_loss_pct = float(np.clip(height_deficit_pct * 0.9 + rainfall_deficit_pct * 0.3, 0, 90))
    tonnage_loss = cfg["hectares"] * TYPICAL_YIELD_T_PER_HA[cfg["crop"]] * yield_loss_pct / 100

    # build a short projection line for charting (history + forward trend)
    proj_dates, proj_values = [], []
    if days_to_critical is not None:
        proj_len = int(min(days_to_critical, 90)) + 1
        for k in range(proj_len):
            proj_dates.append(region_data["dates_hist"][-1] + timedelta(days=k))
            proj_values.append(intercept + slope * (len(last30) - 1 + k))

    return {
        "risk_score": score,
        "risk_category": category,
        "risk_emoji": color,
        "days_to_critical": days_to_critical,
        "rainfall_deficit_pct": rainfall_deficit_pct,
        "height_deficit_pct": height_deficit_pct,
        "yield_loss_pct": yield_loss_pct,
        "tonnage_loss": tonnage_loss,
        "proj_dates": proj_dates,
        "proj_values": proj_values,
    }


# ---------------------------------------------------------------------------
# 4. GEMINI CALL WRAPPER  — retry/backoff for 503 UNAVAILABLE spikes
# ---------------------------------------------------------------------------

def call_gemini(prompt, system_instruction, model=MODEL_PRIMARY, max_retries=3):
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.4,
                ),
            )
            return resp.text
        except Exception as e:
            last_err = e
            msg = str(e)
            if "503" in msg or "UNAVAILABLE" in msg or "overloaded" in msg.lower():
                wait = (2 ** attempt) + random.random()
                time.sleep(wait)
                continue
            raise

    # Final fallback: try the lighter flash model once before giving up
    try:
        resp = client.models.generate_content(
            model=MODEL_FALLBACK,
            contents=prompt,
            config=types.GenerateContentConfig(system_instruction=system_instruction),
        )
        return resp.text + "\n\n*(⚠️ Generated using fallback gemini-2.5-flash after repeated 503 errors on gemini-2.5-pro)*"
    except Exception as e2:
        raise RuntimeError(f"Both primary and fallback models failed. Last error: {e2}") from last_err


# ---------------------------------------------------------------------------
# 5. MULTI-AGENT PIPELINE
# ---------------------------------------------------------------------------

def agent1_spatial_growth_parser(region_data, metrics):
    cfg = region_data["cfg"]
    evidence = (
        f"Region: {cfg['name']} ({cfg['country']}). Crop: {cfg['crop']} on {cfg['hectares']} ha.\n"
        f"Expected height today: {region_data['expected_height'][-1]:.1f} cm | "
        f"Actual height: {region_data['actual_height'][-1]:.1f} cm "
        f"(deficit: {metrics['height_deficit_pct']:.1f}%).\n"
        f"Latest NDVI: {region_data['ndvi'][-1]:.2f}.\n"
        f"30-day soil moisture trend (%): {[round(float(v),1) for v in region_data['soil_moisture'][-30:]]}\n"
        f"Detected water bodies: {', '.join(cfg['water_bodies'])}."
    )
    system_instruction = (
        "You are a remote-sensing data ingestion agent. Summarize the field's growth "
        "trajectory deviation and soil moisture trend in 2-3 factual sentences for a "
        "climatologist. Do not invent numbers beyond what is given."
    )
    return call_gemini(evidence, system_instruction)


def agent2_climate_hydrologist(region_data, metrics, agent1_summary):
    cfg = region_data["cfg"]
    dtc_text = (
        f"{metrics['days_to_critical']:.0f} days" if metrics["days_to_critical"] is not None
        else "no near-term crossing projected at current trend"
    )
    evidence = (
        f"Field summary from ingestion agent: {agent1_summary}\n\n"
        f"Calculated figures (treat as ground truth, do not recompute):\n"
        f"- Statistically projected days until soil moisture hits the critical "
        f"{CRITICAL_SOIL_MOISTURE:.0f}% threshold: {dtc_text}.\n"
        f"- 12-week forecast rainfall deficit vs seasonal baseline: {metrics['rainfall_deficit_pct']:.1f}%.\n"
        f"- Forecast next-12-week avg temperature: {np.mean(region_data['forecast_temp']):.1f}°C.\n"
    )
    system_instruction = (
        "You are an agricultural hydrologist/climatologist. Using ONLY the provided "
        "calculated figures, write a short drought-onset forecast: state the approximate "
        "calendar timing of critical water stress and your confidence level. Do not invent "
        "your own numeric projections — reference the ones given."
    )
    return call_gemini(evidence, system_instruction)


def agent3_food_security_analyst(all_reports):
    bundle = "\n\n".join(
        f"### {r['cfg']['name']} ({r['cfg']['country']}) — {r['metrics']['risk_category']} risk\n"
        f"Crop: {r['cfg']['crop']} | Hectares: {r['cfg']['hectares']} | "
        f"Est. yield loss: {r['metrics']['yield_loss_pct']:.1f}% "
        f"(~{r['metrics']['tonnage_loss']:.0f} tonnes)\n"
        f"Hydrologist forecast: {r['agent2']}"
        for r in all_reports
    )
    total_tonnage = sum(r["metrics"]["tonnage_loss"] for r in all_reports)
    evidence = (
        f"Multi-region satellite drought forecasts below. Aggregate estimated tonnage at risk "
        f"across all regions: ~{total_tonnage:.0f} tonnes.\n\n{bundle}"
    )
    system_instruction = (
        "You are a national food-security risk analyst synthesizing multi-region satellite "
        "drought forecasts into an early-warning report for government stockpile planners. "
        "Rank regions by urgency, state the aggregate tonnage at risk, estimate the month(s) "
        "in which shortages could materialize, and give one overall national risk rating "
        "(LOW/MODERATE/HIGH/CRITICAL)."
    )
    return call_gemini(evidence, system_instruction), total_tonnage


def agent4_policy_agronomist(agent3_report, all_reports):
    water_bodies_bundle = "\n".join(
        f"- {r['cfg']['name']}: {', '.join(r['cfg']['water_bodies'])}" for r in all_reports
    )
    evidence = (
        f"National food security analyst report:\n{agent3_report}\n\n"
        f"Available regional water infrastructure:\n{water_bodies_bundle}"
    )
    system_instruction = (
        "You are a senior agronomist and food-security policy advisor. Produce a structured "
        "markdown action plan with three headed sections: "
        "1) Immediate irrigation triage (reference the specific water bodies per region), "
        "2) Medium-term conservation / storage / rationing recommendations, "
        "3) Longer-term planting and policy adjustments. Be concise and practical."
    )
    return call_gemini(evidence, system_instruction)


# ---------------------------------------------------------------------------
# 6. SESSION STATE INIT
# ---------------------------------------------------------------------------
if "seeds" not in st.session_state:
    st.session_state.seeds = {cfg["id"]: hash(cfg["id"]) % 10_000 for cfg in REGIONS_CONFIG}
if "pipeline_results" not in st.session_state:
    st.session_state.pipeline_results = None

# ---------------------------------------------------------------------------
# 7. SIDEBAR
# ---------------------------------------------------------------------------
st.sidebar.title("🛰️ Mission Control")
st.sidebar.caption(
    "Telemetry is simulated to mirror Google's Agricultural Landscape Understanding (ALU) "
    "and Agricultural Monitoring & Event Detection (AMED) schemas, plus a mock climate feed."
)
selected_ids = st.sidebar.multiselect(
    "Regions to monitor",
    options=[c["id"] for c in REGIONS_CONFIG],
    default=[c["id"] for c in REGIONS_CONFIG],
    format_func=lambda i: next(c["name"] for c in REGIONS_CONFIG if c["id"] == i),
)
if st.sidebar.button("🔄 Resimulate Satellite Pass"):
    st.session_state.seeds = {cfg["id"]: random.randint(0, 999_999) for cfg in REGIONS_CONFIG}
    st.session_state.pipeline_results = None

st.sidebar.markdown("---")
st.sidebar.markdown(
    "**Pipeline:** Spatial Parser → Hydrologist → Food Security Analyst → Policy Agronomist\n\n"
    f"**Models:** `{MODEL_PRIMARY}` (fallback: `{MODEL_FALLBACK}`)"
)

# ---------------------------------------------------------------------------
# 8. MAIN PAGE
# ---------------------------------------------------------------------------
st.title("🌍 Orbital Agronomist")
st.subheader("National Food Security Early Warning System")
st.caption(
    "Fuses simulated satellite crop-growth telemetry with weather forecasts to predict "
    "drought stress and potential food shortages months in advance."
)

all_regions = load_all_regions(st.session_state.seeds)
analysis = {rid: analyze_region(all_regions[rid]) for rid in all_regions}

if not selected_ids:
    st.info("Select at least one region from the sidebar to begin.")
    st.stop()

# --- National overview strip -------------------------------------------------
sel_analysis = {rid: analysis[rid] for rid in selected_ids}
total_hectares_at_risk = sum(
    all_regions[rid]["cfg"]["hectares"] for rid in selected_ids
    if sel_analysis[rid]["risk_category"] in ("HIGH", "CRITICAL")
)
total_tonnage_at_risk = sum(sel_analysis[rid]["tonnage_loss"] for rid in selected_ids)
worst_region_id = max(selected_ids, key=lambda rid: sel_analysis[rid]["risk_score"])

c1, c2, c3, c4 = st.columns(4)
c1.metric("Hectares at High/Critical Risk", f"{total_hectares_at_risk:,}")
c2.metric("Est. Tonnage at Risk", f"{total_tonnage_at_risk:,.0f} t")
c3.metric(
    "Most Urgent Region",
    all_regions[worst_region_id]["cfg"]["name"],
    f"{sel_analysis[worst_region_id]['risk_category']}",
)
dtc = sel_analysis[worst_region_id]["days_to_critical"]
c4.metric(
    "Fastest Projected Critical Onset",
    f"{dtc:.0f} days" if dtc is not None else "Stable",
)

st.markdown("---")

# --- Per-region tabs -----------------------------------------------------
tabs = st.tabs([all_regions[rid]["cfg"]["name"] for rid in selected_ids])

for rid, tab in zip(selected_ids, tabs):
    rd = all_regions[rid]
    m = analysis[rid]
    cfg = rd["cfg"]

    with tab:
        colA, colB = st.columns([2, 1])
        with colA:
            st.markdown(
                f"**Crop:** {cfg['crop']}  |  **Hectares:** {cfg['hectares']}  |  "
                f"**Water sources:** {', '.join(cfg['water_bodies'])}"
            )
        with colB:
            st.markdown(f"### {m['risk_emoji']} {m['risk_category']} RISK")
            st.progress(min(int(m["risk_score"]), 100))

        m1, m2, m3 = st.columns(3)
        m1.metric("Height Deficit vs Expected", f"{m['height_deficit_pct']:.1f}%")
        m2.metric("12-wk Rainfall Deficit", f"{m['rainfall_deficit_pct']:.1f}%")
        m3.metric("Est. Yield Loss", f"{m['yield_loss_pct']:.1f}%  (~{m['tonnage_loss']:.0f} t)")

        st.markdown("##### 🌱 Crop Height: Actual vs Expected (cm)")
        growth_df = pd.DataFrame({
            "Expected": rd["expected_height"],
            "Actual": rd["actual_height"],
        }, index=rd["dates_hist"])
        st.line_chart(growth_df)

        st.markdown("##### 🛰️ NDVI Vegetation Index (last 90 days)")
        ndvi_df = pd.DataFrame({"NDVI": rd["ndvi"]}, index=rd["dates_hist"])
        st.area_chart(ndvi_df)

        st.markdown("##### 💧 Soil Moisture (%) — history + projected trend to critical threshold")
        moisture_df = pd.DataFrame({"Soil Moisture (actual)": rd["soil_moisture"]}, index=rd["dates_hist"])
        if m["proj_dates"]:
            proj_series = pd.Series(m["proj_values"], index=m["proj_dates"], name="Projected trend")
            moisture_df = moisture_df.join(proj_series, how="outer")
        moisture_df["Critical threshold"] = CRITICAL_SOIL_MOISTURE
        st.line_chart(moisture_df)

        st.markdown("##### 🌧️ Weekly Rainfall (mm) — history + forecast")
        rain_hist_df = pd.DataFrame({"Rainfall": rd["hist_rainfall"]}, index=rd["week_dates_hist"])
        rain_fcst_df = pd.DataFrame({"Rainfall": rd["forecast_rainfall"]}, index=rd["week_dates_fcst"])
        rain_df = pd.concat([
            rain_hist_df.rename(columns={"Rainfall": "Historical"}),
            rain_fcst_df.rename(columns={"Rainfall": "Forecast"}),
        ])
        st.bar_chart(rain_df)

        with st.expander("🔍 Raw simulated satellite / climate JSON (ALU + AMED + climate feed)"):
            st.json(rd["raw_json"])

st.markdown("---")

# ---------------------------------------------------------------------------
# 9. MULTI-AGENT PIPELINE TRIGGER
# ---------------------------------------------------------------------------
st.header("🧠 Multi-Agent Food Security Forecast")
st.caption(
    "Runs Spatial Parser → Hydrologist for each selected region, then a Food Security "
    "Analyst and Policy Agronomist synthesize a national early-warning report."
)

if st.button("🛰️ Run Multi-Agent Food Security Forecast", type="primary"):
    try:
        progress = st.progress(0, text="Starting pipeline...")
        total_steps = len(selected_ids) * 2 + 2
        step = 0
        region_reports = []

        for rid in selected_ids:
            rd = all_regions[rid]
            m = analysis[rid]
            name = rd["cfg"]["name"]

            step += 1
            progress.progress(step / total_steps, text=f"Agent 1 (Spatial Parser) — {name}")
            a1 = agent1_spatial_growth_parser(rd, m)

            step += 1
            progress.progress(step / total_steps, text=f"Agent 2 (Hydrologist) — {name}")
            a2 = agent2_climate_hydrologist(rd, m, a1)

            region_reports.append({"cfg": rd["cfg"], "metrics": m, "agent1": a1, "agent2": a2})

        step += 1
        progress.progress(step / total_steps, text="Agent 3 (Food Security Analyst) — national synthesis")
        a3_report, total_tonnage = agent3_food_security_analyst(region_reports)

        step += 1
        progress.progress(step / total_steps, text="Agent 4 (Policy Agronomist) — mitigation plan")
        a4_report = agent4_policy_agronomist(a3_report, region_reports)

        progress.progress(1.0, text="Done.")
        st.session_state.pipeline_results = {
            "region_reports": region_reports,
            "a3_report": a3_report,
            "a4_report": a4_report,
            "total_tonnage": total_tonnage,
        }

    except Exception as e:
        st.error(f"⚠️ Pipeline error (possible server high-demand / 503): {e}")

# ---------------------------------------------------------------------------
# 10. RESULTS DISPLAY
# ---------------------------------------------------------------------------
results = st.session_state.pipeline_results
if results:
    st.subheader("📡 Per-Region Agent Findings")
    for r in results["region_reports"]:
        with st.expander(f"{r['metrics']['risk_emoji']} {r['cfg']['name']} — {r['metrics']['risk_category']} risk"):
            st.markdown(f"**Agent 1 (Spatial Parser):** {r['agent1']}")
            st.markdown(f"**Agent 2 (Hydrologist):** {r['agent2']}")

    st.subheader("🌾 National Food Security Report (Agent 3)")
    st.warning(results["a3_report"])

    st.subheader("🛡️ Mitigation & Conservation Plan (Agent 4)")
    st.success(results["a4_report"])

    report_md = (
        f"# Orbital Agronomist — Food Security Early Warning Report\n"
        f"Generated: {TODAY.strftime('%Y-%m-%d')}\n\n"
        f"**Total estimated tonnage at risk:** {results['total_tonnage']:.0f} t\n\n"
        f"## National Food Security Analysis\n{results['a3_report']}\n\n"
        f"## Mitigation & Conservation Plan\n{results['a4_report']}\n\n"
        f"## Per-Region Detail\n" + "\n\n".join(
            f"### {r['cfg']['name']} ({r['metrics']['risk_category']})\n"
            f"- Agent 1: {r['agent1']}\n- Agent 2: {r['agent2']}"
            for r in results["region_reports"]
        )
    )
    st.download_button(
        "⬇️ Download Full Report (Markdown)",
        data=report_md,
        file_name="orbital_agronomist_food_security_report.md",
        mime="text/markdown",
    )
