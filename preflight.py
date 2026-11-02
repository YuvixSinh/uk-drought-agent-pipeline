"""
Stage 0 Preflight Verification Script — Orbital Agronomist (v2)
Verifies Python, Streamlit, and google-genai versions, lists visible Gemini models,
tests streaming + thinking_config on chosen primary and fallback models (non-1.5/2.5/Argon-4),
and verifies Open-Meteo forecast, 10-year archive, and seasonal endpoints for Cambridge and Belfast.
"""

import os
import sys
import time
import requests
import streamlit as st
from dotenv import load_dotenv
from google import genai
from google.genai import types

PRIMARY_MODEL = "gemini-3-flash-preview"
FALLBACK_MODEL = "gemini-3.1-flash-lite-preview"

POINTS = [
    ("Cambridge", 52.2053, 0.1218),
    ("Belfast", 54.5973, -5.9301),
]


def run_preflight() -> None:
    load_dotenv()
    print("=" * 72)
    print("ORBITAL AGRONOMIST v2 — STAGE 0 PREFLIGHT")
    print("=" * 72)
    print(f"Python version      : {sys.version.split()[0]} ({sys.version})")
    print(f"Streamlit version   : {st.__version__}")
    print(f"google-genai version: {genai.__version__}")

    api_key = os.getenv("GEMINI_API_KEY", "")
    print(f"GEMINI_API_KEY set  : {'YES' if bool(api_key) else 'NO'} (value hidden)")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not found in .env")

    client = genai.Client(
        api_key=api_key,
        http_options=types.HttpOptions(timeout=20000),
    )

    print("\n--- 1. Visible Gemini Models ---")
    all_models = [m.name for m in client.models.list() if "gemini" in m.name.lower()]
    for m in all_models:
        print(f"  - {m}")

    print("\n--- 2. Model Selection & Thinking Config Verification ---")
    print("Note: models/gemini-3.1-pro-preview returns HTTP 429 with Free Tier limit=0 on this key.")
    print("      Gemini 1.5, Gemini 2.5, and Argon 4 are excluded per Section 1.")
    print(f"Chosen Primary Model : {PRIMARY_MODEL}")
    print(f"Chosen Fallback Model: {FALLBACK_MODEL}")
    print("ThinkingConfig used  : ThinkingConfig(thinking_level=ThinkingLevel.LOW, include_thoughts=False)")

    for label, model_id in [("PRIMARY", PRIMARY_MODEL), ("FALLBACK", FALLBACK_MODEL), ("PRO-CHECK (expected 429)", "gemini-3.1-pro-preview")]:
        t0 = time.perf_counter()
        try:
            chunks = []
            for chunk in client.models.generate_content_stream(
                model=model_id,
                contents="Reply with the single word READY.",
                config=types.GenerateContentConfig(
                    thinking_config=types.ThinkingConfig(
                        thinking_level=types.ThinkingLevel.LOW,
                        include_thoughts=False,
                    ),
                    temperature=0.2,
                    max_output_tokens=512,
                ),
            ):
                if chunk.text:
                    chunks.append(chunk.text)
            dt_ms = (time.perf_counter() - t0) * 1000.0
            text_out = "".join(chunks).strip()
            print(f"  [{label}] {model_id}: OK in {dt_ms:.0f} ms | output={text_out!r}")
        except Exception as exc:
            dt_ms = (time.perf_counter() - t0) * 1000.0
            print(f"  [{label}] {model_id}: FAILED in {dt_ms:.0f} ms | {str(exc)[:160]}")

    print("\n--- 3. Open-Meteo Endpoints Verification ---")
    for name, lat, lon in POINTS:
        print(f"\nLocation: {name} (requested {lat}, {lon})")

        # A. Forecast endpoint (past 30 days + next 15 days, daily + hourly soil layers + ET0)
        t0 = time.perf_counter()
        r_fc = requests.get(
            "https://api.open-meteo.com/v1/forecast",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "precipitation_sum,et0_fao_evapotranspiration,temperature_2m_max,temperature_2m_min",
                "hourly": "soil_moisture_0_to_7cm,soil_moisture_7_to_28cm,soil_moisture_28_to_100cm,soil_temperature_0_to_7cm",
                "past_days": 30,
                "forecast_days": 15,
                "timezone": "Europe/London",
            },
            timeout=15,
        )
        fc_ms = (time.perf_counter() - t0) * 1000.0
        r_fc.raise_for_status()
        fc = r_fc.json()
        print(f"  [Forecast] HTTP {r_fc.status_code} ({fc_ms:.0f} ms) | grid=({fc.get('latitude'):.4f}, {fc.get('longitude'):.4f})")
        for sec in ("daily", "hourly"):
            units = fc.get(f"{sec}_units", {})
            block = fc.get(sec, {})
            for var, vals in block.items():
                if var == "time":
                    continue
                non_null = [v for v in vals if v is not None]
                print(
                    f"    - {sec}.{var}: {len(non_null)}/{len(vals)} non-null | "
                    f"unit='{units.get(var, '')}' | sample={non_null[-1] if non_null else None}"
                )

        # B1. Archive 10-year daily precipitation & ET0 baseline (2016-01-01 to 2025-12-31)
        t0 = time.perf_counter()
        r_ar10 = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": "2016-01-01",
                "end_date": "2025-12-31",
                "daily": "precipitation_sum,et0_fao_evapotranspiration",
                "timezone": "Europe/London",
            },
            timeout=15,
        )
        ar10_ms = (time.perf_counter() - t0) * 1000.0
        r_ar10.raise_for_status()
        ar10 = r_ar10.json()
        print(f"  [Archive 10-yr Daily] HTTP {r_ar10.status_code} ({ar10_ms:.0f} ms) | grid=({ar10.get('latitude'):.4f}, {ar10.get('longitude'):.4f})")
        u_ar10 = ar10.get("daily_units", {})
        for var, vals in ar10.get("daily", {}).items():
            if var == "time":
                continue
            non_null = [v for v in vals if v is not None]
            print(
                f"    - daily.{var}: {len(non_null)}/{len(vals)} non-null | "
                f"unit='{u_ar10.get(var, '')}' | sample={non_null[-1] if non_null else None}"
            )

        # B2. Archive soil moisture & temperature layers verification (30-day window in 2025)
        t0 = time.perf_counter()
        r_ar_soil = requests.get(
            "https://archive-api.open-meteo.com/v1/archive",
            params={
                "latitude": lat,
                "longitude": lon,
                "start_date": "2025-10-01",
                "end_date": "2025-10-31",
                "hourly": "soil_moisture_0_to_7cm,soil_moisture_28_to_100cm,soil_temperature_0_to_7cm",
                "timezone": "Europe/London",
            },
            timeout=15,
        )
        ar_soil_ms = (time.perf_counter() - t0) * 1000.0
        r_ar_soil.raise_for_status()
        ar_soil = r_ar_soil.json()
        print(f"  [Archive Hourly Soil] HTTP {r_ar_soil.status_code} ({ar_soil_ms:.0f} ms) | grid=({ar_soil.get('latitude'):.4f}, {ar_soil.get('longitude'):.4f})")
        u_ars = ar_soil.get("hourly_units", {})
        for var, vals in ar_soil.get("hourly", {}).items():
            if var == "time":
                continue
            non_null = [v for v in vals if v is not None]
            print(
                f"    - hourly.{var}: {len(non_null)}/{len(vals)} non-null | "
                f"unit='{u_ars.get(var, '')}' | sample={non_null[-1] if non_null else None}"
            )

        # C. Seasonal endpoint (1-3 month outlook + ensemble members)
        t0 = time.perf_counter()
        r_seas = requests.get(
            "https://seasonal-api.open-meteo.com/v1/seasonal",
            params={
                "latitude": lat,
                "longitude": lon,
                "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min",
                "timezone": "Europe/London",
            },
            timeout=15,
        )
        seas_ms = (time.perf_counter() - t0) * 1000.0
        r_seas.raise_for_status()
        seas = r_seas.json()
        u_seas = seas.get("daily_units", {})
        d_seas = seas.get("daily", {})
        member_keys = [k for k in d_seas.keys() if k.startswith("precipitation_sum_member")]
        print(
            f"  [Seasonal] HTTP {r_seas.status_code} ({seas_ms:.0f} ms) | "
            f"grid=({seas.get('latitude'):.4f}, {seas.get('longitude'):.4f}) | "
            f"precip_ensemble_members={len(member_keys)}"
        )
        for var in ("precipitation_sum", "precipitation_sum_member01", "temperature_2m_max", "temperature_2m_min"):
            vals = d_seas.get(var, [])
            non_null = [v for v in vals if v is not None]
            print(
                f"    - daily.{var}: {len(non_null)}/{len(vals)} non-null | "
                f"unit='{u_seas.get(var, '')}' | sample={non_null[0] if non_null else None}"
            )


if __name__ == "__main__":
    run_preflight()
