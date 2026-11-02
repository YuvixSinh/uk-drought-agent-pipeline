"""
Automated Verification Suite (Stages 1–5) — Orbital Agronomist (v2)
Run with: py -m unittest discover -s tests -v
"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from agents import (
    FALLBACK_MODEL,
    PRIMARY_MODEL,
    _assert_allowed_model,
    build_deterministic_a1,
    build_deterministic_a2,
    build_deterministic_a3,
)
from crop_rules import UK_CROP_RULE_TABLE, match_uk_crops
from globe_component.uk_land import validate_uk_coordinate
from indicators import compute_drought_indicators
from schemas import Agent1Output, Agent2Output, Agent3Output
from seasonal import fetch_seasonal_ensemble
from ui.screens.outlook import _generate_dossier_text
from weather import compute_10y_window_stats, fetch_10y_baseline, fetch_forecast_and_recent

ROOT_DIR = Path(__file__).resolve().parent.parent


class TestOrbitalAgronomistPipeline(unittest.TestCase):
    """End-to-end unit and integration tests for Orbital Agronomist (v2)."""

    def test_01_uk_land_and_exclusion_boundaries(self) -> None:
        """Verify UK land, islands, and strict exclusion of Dublin, Isle of Man, Guernsey, and North Sea."""
        # Valid UK land points
        for name, lat, lon in [
            ("Cambridge", 52.2053, 0.1218),
            ("Edinburgh", 55.9533, -3.1883),
            ("Belfast", 54.5973, -5.9301),
            ("Cardiff", 51.4816, -3.1791),
            ("Isle of Wight", 50.6938, -1.3047),
            ("Anglesey", 53.2556, -4.3624),
        ]:
            res = validate_uk_coordinate(lat, lon)
            self.assertIn(res["status"], ("uk_land", "near_coast"), f"{name} should be valid UK land")

        # Excluded non-UK points
        for name, lat, lon in [
            ("Dublin (RoI)", 53.3498, -6.2603),
            ("Isle of Man", 54.1523, -4.4861),
            ("Guernsey", 49.4582, -2.5368),
            ("North Sea", 54.5000, 2.5000),
        ]:
            res = validate_uk_coordinate(lat, lon)
            self.assertIn(res["status"], ("non_uk", "sea"), f"{name} status must be non_uk or sea")

    def test_02_model_policy_guards(self) -> None:
        """Verify Gemini 1.5, 2.5, and Argon 4 are strictly blocked and active models are permitted."""
        _assert_allowed_model(PRIMARY_MODEL)
        _assert_allowed_model(FALLBACK_MODEL)
        self.assertNotEqual(PRIMARY_MODEL, FALLBACK_MODEL)

        for forbidden in ["gemini-1.5-pro", "gemini-1.5-flash", "gemini-2.5-flash", "gemini-2.5-pro", "argon-4"]:
            with self.assertRaises(ValueError):
                _assert_allowed_model(forbidden)

    def test_03_weather_indicators_and_what_if_stress(self) -> None:
        """Verify Open-Meteo data structure, drought indicators, and What-If stress perturbation."""
        fc = fetch_forecast_and_recent(52.2053, 0.1218, "test_run")
        base_raw = fetch_10y_baseline(52.2053, 0.1218, "test_run")
        base_stats = compute_10y_window_stats(base_raw)
        seas = fetch_seasonal_ensemble(52.2053, 0.1218, "test_run")

        ind_normal = compute_drought_indicators(fc, base_stats, seas, what_if=False)
        ind_stress = compute_drought_indicators(fc, base_stats, seas, what_if=True)

        self.assertIn(ind_normal["chip_current"], ("LOW", "WATCH", "ELEVATED", "INCONCLUSIVE"))
        self.assertIn(ind_normal["chip_15d"], ("LOW", "WATCH", "ELEVATED", "INCONCLUSIVE"))
        self.assertIn(ind_normal["chip_13m"], ("LOW", "WATCH", "ELEVATED", "INCONCLUSIVE", "UNAVAILABLE"))

        # Under What-If stress (-35% rain, +15% ET0, -20% soil moisture), soil moisture is lower
        self.assertLess(ind_stress["sm_0_7_now"], ind_normal["sm_0_7_now"])
        self.assertLess(ind_stress["rain_15d_mm"], ind_normal["rain_15d_mm"])
        self.assertGreater(ind_stress["et0_15d_mm"], ind_normal["et0_15d_mm"])

    def test_04_uk_crop_rules_and_dossier(self) -> None:
        """Verify UK crop rule table matching, fallback agent schemas, and .txt dossier generation."""
        self.assertGreaterEqual(len(UK_CROP_RULE_TABLE), 10)
        fc = fetch_forecast_and_recent(52.2053, 0.1218, "test_run")
        base_stats = compute_10y_window_stats(fetch_10y_baseline(52.2053, 0.1218, "test_run"))
        seas = fetch_seasonal_ensemble(52.2053, 0.1218, "test_run")
        ind = compute_drought_indicators(fc, base_stats, seas, what_if=False)

        selection = {
            "lat": 52.2053,
            "lon": 0.1218,
            "grid_cell": fc.get("grid_cell", "52.21°N, 0.11°E"),
            "admin_area": "England",
            "country": "United Kingdom",
            "status": "uk_land",
            "land_status": "UK land · England",
        }
        crop_eval = match_uk_crops(
            indicators=ind,
            selection=selection,
            run_id="test_run",
        )
        self.assertEqual(len(crop_eval["candidates_ui"]), 3)
        self.assertTrue(crop_eval["q3_answer_line"])

        # Validate deterministic fallback schemas
        a1 = build_deterministic_a1(ind, selection)
        a2 = build_deterministic_a2(ind, a1)
        a3 = build_deterministic_a3(ind, crop_eval, selection, a2)
        self.assertIsInstance(a1, Agent1Output)
        self.assertIsInstance(a2, Agent2Output)
        self.assertIsInstance(a3, Agent3Output)

        # Validate dossier generation
        agents_res = {
            "a1": {"output": a1, "model_id": PRIMARY_MODEL, "source_state": "LIVE", "product_kind": "AI-GENERATED"},
            "a2": {"output": a2, "model_id": PRIMARY_MODEL, "source_state": "LIVE", "product_kind": "AI-GENERATED"},
            "a3": {"output": a3, "model_id": PRIMARY_MODEL, "source_state": "LIVE", "product_kind": "AI-GENERATED"},
        }
        dossier = _generate_dossier_text(
            sel=selection,
            run_id="test_run",
            s3_state="complete",
            what_if=False,
            ind=ind,
            crops_res=crop_eval,
            agents_res=agents_res,
        )
        self.assertIn("ORBITAL AGRONOMIST", dossier)
        self.assertIn("1. Q1 — HOW DRY IS IT NOW?", dossier)
        self.assertIn("2. Q2 — WHAT DO THE NEXT 7-15 DAYS AND 1-3 MONTHS SUGGEST?", dossier)
        self.assertIn("3. Q3 — WHICH CROPS ARE PLAUSIBLE, AND WHEN SHOULD PLANTING BE CONSIDERED?", dossier)

    def test_05_syntax_check_all_project_files(self) -> None:
        """Ensure every Python module in the project parses cleanly."""
        for py_file in ROOT_DIR.rglob("*.py"):
            if ".venv" in py_file.parts:
                continue
            source = py_file.read_text(encoding="utf-8")
            ast.parse(source, filename=str(py_file))


if __name__ == "__main__":
    unittest.main()
