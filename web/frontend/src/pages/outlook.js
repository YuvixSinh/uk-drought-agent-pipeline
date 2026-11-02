/**
 * Page 3: `#outlook` (Three-Question Split View) — Orbital Agronomist (v5)
 * Three equal columns (`Q1: How dry is it now?`, `Q2: What is coming?`, `Q3: What could grow?`)
 * with deterministic <=14-word headlines, SVG arc gauges, hero numbers, hand-built SVG charts,
 * Scenario (`30 dry days`) toggle, `.txt` Dossier export, Details drawer trigger, and persistent disclaimer.
 */

import { state, subscribe, notify, getActiveQPayloads } from '../state.js';
import { apiToggleScenario, getDossierDownloadUrl } from '../api.js';
import { renderGlyphSVG } from '../components/glyphs.js';
import { renderSingleGaugeSVG, renderDualHorizonGaugesSVG } from '../components/charts/gauge.js';
import { renderRainBaselineSVG } from '../components/charts/rainBaseline.js';
import { renderSoilProfileSVG } from '../components/charts/soilProfile.js';
import { renderNetBalanceSVG } from '../components/charts/netBalance.js';
import { renderSeasonalRangeSVG } from '../components/charts/seasonalRange.js';
import { renderCropTilesHTML } from '../components/charts/cropTimeline.js';

