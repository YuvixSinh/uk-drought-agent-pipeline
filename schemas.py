"""
Contracts & Data Schemas (Section 10) — Orbital Agronomist (v2)
All metrics, horizon chips, events, selections, and agent structured outputs
are strongly typed with Pydantic v2. No single unqualified risk number exists.
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field

SourceState = Literal["LIVE", "CACHED", "SIMULATED", "FALLBACK", "DEMO FIXTURE", "UNAVAILABLE"]
ProductKind = Literal["MODELLED", "DERIVED", "SEASONAL ENSEMBLE", "SIMULATED", "AI-GENERATED", "HEURISTIC", "USER-ENTERED"]
RiskLevel = Literal["LOW", "WATCH", "ELEVATED", "INCONCLUSIVE", "UNAVAILABLE"]
PhaseName = Literal["pick", "analyse", "outlook"]
FeedEventType = Literal["SOURCE", "INDICATOR", "AGENT", "HANDOFF", "FALLBACK", "ERROR"]
AgentMode = Literal["GEMINI", "CACHED GEMINI", "DETERMINISTIC FALLBACK"]


class LocationSelection(BaseModel):
    run_id: str | None = None
    lat: float
    lon: float
    local_time: str
    source: str
    land_status: str
    status_code: str = "uk_land"
    unit: str | None = None
    context: str = ""
    grid_cell: str = ""
    valid: bool = True


class Metric(BaseModel):
    value: float | None = None
    unit: str
    source_state: SourceState
    product_kind: ProductKind
    source: str
    valid_at: str
    fetched_at: str
    note: str = ""
    cache_age_s: float | None = None
    grid_used: str = ""


class HorizonChip(BaseModel):
    horizon: Literal["NOW", "7–15 DAYS", "1–3 MONTHS"]
    risk: RiskLevel
    reason: str
    source_state: SourceState
    product_kind: ProductKind
    source: str
    valid_at: str
    fetched_at: str
    rule_summary: str = ""


class FeedEvent(BaseModel):
    run_id: str
    ts: str
    type: FeedEventType
    source: str
    text: str
    payload: dict[str, Any] | None = None


class AgentEvent(BaseModel):
    run_id: str
    agent: Literal["A1", "A2", "A3"]
    stage: Literal["Queued", "Running", "Done", "Fallback", "Error"]
    text: str
    payload: dict[str, Any] | None = None


class CropCandidate(BaseModel):
    name: str
    category: Literal["now_sown", "spring_sowing", "conditional_forage"] = "now_sown"
    icon_kind: Literal["wheat", "barley", "beans", "oats", "forage", "cover"] = "wheat"
    window: str
    climate_fit: str
    constraints: str
    uncertainty: str
    confidence: Literal["MODERATE", "CONDITIONAL", "LOW"] = "CONDITIONAL"
    evidence_to_verify: str = "Soil texture, drainage class, field elevation, and current parcel use."
    is_demo_assumption: bool = False


class ProtectPrepareCard(BaseModel):
    action_24_72h: str
    action_7d: str
    action_1_3m: str
    qualification: str = "Options to verify against local parcel conditions; not farm advice."


class Agent1Output(BaseModel):
    public_narrative: str = Field(description="Concise 100-140 word factual site evidence summary.")
    surface_moisture_state: str = Field(description="Short tag on 0-7 cm modelled moisture.")
    deep_moisture_state: str = Field(description="Short tag on 28-100 cm modelled moisture.")
    missing_facts_noted: list[str] = Field(default_factory=list)
    handoff_note: str = Field(description="One-sentence validated hand-off to A2.")


class Agent2Output(BaseModel):
    public_narrative: str = Field(description="Concise 100-140 word hydrometeorology outlook separating horizons.")
    evidence_for_concern: str = Field(description="Key evidence supporting dryness concern.")
    evidence_against_concern: str = Field(description="Key mitigating or uncertain evidence.")
    seasonal_signal_tag: str = Field(description="Short tag on 1-3 month seasonal signal or unavailable.")
    handoff_note: str = Field(description="One-sentence validated hand-off to A3.")


class Agent3Output(BaseModel):
    public_narrative: str = Field(description="Concise 100-140 word conditional crop candidate reasoning.")
    crop_tags: list[str] = Field(default_factory=list)
    parcel_qualification: str = Field(description="Explicit qualification on land/soil suitability.")
    protect_actions: ProtectPrepareCard


class Assessment(BaseModel):
    run_id: str
    selection: LocationSelection
    dryness_now: HorizonChip
    short_term_risk: HorizonChip
    medium_term_outlook: HorizonChip
    uncertainty: str
    crops: list[CropCandidate]
    follow_up: ProtectPrepareCard
    sources: dict[str, Any] = Field(default_factory=dict)


class PhaseState(BaseModel):
    phase: PhaseName = "pick"
    pending_selection: LocationSelection | None = None
    confirmed_selection: LocationSelection | None = None
    run_id: str | None = None
    camera_pov: dict[str, float] = Field(
        default_factory=lambda: {"lat": 54.5, "lng": -3.0, "altitude": 1.6}
    )
    results_history: list[dict[str, Any]] = Field(default_factory=list)
