/**
 * Sliding Right-Hand Details Drawer — Orbital Agronomist (v5)
 * Keeps the main views clean ("show, don't write") while placing full
 * Evidence, Method, Sources, Assumptions, Agents (including live stream),
 * and Feed one tap away.
 */

import { state, subscribe, notify, getActiveQPayloads } from '../state.js';
import { renderGlyphSVG } from './glyphs.js';

const TABS = ['Evidence', 'Method', 'Sources', 'Assumptions', 'Agents', 'Feed'];

const UNKNOWN_PARAMETERS = [
  'Canopy height',
  'NDVI / NDRE satellite vegetation indices',
  'Canopy temperature',
  'True in-situ root-zone moisture',
  'Field capacity & permanent wilting point',
  'Irrigated area & on-farm water storage assets',
  'Parcel-scale crop yield',
];

export function initDrawer() {
  const drawerEl = document.getElementById('details-drawer');
  if (!drawerEl) return;

  const renderDrawer = () => {
    drawerEl.classList.toggle('open', Boolean(state.drawerOpen));
    const res = state.result;
    const { q1, q2, q3, isScenario } = getActiveQPayloads();

    const tabsHTML = TABS.map(
      (t) => `
        <button type="button" class="drawer-tab-btn interactive ${state.drawerTab === t ? 'active' : ''}" data-tab="${t}">
          ${t}
        </button>
      `
    ).join('');

    let bodyHTML = '';
    if (state.drawerTab === 'Evidence') {
      bodyHTML = renderEvidenceTab(res, q1, q2, q3, isScenario);
    } else if (state.drawerTab === 'Method') {
      bodyHTML = renderMethodTab(res, isScenario);
    } else if (state.drawerTab === 'Sources') {
      bodyHTML = renderSourcesTab(res);
    } else if (state.drawerTab === 'Assumptions') {
      bodyHTML = renderAssumptionsTab(res);
    } else if (state.drawerTab === 'Agents') {
      bodyHTML = renderAgentsTab(res);
    } else {
      bodyHTML = renderFeedTab(res);
    }

    drawerEl.innerHTML = `
      <div class="drawer-header">
        <div>
          <div class="micro-label">INSPECTION DRAWER · ONE TAP DETAIL</div>
          <div style="font-size:18px;font-weight:500;color:var(--ink);margin-top:2px;">
            ${res?.location?.label || 'UK Land'} · <span class="mono" style="color:var(--accent);">${res?.location?.grid_cell || ''}</span>
          </div>
        </div>
        <button type="button" id="drawer-close-btn" class="btn-glass interactive" aria-label="Close details drawer">✕ Close</button>
      </div>
      <div class="drawer-tabs">
        ${tabsHTML}
      </div>
      <div class="drawer-body">
        ${bodyHTML}
      </div>
    `;

    drawerEl.querySelector('#drawer-close-btn')?.addEventListener('click', () => {
      state.drawerOpen = false;
      notify('drawer');
    });

    drawerEl.querySelectorAll('.drawer-tab-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.drawerTab = btn.getAttribute('data-tab') || 'Evidence';
        state.drawerFocusId = null;
        notify('drawer');
      });
    });
  };

  subscribe((_, reason) => {
    if (['drawer', 'result', 'wheel', 'token', 'scenario'].includes(reason)) {
      renderDrawer();
    }
  });

  renderDrawer();
}