export function initOutlookPage() {
  const screenEl = document.getElementById('page-outlook');
  if (!screenEl) return;

  const renderOutlook = () => {
    const res = state.result;
    const { q1, q2, q3, isScenario } = getActiveQPayloads();
    const loc = res?.location || state.selection;
    const ns = (loc?.lat ?? 52.21) >= 0 ? 'N' : 'S';
    const ew = (loc?.lon ?? 0.12) >= 0 ? 'E' : 'W';
    const coordStr = `${Math.abs(loc?.lat ?? 52.21).toFixed(2)}°${ns} ${Math.abs(loc?.lon ?? 0.12).toFixed(2)}°${ew}`;

    const modeBadgeText = isScenario
      ? 'SCENARIO · SIMULATED'
      : res?.is_demo
      ? 'CACHED DEMO'
      : 'LIVE RUN';

    const kpi1 = q1.kpis?.[0] || { id: 'rain_anom_30d', display_value: '-20%', unit: 'vs 10y mean', label: '30-day rain anomaly', glyph: 'CACHED', tooltip: '' };
    const kpi2 = q1.kpis?.[1] || { id: 'root_zone_sm', display_value: '0.24', unit: 'm³/m³', label: 'Root-zone moisture (7–28 cm)', glyph: 'CACHED', tooltip: '' };

    const q2Kpi1 = q2.kpis?.[0] || { id: 'net_p_et0_15d', display_value: '+3.2', unit: 'mm', label: 'Next 15-day net P − ET₀', glyph: 'CACHED', tooltip: '' };
    const q2Kpi2 = q2.kpis?.[1] || { id: 'seasonal_anom_90d', display_value: '-6%', unit: 'IQR -16% to +8%', label: '1–3 month seasonal anomaly', glyph: 'CACHED', tooltip: '' };

    const q3Kpi1 = q3.kpis?.[0] || { id: 'soil_temp_0_7', display_value: '9.8', unit: '°C · 0–7 cm', label: 'Topsoil temperature', glyph: 'CACHED', tooltip: '' };

    const protectList = q3.protect_prepare || [];
    const activeProtectIdx = Math.min(state.protectIdx || 0, Math.max(0, protectList.length - 1));
    const activeProtect = protectList[activeProtectIdx] || { horizon: '24–72 h', action: 'Consolidate seedbeds to conserve topsoil moisture.' };

    const protectPipsHTML = protectList
      .map(
        (p, idx) => `
          <button type="button" class="protect-pip-btn interactive ${idx === activeProtectIdx ? 'active' : ''}" data-protect-idx="${idx}">
            ${p.horizon}
          </button>
        `
      )
      .join('');

    const dossierUrl = getDossierDownloadUrl(state.runId || res?.run_id, isScenario);

    screenEl.innerHTML = `
      <div class="outlook-shell">
        <!-- Top Header Bar -->
        <header class="outlook-header">
          <div class="outlook-loc-group">
            <span class="wordmark" style="font-size:14px;">
              <span class="wordmark-dot"></span>
              <span>OUTLOOK</span>
            </span>
            <span class="badge-pill">
              ${coordStr} · ${loc?.nation || 'England'} · Grid ${loc?.grid_cell || '52.20°N, 0.10°E'}
            </span>
            <span id="outlook-mode-badge" class="badge-pill ${isScenario ? 'accent' : ''}">
              ${modeBadgeText}
            </span>
          </div>

          <div class="outlook-actions-group interactive">
            <button
              type="button"
              id="btn-scenario-toggle"
              class="btn-glass ${isScenario ? 'active-toggle' : ''}"
              title="Toggle 30 dry days stress scenario (-35% rain, +15% ET0, -20% soil moisture · Shortcut: S)"
            >
              <span>◆ Scenario: 30 dry days</span>
            </button>
            <a
              id="btn-export-dossier"
              href="${dossierUrl}"
              download="orbital_agronomist_${state.runId || 'dossier'}.txt"
              class="btn-glass"
              style="text-decoration:none;"
            >
              ↓ Export .txt
            </a>
            <button type="button" id="btn-outlook-details" class="btn-glass">
              Details
            </button>
          </div>
        </header>

        <!-- Three-Column Split View -->
        <div class="outlook-grid">
          <!-- COLUMN 1: Q1 How dry is it now? -->
          <section class="outlook-col interactive" aria-label="How dry is it now?">
            <div class="col-top">
              <div class="col-question">
                <span>01 · How dry is it now?</span>
                ${renderGlyphSVG(q1.glyph, q1.tooltip)}
              </div>
              <h2 id="q1-headline" class="col-headline">${q1.headline}</h2>
            </div>

            <div class="col-hero-zone">
              ${renderSingleGaugeSVG(q1.chip, 'CURRENT DRYNESS', q1.glyph, q1.tooltip)}
              <div class="kpi-stack">
                <div class="kpi-block" data-kpi-id="${kpi1.id}" data-tooltip="${String(kpi1.tooltip || '').replace(/"/g, '&quot;')}">
                  <div class="kpi-num-row">
                    <span class="kpi-big">${kpi1.display_value}</span>
                    <span class="kpi-unit">${kpi1.unit}</span>
                  </div>
                  <div class="kpi-label-row">
                    <span>${kpi1.label}</span>
                    ${renderGlyphSVG(kpi1.glyph, kpi1.tooltip)}
                  </div>
                </div>

                <div class="kpi-block" data-kpi-id="${kpi2.id}" data-tooltip="${String(kpi2.tooltip || '').replace(/"/g, '&quot;')}">
                  <div class="kpi-num-row">
                    <span class="kpi-big" style="font-size:44px;line-height:44px;">${kpi2.display_value}</span>
                    <span class="kpi-unit">${kpi2.unit}</span>
                  </div>
                  <div class="kpi-label-row">
                    <span>${kpi2.label}</span>
                    ${renderGlyphSVG(kpi2.glyph, kpi2.tooltip)}
                  </div>
                </div>
              </div>
            </div>

            <div class="col-charts-zone">
              <div class="chart-box">
                <div class="chart-header">
                  <span>30-DAY RAIN VS 10-YEAR BASELINE (2016–2025)</span>
                  <span class="mono">Mean ${(q1.mean_30d_mm ?? 57.8).toFixed(1)} mm</span>
                </div>
                ${renderRainBaselineSVG(q1.baseline_years, q1.mean_30d_mm)}
              </div>

              <div class="chart-box">
                <div class="chart-header">
                  <span>VOLUMETRIC SOIL MOISTURE PROFILE (0–100 CM)</span>
                  <span class="mono">${isScenario ? 'Solid: Sim · Dashed: Now' : 'm³/m³'}</span>
                </div>
                ${renderSoilProfileSVG(q1.soil_layers, isScenario)}
              </div>
            </div>
          </section>

          <!-- COLUMN 2: Q2 What is coming? -->
          <section class="outlook-col interactive" aria-label="What is coming?">
            <div class="col-top">
              <div class="col-question">
                <span>02 · What is coming?</span>
                ${renderGlyphSVG(q2.glyph_7_15, q2.tooltip_7_15)}
              </div>
              <h2 id="q2-headline" class="col-headline">${q2.headline}</h2>
            </div>

            <div class="col-hero-zone q2-layout">
              ${renderDualHorizonGaugesSVG(q2)}
              <div class="kpi-stack">
                <div class="kpi-block" data-kpi-id="${q2Kpi1.id}" data-tooltip="${String(q2Kpi1.tooltip || '').replace(/"/g, '&quot;')}">
                  <div class="kpi-num-row">
                    <span class="kpi-big">${q2Kpi1.display_value}</span>
                    <span class="kpi-unit">mm net</span>
                  </div>
                  <div class="kpi-label-row">
                    <span>${q2Kpi1.label}</span>
                    ${renderGlyphSVG(q2Kpi1.glyph, q2Kpi1.tooltip)}
                  </div>
                </div>

                <div class="kpi-block" data-kpi-id="${q2Kpi2.id}" data-tooltip="${String(q2Kpi2.tooltip || '').replace(/"/g, '&quot;')}">
                  <div class="kpi-num-row">
                    <span class="kpi-big" style="font-size:44px;line-height:44px;">${q2Kpi2.display_value}</span>
                    <span class="kpi-unit">${q2.seasonal?.status || 'Ensemble'}</span>
                  </div>
                  <div class="kpi-label-row">
                    <span>${q2Kpi2.label}</span>
                    ${renderGlyphSVG(q2Kpi2.glyph, q2Kpi2.tooltip)}
                  </div>
                </div>
              </div>
            </div>

            <div class="col-charts-zone">
              <div class="chart-box">
                <div class="chart-header">
                  <span>15-DAY CUMULATIVE WATER BALANCE (P − ET₀)</span>
                  <span class="mono">${isScenario ? 'Hatched < 0 · Dashed: Baseline' : 'Hatched deficit < 0 mm'}</span>
                </div>
                ${renderNetBalanceSVG(q2.net_balance_series, isScenario)}
              </div>

              <div class="chart-box">
                <div class="chart-header">
                  <span>1–3 MONTH SEASONAL ENSEMBLE SPREAD (50 MEMBERS)</span>
                  <span class="mono">${q2.seasonal?.iqr_label || 'IQR'}</span>
                </div>
                ${renderSeasonalRangeSVG(q2.seasonal)}
              </div>
            </div>
          </section>

          <!-- COLUMN 3: Q3 What could grow? -->
          <section class="outlook-col interactive" aria-label="What could grow?">
            <div class="col-top">
              <div class="col-question">
                <span>03 · What could grow?</span>
                <div style="display:flex;align-items:center;gap:6px;">
                  <span class="mono" style="color:var(--accent);">${q3Kpi1.display_value} °C soil</span>
                  ${renderGlyphSVG(q3Kpi1.glyph, q3Kpi1.tooltip)}
                </div>
              </div>
              <h2 id="q3-headline" class="col-headline">${q3.headline}</h2>
            </div>

            <!-- 3 UK Candidate Crop Tiles -->
            <div class="crop-tiles-list">
              ${renderCropTilesHTML(q3.crops)}
            </div>

            <!-- Protect & Prepare Horizon Strip + Honesty Micro-Line -->
            <div style="display:flex;flex-direction:column;gap:8px;">
              <div class="protect-strip">
                <div style="display:flex;align-items:center;justify-content:space-between;">
                  <span class="micro-label">PROTECT &amp; PREPARE</span>
                  <div class="protect-pips-row">
                    ${protectPipsHTML}
                  </div>
                </div>
                <div class="protect-action-text">${activeProtect.action}</div>
              </div>

              <div style="display:flex;align-items:center;justify-content:space-between;font-size:14px;color:var(--ink-3);">
                <span>${q3.micro_line || 'Regional candidates. Verify soil and drainage.'}</span>
                <button type="button" id="btn-verify-checklist" class="btn-glass" style="height:26px;padding:0 10px;font-size:14px;">
                  Checklist →
                </button>
              </div>
            </div>
          </section>
        </div>

        <!-- Persistent Footer Disclaimer -->
        <footer class="outlook-footer">
          <span>Model data (about 1 to 25 km), not satellite or field measurement.</span>
          <span class="mono">Primary: ${res?.provenance?.primary_model || 'gemini-3-flash-preview'} · Fallback: ${res?.provenance?.fallback_model || 'gemini-3.1-flash-lite-preview'}</span>
        </footer>
      </div>
    `;

    // Bind Scenario toggle
    screenEl.querySelector('#btn-scenario-toggle')?.addEventListener('click', () => {
      toggleScenarioMode();
    });

    // Bind Details button
    screenEl.querySelector('#btn-outlook-details')?.addEventListener('click', () => {
      state.drawerOpen = !state.drawerOpen;
      notify('drawer');
    });

    // Bind Checklist button
    screenEl.querySelector('#btn-verify-checklist')?.addEventListener('click', () => {
      state.drawerOpen = true;
      state.drawerTab = 'Evidence';
      state.drawerFocusId = null;
      notify('drawer');
    });

    // Bind Protect & Prepare horizon pips
    screenEl.querySelectorAll('.protect-pip-btn').forEach((btn) => {
      btn.addEventListener('click', () => {
        state.protectIdx = parseInt(btn.getAttribute('data-protect-idx') || '0', 10);
        renderOutlook();
      });
    });

    // Bind KPI clicks -> open Drawer Evidence tab focused on KPI
    screenEl.querySelectorAll('.kpi-block').forEach((blk) => {
      blk.addEventListener('click', () => {
        state.drawerOpen = true;
        state.drawerTab = 'Evidence';
        state.drawerFocusId = blk.getAttribute('data-kpi-id');
        notify('drawer');
      });
    });

    // Bind Crop tile clicks -> open Drawer Evidence tab focused on Crop
    screenEl.querySelectorAll('.crop-tile').forEach((tile) => {
      tile.addEventListener('click', () => {
        state.drawerOpen = true;
        state.drawerTab = 'Evidence';
        state.drawerFocusId = tile.getAttribute('data-crop-id');
        notify('drawer');
      });
    });
  };

  subscribe((_, reason) => {
    if (['result', 'scenario', 'route'].includes(reason)) {
      renderOutlook();
    }
  });

  renderOutlook();
}

export async function toggleScenarioMode() {
  state.scenarioActive = !state.scenarioActive;
  notify('scenario');

  if (state.runId) {
    try {
      await apiToggleScenario(state.runId, state.scenarioActive);
    } catch (_) {}
  }
}
