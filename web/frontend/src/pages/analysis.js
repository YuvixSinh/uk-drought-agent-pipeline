/**
 * Page 2: `#analysis` (The Wheel) — Orbital Agronomist (v5)
 * Displays the 760px SVG Analysis Wheel centred over the shrunken persistent globe orb,
 * top bar (`✕ Cancel`, location pill, `Replay`, `Details`), and 1-line mono ticker.
 */

import { state, subscribe, notify } from '../state.js';
import { apiCancelRun } from '../api.js';
import { closeActiveStream, runChoreographedDemoWheel } from '../sse.js';
import { renderWheelSVG, bindWheelNodeClicks } from '../components/wheel.js';
import { navigateTo } from '../router.js';

export function initAnalysisPage() {
  const screenEl = document.getElementById('page-analysis');
  if (!screenEl) return;

  screenEl.innerHTML = `
    <header class="analysis-topbar">
      <div style="display:flex;align-items:center;gap:12px;" class="interactive">
        <button type="button" id="btn-analysis-cancel" class="btn-glass" aria-label="Cancel run and return to Place">
          ✕ Cancel
        </button>
        <span id="analysis-loc-pill" class="badge-pill">
          52.21°N 0.12°E · England
        </span>
      </div>

      <div style="display:flex;align-items:center;gap:10px;" class="interactive">
        <button type="button" id="btn-analysis-replay" class="btn-glass" title="Replay wheel choreography">
          ↻ Replay
        </button>
        <button type="button" id="btn-analysis-to-outlook" class="btn-accent">
          Outlook →
        </button>
        <button type="button" id="btn-analysis-details" class="btn-glass">
          Details
        </button>
      </div>
    </header>

    <div class="wheel-stage">
      <div id="wheel-mount" class="wheel-container interactive"></div>
      <div id="wheel-ticker-text" class="wheel-ticker">Analysis complete · Ready for Outlook</div>
    </div>
  `;

  const wheelMount = screenEl.querySelector('#wheel-mount');
  const tickerEl = screenEl.querySelector('#wheel-ticker-text');
  const locPill = screenEl.querySelector('#analysis-loc-pill');
  const btnCancel = screenEl.querySelector('#btn-analysis-cancel');
  const btnReplay = screenEl.querySelector('#btn-analysis-replay');
  const btnToOutlook = screenEl.querySelector('#btn-analysis-to-outlook');
  const btnDetails = screenEl.querySelector('#btn-analysis-details');

  btnCancel?.addEventListener('click', async () => {
    closeActiveStream();
    if (state.runState === 'RUNNING' && state.runId) {
      try {
        await apiCancelRun(state.runId);
      } catch (_) {}
    }
    state.runState = 'SELECTED';
    notify('cancel');
    navigateTo('place');
  });

  btnReplay?.addEventListener('click', () => {
    if (state.result) {
      runChoreographedDemoWheel(state.result, false);
    }
  });

  btnToOutlook?.addEventListener('click', () => {
    navigateTo('outlook');
  });

  btnDetails?.addEventListener('click', () => {
    state.drawerOpen = !state.drawerOpen;
    if (state.drawerOpen && !state.drawerTab) {
      state.drawerTab = 'Agents';
    }
    notify('drawer');
  });

  const renderAnalysis = () => {
    const sel = state.selection;
    if (locPill && sel) {
      const ns = sel.lat >= 0 ? 'N' : 'S';
      const ew = sel.lon >= 0 ? 'E' : 'W';
      locPill.textContent = `${Math.abs(sel.lat).toFixed(2)}°${ns} ${Math.abs(sel.lon).toFixed(2)}°${ew} · ${sel.nation || 'UK Land'} · Grid ${sel.grid_cell || ''}`;
    }

    if (wheelMount) {
      wheelMount.innerHTML = renderWheelSVG();
      bindWheelNodeClicks(wheelMount);
    }

    if (tickerEl) {
      tickerEl.textContent = state.wheel.ticker || '';
    }
  };

  subscribe((_, reason) => {
    if (['wheel', 'result', 'selection', 'route', 'quality'].includes(reason)) {
      renderAnalysis();
    }
  });

  renderAnalysis();
}