function renderEvidenceTab(res, q1, q2, q3, isScenario) {
  const allKpis = [...(q1.kpis || []), ...(q2.kpis || []), ...(q3.kpis || [])];
  const kpiCards = allKpis
    .map((k) => {
      const isFocused = state.drawerFocusId === k.id;
      return `
        <div class="drawer-card ${isFocused ? 'highlight' : ''}">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="micro-label">${k.label}</span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span class="mono" style="font-size:14px;color:var(--accent);">${k.provenance}</span>
              ${renderGlyphSVG(k.glyph, k.tooltip)}
            </div>
          </div>
          <div style="display:flex;align-items:baseline;gap:8px;">
            <span class="mono" style="font-size:24px;font-weight:500;color:var(--ink);">${k.display_value}</span>
            <span class="mono" style="font-size:14px;color:var(--ink-3);">${k.unit}</span>
          </div>
          <div style="font-size:14px;color:var(--ink-2);">${k.tooltip}</div>
          <div class="mono" style="font-size:14px;color:var(--ink-3);">Source: ${k.source} · Valid: ${k.valid_time}</div>
        </div>
      `;
    })
    .join('');

  const cropCards = (q3.crops || [])
    .map((c) => {
      const isFocused = state.drawerFocusId === c.id;
      return `
        <div class="drawer-card ${isFocused ? 'highlight' : ''}">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span style="font-size:16px;font-weight:500;color:var(--ink);">${c.name} (${c.window_label})</span>
            <span class="mono" style="font-size:14px;color:var(--accent);">${c.confidence_word}</span>
          </div>
          <div style="font-size:14px;color:var(--ink-2);"><strong>Why it fits:</strong> ${c.why}</div>
          <div style="font-size:14px;color:var(--ink-2);"><strong>Watch-out:</strong> ${c.watch}</div>
          <div style="font-size:14px;color:var(--ink-3);">${c.verify}</div>
        </div>
      `;
    })
    .join('');

  const checklistItems = (q3.verification_checklist || [])
    .map((item) => `<li style="margin-left:18px;font-size:14px;color:var(--ink-2);">${item}</li>`)
    .join('');

  const unknownItems = UNKNOWN_PARAMETERS.map(
    (u) => `<li style="margin-left:18px;font-size:14px;color:var(--ink-3);"><span class="mono" style="color:var(--accent);">UNKNOWN</span> — ${u} (not available without field/satellite input)</li>`
  ).join('');

  return `
    ${isScenario ? `<div class="drawer-card highlight"><div class="micro-label" style="color:var(--accent);">SCENARIO ACTIVE · SIMULATED</div><div style="font-size:14px;color:var(--ink-2);">Showing perturbed water-balance values (-35% rain, +15% ET₀, -20% soil moisture). Zero external API calls made.</div></div>` : ''}
    <div class="micro-label">KEY INDICATORS & PROVENANCE</div>
    ${kpiCards}
    <div class="micro-label" style="margin-top:6px;">UK CANDIDATE CROPS (RULE TABLE)</div>
    ${cropCards}
    <div class="drawer-card">
      <div class="micro-label">ON-GROUND VERIFICATION CHECKLIST</div>
      <ul style="display:flex;flex-direction:column;gap:4px;">${checklistItems}</ul>
    </div>
    <div class="drawer-card">
      <div class="micro-label">UNMEASURED FIELD & SATELLITE PARAMETERS</div>
      <ul style="display:flex;flex-direction:column;gap:4px;">${unknownItems}</ul>
    </div>
  `;
}

function renderMethodTab(res, isScenario) {
  return `
    <div class="drawer-card">
      <div class="micro-label">DETERMINISTIC WATER BALANCE & HORIZON CHIPS</div>
      <div style="font-size:14px;color:var(--ink-2);">
        All numerical indicators and risk chips (<span class="mono">LOW</span>, <span class="mono">WATCH</span>, <span class="mono">ELEVATED</span>, <span class="mono">INCONCLUSIVE</span>) are computed deterministically in Python (<span class="mono">indicators.py</span>) before any Gemini agent is called. Agents cannot alter numeric values or horizon classifications.
      </div>
    </div>
    <div class="drawer-card">
      <div class="micro-label">Q1 · HOW DRY IS IT NOW? (PAST 30 DAYS)</div>
      <div style="font-size:14px;color:var(--ink-2);">
        Compares cumulative 30-day precipitation against the 10-year (2016–2025) same-calendar-window mean at the nearest Open-Meteo archive grid cell, combined with hourly volumetric soil moisture across three depths (0–7 cm topsoil, 7–28 cm root zone, 28–100 cm deep subsoil) and dry-day count (&lt; 1.0 mm) over the last 14 days.
      </div>
    </div>
    <div class="drawer-card">
      <div class="micro-label">Q2 · WHAT IS COMING? (7–15d & 1–3m)</div>
      <div style="font-size:14px;color:var(--ink-2);">
        <strong>7–15 days:</strong> Cumulative forecast precipitation minus FAO Penman-Monteith reference evapotranspiration (<span class="mono">P − ET₀</span>) plus projected root-zone soil moisture trend.<br/>
        <strong>1–3 months:</strong> 50-member seasonal ensemble anomaly distribution (<span class="mono">p25</span>, <span class="mono">median</span>, <span class="mono">p75</span>) relative to the 10-year baseline. Explicitly reports <em>"No clear signal"</em> when the interquartile range straddles zero.
      </div>
    </div>
    <div class="drawer-card ${isScenario ? 'highlight' : ''}">
      <div class="micro-label">SCENARIO · 30 DRY DAYS PERTURBATION</div>
      <div style="font-size:14px;color:var(--ink-2);">
        Applies an instant in-memory stress perturbation (<span class="mono">-35%</span> precipitation, <span class="mono">+15%</span> FAO ET₀, <span class="mono">-20%</span> volumetric soil moisture across all 3 depths) and re-evaluates <span class="mono">compute_drought_indicators()</span> and <span class="mono">match_uk_crops()</span> with zero network calls.
      </div>
    </div>
  `;
}

