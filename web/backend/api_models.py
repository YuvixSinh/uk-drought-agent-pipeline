"""
Pydantic v2 API Models — Orbital Agronomist (v5)
Defines the exact JSON contracts for /api/validate, /api/run, /api/run/{run_id}/result,
/api/run/{run_id}/scenario, and /api/demo/{name} (documented in web/API.md).
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

ProvenanceKind = Literal[
    "LIVE · MODELLED",
    "LIVE · SEASONAL ENSEMBLE",
    "LIVE · DERIVED",
    "CACHED · MODELLED",
    "CACHED · SEASONAL ENSEMBLE",
    "CACHED · DERIVED",
    "SIMULATED",
    "LIVE · AI-GENERATED",
    "FALLBACK · HEURISTIC",
    "UNAVAILABLE",
]

GlyphKind = Literal["LIVE", "CACHED", "SIMULATED", "FALLBACK", "AI-GENERATED"]
RiskWord = Literal["LOW", "WATCH", "ELEVATED", "INCONCLUSIVE", "UNAVAILABLE"]


class ValidateRequest(BaseModel):
    lat: float
    lon: float


class ValidateResponse(BaseModel):
    valid: bool
    nation: str | None
    grid_cell: str
    status: str
    label: str
    context: str
    reason: str | None = None
    lat: float
    lon: float


class RunStartRequest(BaseModel):
    lat: float
    lon: float
    force_model_fail: bool = False


class RunStartResponse(BaseModel):
    run_id: str
    status: str = "RUNNING"
    location: ValidateResponse


class ScenarioRequest(BaseModel):
    scenario: Literal["dry30", "none"] = "dry30"


class KpiItem(BaseModel):
    id: str
    label: str
    value: float | None
    display_value: str
    unit: str
    glyph: GlyphKind
    provenance: str
    source: str
    valid_time: str
    fetched_time: str
    cache_age_s: float | None = None
    tooltip: str


class BaselineYearBar(BaseModel):
    year: str
    rain_mm: float
    is_current: bool = False


class SoilLayerBar(BaseModel):
    depth_label: str
    moisture_m3m3: float | None
    baseline_m3m3: float | None = None
    glyph: GlyphKind = "LIVE"
    provenance: str = "LIVE · MODELLED"
    tooltip: str = ""


class DailySeriesPoint(BaseModel):
    date: str
    rain_mm: float
    et0_mm: float
    cum_net_mm: float
    baseline_cum_net_mm: float | None = None


class SeasonalSummary(BaseModel):
    available: bool
    median_pct: int | None = None
    p25_pct: int | None = None
    p75_pct: int | None = None
    iqr_label: str = ""
    status: str = "No clear signal"
    glyph: GlyphKind = "LIVE"
    provenance: str = "LIVE · SEASONAL ENSEMBLE"
    tooltip: str = ""


class CropConstraintIcon(BaseModel):
    kind: Literal["water", "temp", "drainage"]
    label: str
    tooltip: str


class CropTileModel(BaseModel):
    id: str
    name: str
    window_label: str
    start_month_idx: int = Field(description="0=Oct, 1=Nov, 2=Dec, 3=Jan, 4=Feb, 5=Mar, 6=Apr")
    end_month_idx: int = Field(description="0=Oct .. 6=Apr")
    confidence_dots: int = Field(ge=1, le=3)
    confidence_word: str
    why: str
    watch: str
    verify: str
    constraints: list[CropConstraintIcon] = Field(default_factory=list)
    glyph: GlyphKind = "FALLBACK"
    provenance: str = "FALLBACK · HEURISTIC"


class ProtectPipModel(BaseModel):
    horizon: str
    action: str


class Q1Payload(BaseModel):
    chip: RiskWord
    glyph: GlyphKind
    provenance: str
    tooltip: str
    headline: str
    baseline_headline: str | None = None
    kpis: list[KpiItem]
    baseline_years: list[BaselineYearBar]
    mean_30d_mm: float
    soil_layers: list[SoilLayerBar]
    series_past30: list[DailySeriesPoint]


class Q2Payload(BaseModel):
    chip_7_15: RiskWord
    glyph_7_15: GlyphKind
    tooltip_7_15: str
    headline_7_15: str
    chip_1_3m: RiskWord
    glyph_1_3m: GlyphKind
    tooltip_1_3m: str
    headline_1_3m: str
    headline: str
    kpis: list[KpiItem]
    net_balance_series: list[DailySeriesPoint]
    daily_rain_et0: list[DailySeriesPoint]
    seasonal: SeasonalSummary


class Q3Payload(BaseModel):
    headline: str
    kpis: list[KpiItem]
    crops: list[CropTileModel]
    protect_prepare: list[ProtectPipModel]
    verification_checklist: list[str]
    micro_line: str = "Regional candidates. Verify soil and drainage."


class AgentDetailModel(BaseModel):
    agent: Literal["meteorologist", "hydrologist", "agronomist"]
    title: str
    state: Literal["done", "fallback", "error"]
    model: str
    mode: str
    glyph: GlyphKind
    provenance: str
    text: str
    takeaway: str
    extra: dict[str, Any] = Field(default_factory=dict)


class SourceDiagnosticItem(BaseModel):
    id: str
    name: str
    state: Literal["done", "cached", "failed"]
    glyph: GlyphKind
    provenance: str
    latency_ms: int
    valid_time: str
    fetched_time: str
    cache_age_s: float | None = None
    grid_cell: str
    summary: str


class ResultPayload(BaseModel):
    run_id: str
    state: Literal["DONE", "PARTIAL"]
    is_demo: bool = False
    scenario_active: bool = False
    location: dict[str, Any]
    q1: Q1Payload
    q2: Q2Payload
    q3: Q3Payload
    agents: dict[str, AgentDetailModel]
    sources: list[SourceDiagnosticItem]
    provenance: dict[str, Any]
    assumptions: list[str]
    feed: list[dict[str, Any]]
    scenario: dict[str, Any] | None = None
