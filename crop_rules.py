"""
UK Crop & Planting Rule Table (Stage 3 & Section 3/6/8) — Orbital Agronomist (v2)
Implements the deterministic UK agronomy heuristic rule table (~12 UK crops, forages,
and cover crops) filtered by:
- UK region (England, Scotland, Wales, Northern Ireland)
- Calendar month (Europe/London)
- Modelled 0-7 cm soil temperature (deg C)
- Current and 7-15d drought risk (LOW, WATCH, ELEVATED)
- Root-zone (7-28 cm) and deep (28-100 cm) soil moisture regime

Honesty & Provenance Rules (Section 6):
- Every crop candidate is explicitly framed as a weather-based regional candidate.
- Parcel suitability (land cover, soil texture, drainage, pH, slope, abstraction) is NEVER
  asserted and always listed under ground verification checks.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from events import append_feed_event
from schemas import CropCandidate, ProtectPrepareCard

LONDON_TZ = ZoneInfo("Europe/London")

# ---------------------------------------------------------------------------
# 12-Entry UK Agronomy Rule Table (Heuristic · Open-Meteo Weather-Filtered)
# ---------------------------------------------------------------------------
UK_CROP_RULE_TABLE: list[dict[str, Any]] = [
    {
        "id": "winter_wheat",
        "name": "Winter Wheat (hardy cultivars)",
        "category": "now_sown",
        "icon_kind": "wheat",
        "ui_icon": "grain",
        "months": [9, 10, 11],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 5.5,
        "window_label": "Sep–Nov",
        "drought_tolerance": "MODERATE",
        "why_template": "Low late-autumn ET₀ demand and vernalisation requirement align with UK autumn drilling regimes.",
        "watch_normal": "Ensure firm, consolidated seedbed at 3–5 cm depth to promote crown-root establishment before frosts.",
        "watch_dry": "Dry cloddy seedbeds reduce seed-to-soil contact and pre-emergence residual herbicide efficacy.",
        "verify": "Verify on ground: seedbed moisture at 3–5 cm depth, slug pressure, field drainage & pH (6.0–7.5).",
    },
    {
        "id": "winter_field_beans",
        "name": "Winter Field Beans (Vicia faba)",
        "category": "now_sown",
        "icon_kind": "beans",
        "ui_icon": "legume",
        "months": [10, 11],
        "regions": ["England", "Wales", "Scotland", "Northern Ireland"],
        "min_soil_temp_c": 4.5,
        "window_label": "Oct–Nov",
        "drought_tolerance": "HIGH_DEEP_ROOT",
        "why_template": "Deep taproot accesses 28–100 cm subsoil moisture ({sm_deep:.2f} m³/m³) and fixes atmospheric nitrogen.",
        "watch_normal": "Drill at 7–10 cm depth into uncompacted moisture to protect hypocotyl from frost heave and bird damage.",
        "watch_dry": "Avoid compacted headlands; deep drilling (7–10 cm) into subsoil moisture is essential under dry topsoil.",
        "verify": "Verify on ground: absence of plough pan, P/K indices, 5+ year legume rotation gap.",
    },
    {
        "id": "rye_vetch_cover",
        "name": "Overwintered Rye + Vetch Cover Crop",
        "category": "conditional_forage",
        "icon_kind": "cover",
        "ui_icon": "forage",
        "months": [8, 9, 10, 11],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 4.0,
        "window_label": "Aug–Nov",
        "drought_tolerance": "HIGH",
        "why_template": "Cereal rye germinates down to 4 °C, protecting bare topsoil from winter runoff and improving infiltration.",
        "watch_normal": "Vetch component slows in late autumn; increase rye seed rate by 15% for late-October / November sowings.",
        "watch_dry": "Plan early spring termination so cover crop transpiration does not deplete spring seedbed moisture.",
        "verify": "Verify on ground: surface residue clearance, machinery trafficability, spring destruction window.",
    },
    {
        "id": "winter_barley",
        "name": "Winter Barley (2-row / 6-row)",
        "category": "now_sown",
        "icon_kind": "barley",
        "ui_icon": "grain",
        "months": [9, 10],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 6.5,
        "window_label": "Sep–Oct",
        "drought_tolerance": "MODERATE",
        "why_template": "Earlier spring stem extension and harvest escape peak mid-summer soil moisture deficits.",
        "watch_normal": "Intolerant of waterlogging and low pH (< 6.0); BYDV aphid vector monitoring required in mild autumns.",
        "watch_dry": "Late October drilling in dry topsoil slows tillering before winter dormancy.",
        "verify": "Verify on ground: soil pH >= 6.2, absence of waterlogging, BYDV risk & manganese status.",
    },
    {
        "id": "winter_oats",
        "name": "Winter Oats (husking & naked)",
        "category": "now_sown",
        "icon_kind": "oats",
        "ui_icon": "grain",
        "months": [9, 10, 11],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 5.5,
        "window_label": "Sep–Early Nov",
        "drought_tolerance": "MODERATE",
        "why_template": "Extensive fibrous root system scavenges nutrients efficiently and tolerates slightly lower pH than barley.",
        "watch_normal": "Establish before severe frosts in northern / upland grids to avoid winter kill.",
        "watch_dry": "Needs consistent 0–7 cm moisture for even panicle initiation and establishment.",
        "verify": "Verify on ground: elevation/frost exposure, cereal cyst nematode history, lodging risk.",
    },
    {
        "id": "winter_triticale",
        "name": "Winter Triticale (grain / wholecrop)",
        "category": "conditional_forage",
        "icon_kind": "wheat",
        "ui_icon": "grain",
        "months": [9, 10, 11],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 4.5,
        "window_label": "Sep–Nov",
        "drought_tolerance": "HIGH",
        "why_template": "Aggressive rye-derived root system tolerates drought-prone lighter soils and late autumn drilling.",
        "watch_normal": "High straw biomass requires growth regulator planning on fertile sites.",
        "watch_dry": "Roll lightly after drilling if topsoil (0–7 cm) is below 0.22 m³/m³ to preserve moisture.",
        "verify": "Verify on ground: end-market or livestock wholecrop clamp capacity, soil texture, ergot risk.",
    },
    {
        "id": "spring_barley",
        "name": "Spring Malting / Feed Barley",
        "category": "spring_sowing",
        "icon_kind": "barley",
        "ui_icon": "grain",
        "months": [2, 3, 4],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 5.0,
        "window_label": "Feb–Apr (Plan Now)",
        "drought_tolerance": "MODERATE",
        "why_template": "Lower overwinter disease carry-over and strong fit where autumn seedbeds are too dry or black-grass burdened.",
        "watch_normal": "Requires friable overwintered tilth or cover-crop conditioned topsoil for rapid spring rooting.",
        "watch_dry": "Spring drought during tillering (Apr–May) sharply penalises ear number if root depth is restricted.",
        "verify": "Verify on ground: overwintered soil structure, malting N specification, spring trafficability.",
    },
    {
        "id": "spring_oats",
        "name": "Spring Oats",
        "category": "spring_sowing",
        "icon_kind": "oats",
        "ui_icon": "grain",
        "months": [2, 3, 4],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 5.5,
        "window_label": "Feb–Apr (Plan Now)",
        "drought_tolerance": "MODERATE",
        "why_template": "Valuable spring break crop in cool/moist northern & western UK regimes with low input demand.",
        "watch_normal": "Drill as early as soil friability permits in spring to maximise rooting before May dry spells.",
        "watch_dry": "Sensitive to late-spring moisture deficits during panicle emergence.",
        "verify": "Verify on ground: spring seedbed friability, rotation position, local oat mill contract specs.",
    },
    {
        "id": "spring_field_beans",
        "name": "Spring Field Beans / Combining Peas",
        "category": "spring_sowing",
        "icon_kind": "beans",
        "ui_icon": "legume",
        "months": [2, 3, 4],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 5.0,
        "window_label": "Feb–Apr (Plan Now)",
        "drought_tolerance": "MODERATE",
        "why_template": "Nitrogen-fixing spring pulse option when autumn establishment windows close.",
        "watch_normal": "Early spring drilling into uncompacted soil is critical so flowering precedes peak summer ET₀.",
        "watch_dry": "Pod set is sensitive to June moisture stress if subsoil (28–100 cm) is not recharged over winter.",
        "verify": "Verify on ground: winter subsoil recharge, bruchid/weevil history, P & K status.",
    },
    {
        "id": "multispecies_herbal_ley",
        "name": "Deep-Rooting Multispecies Herbal Ley",
        "category": "conditional_forage",
        "icon_kind": "forage",
        "ui_icon": "forage",
        "months": [4, 5, 8, 9],
        "regions": ["England", "Scotland", "Wales", "Northern Ireland"],
        "min_soil_temp_c": 7.5,
        "window_label": "Aug–Sep / Apr–May",
        "drought_tolerance": "HIGH",
        "why_template": "Chicory, plantain, and cocksfoot root below 50 cm, maintaining forage growth during summer dry spells.",
        "watch_normal": "Shallow broadcasting (1 cm) requires warm topsoil (>= 7.5 °C) and Cambridge rolling.",
        "watch_dry": "Outside peak autumn window in late Oct/Nov; plan for spring establishment once topsoil warms.",
        "verify": "Verify on ground: grazing/cutting infrastructure, perennial weed burden, SFI / stewardship rules.",
    },
    {
        "id": "winter_oilseed_rape",
        "name": "Winter Oilseed Rape (Brassica napus)",
        "category": "now_sown",
        "icon_kind": "cover",
        "ui_icon": "brassica",
        "months": [8, 9],
        "regions": ["England", "Scotland", "Wales"],
        "min_soil_temp_c": 9.0,
        "window_label": "Aug–Mid Sep",
        "drought_tolerance": "MODERATE",
        "why_template": "Early autumn brassica cash crop when August/September topsoil moisture is adequate.",
        "watch_normal": "Window closed by late October; late sowing risks cabbage stem flea beetle and poor winter survival.",
        "watch_dry": "Never drill into bone-dry August/September seedbeds where flea beetle grazing outpaces emergence.",
        "verify": "Verify on ground: CSFB pressure, clubroot history, brassica rotation interval.",
    },
    {
        "id": "sugar_beet_maize_spring",
        "name": "Forage Maize / Spring Root Crops",
        "category": "spring_sowing",
        "icon_kind": "forage",
        "ui_icon": "root",
        "months": [4, 5],
        "regions": ["England", "Wales"],
        "min_soil_temp_c": 8.5,
        "window_label": "Apr–May (Spring)",
        "drought_tolerance": "HIGH_C4",
        "why_template": "C4 photosynthesis in forage maize delivers high water-use efficiency during warm summer months.",
        "watch_normal": "Requires 8–10 °C soil temp for five consecutive days in April/May and harvest before autumn wet.",
        "watch_dry": "Maintain overwinter cover crop now to trap winter rainfall and prevent bare-soil erosion.",
        "verify": "Verify on ground: field slope / runoff risk, soil temperature at 10 cm, harvest trafficability.",
    },
]


def match_uk_crops(
    indicators: dict[str, Any],
    selection: dict[str, Any],
    run_id: str,
    month: int | None = None,
    emit_events: bool = True,
) -> dict[str, Any]:
    """
    Evaluate the UK Agronomy Rule Table against the selected UK region, current month,
    modelled 0-7 cm soil temperature, and drought indicators.
    Returns:
      - candidates_ui: list of 3 top candidate dicts for Screen 3 rendering
      - candidates_schema: list[CropCandidate] (Pydantic models)
      - protect_card: ProtectPrepareCard (Pydantic model)
      - protect_bullets: list[str]
      - q3_answer_line: deterministic plain-English answer line for Q3
    """
    if month is None:
        month = datetime.now(LONDON_TZ).month

    admin = selection.get("admin_area") or "England"
    if admin not in ("England", "Scotland", "Wales", "Northern Ireland"):
        # Infer from land_status if needed
        ls = selection.get("land_status", "England")
        for r in ("Scotland", "Wales", "Northern Ireland", "England"):
            if r.lower() in ls.lower():
                admin = r
                break
        else:
            admin = "England"

    what_if = bool(indicators.get("what_if", False))
    raw_cur = indicators.get("chip_current", "WATCH")
    current_risk = raw_cur.risk if hasattr(raw_cur, "risk") else str(raw_cur)
    raw_15d = indicators.get("chip_15d", "WATCH")
    short_risk = raw_15d.risk if hasattr(raw_15d, "risk") else str(raw_15d)

    def _val(key_primary: str, key_alt: str, default: float) -> float:
        v = indicators.get(key_primary, indicators.get(key_alt, default))
        if hasattr(v, "value"):
            return float(v.value if v.value is not None else default)
        return float(v if v is not None else default)

    sm_top = _val("sm_0_7_now", "sm_0_7_m3m3", 0.24)
    sm_root = _val("sm_7_28_now", "sm_7_28_m3m3", 0.26)
    sm_deep = _val("sm_28_100_now", "sm_28_100_m3m3", 0.29)
    soil_temp_c = _val("soil_temp_0_7_c", "soil_temp_0_7_c", 9.8)

    # Filter rules that match current month & region first, then fallback to spring planning options
    in_window = [
        r for r in UK_CROP_RULE_TABLE
        if month in r["months"] and admin in r["regions"]
    ]
    out_window = [
        r for r in UK_CROP_RULE_TABLE
        if month not in r["months"] and admin in r["regions"]
    ]

    # Sort in-window candidates by suitability for current soil temp & dryness
    def _score_rule(r: dict[str, Any]) -> tuple[int, float]:
        temp_ok = 1 if soil_temp_c >= r["min_soil_temp_c"] else 0
        drought_bonus = 1 if (current_risk in ("WATCH", "ELEVATED") and "HIGH" in r["drought_tolerance"]) else 0
        return (temp_ok + drought_bonus, -r["min_soil_temp_c"])

    in_window_sorted = sorted(in_window, key=_score_rule, reverse=True)
    selected_rules = (in_window_sorted + out_window)[:3]

    candidates_ui: list[dict[str, Any]] = []
    candidates_schema: list[CropCandidate] = []

    for r in selected_rules:
        is_month_open = month in r["months"]
        temp_ok = soil_temp_c >= r["min_soil_temp_c"]

        # Determine planting window status & fit tag
        if is_month_open and temp_ok:
            if current_risk == "ELEVATED" or what_if:
                if r["drought_tolerance"] in ("HIGH", "HIGH_DEEP_ROOT"):
                    tag = "Possible with watch-outs"
                    tag_color = "#F59E0B"
                    conf = "CONDITIONAL"
                    win_status = f"{r['window_label']} · Window OPEN (0–7 cm {soil_temp_c:.1f} °C >= {r['min_soil_temp_c']:.1f} °C; dry stress watch)"
                else:
                    tag = "Wait / monitor"
                    tag_color = "#F59E0B"
                    conf = "LOW"
                    win_status = f"{r['window_label']} · WAIT FOR MOISTURE (0–7 cm {sm_top:.2f} m³/m³)"
            elif current_risk == "WATCH":
                if r["id"] == "winter_field_beans":
                    tag = "Possible with watch-outs"
                    tag_color = "#F59E0B"
                    conf = "CONDITIONAL"
                else:
                    tag = "Good fit now"
                    tag_color = "#10B981"
                    conf = "MODERATE"
                win_status = f"{r['window_label']} · Window OPEN (0–7 cm {soil_temp_c:.1f} °C >= {r['min_soil_temp_c']:.1f} °C min)"
            else:
                tag = "Good fit now"
                tag_color = "#10B981"
                conf = "MODERATE"
                win_status = f"{r['window_label']} · Window OPEN (0–7 cm {soil_temp_c:.1f} °C >= {r['min_soil_temp_c']:.1f} °C min)"
        elif is_month_open and not temp_ok:
            tag = "Possible with watch-outs"
            tag_color = "#F59E0B"
            conf = "CONDITIONAL"
            win_status = f"{r['window_label']} · Cool topsoil ({soil_temp_c:.1f} °C vs {r['min_soil_temp_c']:.1f} °C ideal)"
        else:
            tag = "Next window (Spring)"
            tag_color = "#38BDF8"
            conf = "CONDITIONAL"
            win_status = f"{r['window_label']} · Window NEXT OPENS IN SPRING"

        why_text = r["why_template"].format(sm_deep=sm_deep, sm_root=sm_root, sm_top=sm_top)
        watch_text = r["watch_dry"] if (current_risk in ("WATCH", "ELEVATED") or what_if) else r["watch_normal"]

        candidates_ui.append({
            "name": r["name"],
            "icon": r["ui_icon"],
            "tag": tag,
            "tag_color": tag_color,
            "window": win_status,
            "why": why_text,
            "watch": watch_text,
            "verify": r["verify"],
        })

        candidates_schema.append(
            CropCandidate(
                name=r["name"],
                category=r["category"],
                icon_kind=r["icon_kind"],
                window=win_status,
                climate_fit=why_text,
                constraints=watch_text,
                uncertainty="Regional weather-based candidate only; parcel land cover, soil type, and drainage are unverified.",
                confidence=conf,
                evidence_to_verify=r["verify"],
                is_demo_assumption=what_if,
            )
        )

    # Protect & Prepare Card (Existing Crops & Grassland)
    if current_risk == "ELEVATED" or what_if:
        b1 = f"Consolidate loose seedbeds lightly after drilling to conserve capillary moisture (0–7 cm at {sm_top:.2f} m³/m³)."
        b2 = "Minimise deep tillage moisture loss; inspect on-farm winter water-storage / ditch capture infrastructure."
        p_card = ProtectPrepareCard(
            action_24_72h=b1,
            action_7d="Delay high-disturbance cultivations until 15-day rainfall recharges topsoil above 0.22 m³/m³.",
            action_1_3m=b2,
            qualification="Options to verify against local parcel conditions; not farm advice.",
        )
    elif current_risk == "WATCH":
        b1 = f"Consolidate seedbeds after drilling to preserve 0–7 cm moisture ({sm_top:.2f} m³/m³) and improve seed-to-soil contact."
        b2 = "Avoid high-axle-load passes on headlands and check winter water-storage / ditch capture capacity."
        p_card = ProtectPrepareCard(
            action_24_72h=b1,
            action_7d="Target drilling into uncompacted moisture ahead of forecast rainfall events.",
            action_1_3m=b2,
            qualification="Options to verify against local parcel conditions; not farm advice.",
        )
    else:
        b1 = f"Topsoil moisture ({sm_top:.2f} m³/m³) is adequate; prioritise field trafficability to avoid structural rutting."
        b2 = "Maintain clear field drains and headlands ahead of late-autumn / winter recharge."
        p_card = ProtectPrepareCard(
            action_24_72h=b1,
            action_7d="Time field operations around dry 48-hour windows to protect soil structure.",
            action_1_3m=b2,
            qualification="Options to verify against local parcel conditions; not farm advice.",
        )

    names_short = ", ".join(c["name"].split(" (")[0] for c in candidates_ui)
    month_name = datetime.now(LONDON_TZ).strftime("%B")
    q3_answer_line = (
        f"For {admin} in {month_name} (modelled 0–7 cm soil temp {soil_temp_c:.1f} °C), "
        f"{names_short} are plausible regional weather candidates — planting window is "
        + (
            "WAIT FOR MOISTURE / MONITOR under dry stress conditions."
            if (current_risk == "ELEVATED" or what_if)
            else "OPEN NOW with seedbed & parcel verification watch-outs."
        )
    )

    if emit_events:
        append_feed_event(
            run_id=run_id,
            event_type="INDICATOR",
            source="CROP-RULES",
            text=f"Matched {len(candidates_ui)} UK regional candidates for {admin} ({month_name}, soil 0–7 cm {soil_temp_c:.1f} °C): {names_short}",
        )

    return {
        "admin": admin,
        "month_name": month_name,
        "soil_temp_c": soil_temp_c,
        "candidates_ui": candidates_ui,
        "candidates_schema": candidates_schema,
        "protect_card": p_card,
        "protect_bullets": [b1, b2],
        "q3_answer_line": q3_answer_line,
        "total_rules_loaded": len(UK_CROP_RULE_TABLE),
    }