function renderSourcesTab(res) {
  const sources = res?.sources || [];
  return sources
    .map((s) => {
      const isFocused = state.drawerFocusId === s.id;
      return `
        <div class="drawer-card ${isFocused ? 'highlight' : ''}">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span style="font-size:16px;font-weight:500;color:var(--ink);">${s.name}</span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span class="mono" style="font-size:14px;color:var(--accent);">${s.provenance}</span>
              ${renderGlyphSVG(s.glyph, s.provenance)}
            </div>
          </div>
          <div style="font-size:14px;color:var(--ink-2);">${s.summary}</div>
          <div class="mono" style="font-size:14px;color:var(--ink-3);">
            Grid: ${s.grid_cell} · Valid: ${s.valid_time} · Fetched: ${s.fetched_time} (${s.latency_ms} ms)
          </div>
        </div>
      `;
    })
    .join('');
}

function renderAssumptionsTab(res) {
  const list = res?.assumptions || [];
  const cards = list
    .map(
      (a, idx) => `
        <div class="drawer-card">
          <div class="micro-label">ASSUMPTION 0${idx + 1}</div>
          <div style="font-size:14px;color:var(--ink-2);">${a}</div>
        </div>
      `
    )
    .join('');

  return `
    ${cards}
    <div class="drawer-card">
      <div class="micro-label">MODEL & FALLBACK CONFIGURATION</div>
      <div class="mono" style="font-size:14px;color:var(--ink-2);">
        Primary model: <span style="color:var(--accent);">${res?.provenance?.primary_model || 'gemini-3-flash-preview'}</span><br/>
        Fallback model: <span style="color:var(--accent);">${res?.provenance?.fallback_model || 'gemini-3.1-flash-lite-preview'}</span><br/>
        Thinking config: thinking_level=LOW, include_thoughts=False
      </div>
    </div>
  `;
}

function renderAgentsTab(res) {
  const order = ['meteorologist', 'hydrologist', 'agronomist'];
  return order
    .map((id) => {
      const ag = res?.agents?.[id] || {};
      const wheelAg = state.wheel?.agents?.[id] || {};
      const isFocused = state.drawerFocusId === id;
      const isStreaming = wheelAg.state === 'active' && state.runState === 'RUNNING';
      const bodyText = isStreaming ? (wheelAg.streamText || 'Streaming structured analysis…') : (ag.text || wheelAg.streamText || 'Waiting…');
      const modelId = wheelAg.model || ag.model || 'gemini-3-flash-preview';
      const mode = wheelAg.mode || ag.mode || 'LIVE';

      return `
        <div class="drawer-card ${isFocused || isStreaming ? 'highlight' : ''}">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span style="font-size:16px;font-weight:500;color:var(--ink);">${ag.title || id}</span>
            <div style="display:flex;align-items:center;gap:6px;">
              <span class="mono" style="font-size:14px;color:var(--accent);">${modelId} · ${mode}</span>
              ${renderGlyphSVG(ag.glyph || 'AI-GENERATED', `${modelId} (${mode})`)}
            </div>
          </div>
          <div style="font-size:14px;line-height:21px;color:var(--ink-2);white-space:pre-wrap;">${bodyText}</div>
          ${
            ag.takeaway
              ? `<div style="margin-top:4px;padding-top:8px;border-top:1px solid var(--line);font-family:var(--font-mono);font-size:14px;color:var(--accent);">${ag.takeaway}</div>`
              : ''
          }
        </div>
      `;
    })
    .join('');
}

function renderFeedTab(res) {
  const feed = res?.feed || [];
  if (!feed.length) {
    return `<div class="drawer-card"><div class="mono" style="font-size:14px;color:var(--ink-3);">No events recorded yet.</div></div>`;
  }
  return feed
    .map(
      (f) => `
        <div class="drawer-card" style="padding:10px 14px;gap:4px;">
          <div style="display:flex;align-items:center;justify-content:space-between;">
            <span class="mono" style="font-size:14px;color:var(--accent);">${f.source}</span>
            <span class="mono" style="font-size:14px;color:var(--ink-3);">${f.ts} · ${f.type}</span>
          </div>
          <div class="mono" style="font-size:14px;color:var(--ink-2);">${f.text}</div>
        </div>
      `
    )
    .join('');
}
