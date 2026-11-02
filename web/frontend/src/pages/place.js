/**
 * Page 1: `#place` (The Globe Selection Screen) — Orbital Agronomist (v5)
 * Minimalist full-screen UK globe interface:
 * - Top-left wordmark `ORBITAL AGRONOMIST`
 * - Bottom-left <= 40 word intro + 5 city shortcut pills
 * - Top-right `⋯` menu (manual Lat/Lon, Demo mode `D`, Force model fallback)
 * - Bottom-centre slim Confirm bar (`52.21°N 0.12°E · England`, `Confirm`, `Clear`)
 * - Non-UK sea/land toast: `"Not UK land. No data requested."`
 */

import { state, CITY_SHORTCUTS, subscribe, notify } from '../state.js';
import { apiValidatePoint, apiStartRun, apiGetDemo } from '../api.js';
import { connectLiveRunStream, runChoreographedDemoWheel } from '../sse.js';
import { updateGlobeMarkers, focusGlobeOn } from '../components/globe.js';
import { navigateTo } from '../router.js';

let toastTimer = null;

export function initPlacePage() {
  const screenEl = document.getElementById('page-place');
  if (!screenEl) return;

  const pillsHTML = CITY_SHORTCUTS.map(
    (c) => `
      <button type="button" class="city-pill interactive" data-city-id="${c.id}" data-lat="${c.lat}" data-lon="${c.lon}">
        ${c.name}
      </button>
    `
  ).join('');

  screenEl.innerHTML = `
    <!-- Top-Left Wordmark -->
    <header class="place-header">
      <div class="wordmark">
        <span class="wordmark-dot"></span>
        <span>ORBITAL AGRONOMIST</span>
      </div>
      <div class="wordmark-sub">UK Water Balance &amp; Seasonal Horizon Engine</div>
    </header>

    <!-- Top-Right Controls & Popover Menu -->
    <div class="place-menu-wrap interactive">
      <button type="button" id="place-demo-pill" class="btn-glass" title="Toggle instant cached Demo Mode (Shortcut: D)">
        Demo: OFF
      </button>
      <button type="button" id="place-menu-btn" class="btn-glass" aria-label="Open coordinate and developer menu">
        ⋯ Menu
      </button>

      <div id="place-popover" class="popover-panel">
        <div class="popover-row">
          <div class="micro-label">MANUAL UK COORDINATE</div>
          <div class="coord-inputs">
            <input id="input-lat" type="number" step="0.01" class="input-dark" placeholder="Lat (e.g. 52.21)" value="52.2053" />
            <input id="input-lon" type="number" step="0.01" class="input-dark" placeholder="Lon (e.g. 0.12)" value="0.1218" />
          </div>
          <button type="button" id="btn-validate-manual" class="btn-glass" style="justify-content:center;width:100%;">
            Validate Point
          </button>
        </div>

        <div class="popover-row" style="border-top:1px solid var(--line);padding-top:12px;">
          <div class="micro-label">CACHED DEMO PRESET (SHORTCUT: D)</div>
          <div style="display:flex;gap:8px;">
            <select id="select-demo-city" class="input-dark" style="flex:1;">
              <option value="cambridge">Cambridge (England)</option>
              <option value="edinburgh">Edinburgh (Scotland)</option>
              <option value="belfast">Belfast (N. Ireland)</option>
              <option value="norwich">Norwich (East Anglia)</option>
              <option value="cardiff">Cardiff (Wales)</option>
            </select>
            <button type="button" id="btn-load-demo-now" class="btn-accent" style="padding:0 14px;">
              Load
            </button>
          </div>
        </div>

        <div class="popover-row" style="border-top:1px solid var(--line);padding-top:12px;">
          <label style="display:flex;align-items:center;justify-content:space-between;cursor:pointer;font-size:14px;color:var(--ink-2);">
            <span>Force primary model fallback</span>
            <input id="chk-force-fallback" type="checkbox" style="accent-color:var(--accent);width:16px;height:16px;" />
          </label>
        </div>
      </div>
    </div>

    <!-- Bottom-Left Intro (<= 40 words) + 5 City Shortcut Beacons -->
    <div class="place-intro">
      <p class="place-intro-copy">
        Click any point on UK land to inspect 30-day water balance, 15-day forecast, seasonal ensemble spread, and weather-matched crop windows.
      </p>
      <div class="city-beacons-bar interactive">
        ${pillsHTML}
      </div>
    </div>

    <!-- Non-UK Toast -->
    <div id="place-toast" class="place-toast" role="status" aria-live="polite">
      Not UK land. No data requested.
    </div>

    <!-- Bottom-Centre Slim Confirm Bar -->
    <div id="place-confirm-bar" class="confirm-bar visible interactive">
      <div style="display:flex;flex-direction:column;gap:2px;">
        <div id="confirm-coord-text" class="confirm-coord">52.21°N 0.12°E · England</div>
        <div id="confirm-sub-text" class="confirm-sub">~1–25 km model grid · Grid 52.20°N, 0.10°E</div>
      </div>
      <div style="display:flex;align-items:center;gap:8px;">
        <button type="button" id="btn-confirm-run" class="btn-accent">
          Confirm
        </button>
        <button type="button" id="btn-clear-selection" class="btn-glass">
          Clear
        </button>
      </div>
    </div>
  `;

  const popover = screenEl.querySelector('#place-popover');
  const menuBtn = screenEl.querySelector('#place-menu-btn');
  const demoPill = screenEl.querySelector('#place-demo-pill');
  const inputLat = screenEl.querySelector('#input-lat');
  const inputLon = screenEl.querySelector('#input-lon');
  const btnValidateManual = screenEl.querySelector('#btn-validate-manual');
  const selectDemoCity = screenEl.querySelector('#select-demo-city');
  const btnLoadDemoNow = screenEl.querySelector('#btn-load-demo-now');
  const chkForceFallback = screenEl.querySelector('#chk-force-fallback');
  const btnConfirmRun = screenEl.querySelector('#btn-confirm-run');
  const btnClearSelection = screenEl.querySelector('#btn-clear-selection');

  menuBtn?.addEventListener('click', (e) => {
    e.stopPropagation();
    popover?.classList.toggle('open');
  });

  document.addEventListener('click', (e) => {
    if (popover?.classList.contains('open') && !popover.contains(e.target) && e.target !== menuBtn) {
      popover.classList.remove('open');
    }
  });

  demoPill?.addEventListener('click', () => {
    state.demoMode = !state.demoMode;
    notify('demo');
  });

  chkForceFallback?.addEventListener('change', () => {
    state.forceModelFail = Boolean(chkForceFallback.checked);
    notify('config');
  });

  selectDemoCity?.addEventListener('change', () => {
    state.demoCity = selectDemoCity.value;
  });

  btnLoadDemoNow?.addEventListener('click', async () => {
    const city = selectDemoCity?.value || 'cambridge';
    state.demoCity = city;
    state.demoMode = true;
    popover?.classList.remove('open');
    await triggerDemoRun(city, true);
  });

  btnValidateManual?.addEventListener('click', async () => {
    const lat = parseFloat(inputLat?.value || '52.2053');
    const lon = parseFloat(inputLon?.value || '0.1218');
    popover?.classList.remove('open');
    await handleCoordinateSelection(lat, lon);
  });

  screenEl.querySelectorAll('.city-pill').forEach((pill) => {
    pill.addEventListener('click', async () => {
      const lat = parseFloat(pill.getAttribute('data-lat'));
      const lon = parseFloat(pill.getAttribute('data-lon'));
      const cityId = pill.getAttribute('data-city-id');
      if (cityId) state.demoCity = cityId;
      await handleCoordinateSelection(lat, lon);
    });
  });

  window.addEventListener('globe-city-select', async (e) => {
    if (e.detail) {
      await handleCoordinateSelection(e.detail.lat, e.detail.lon);
    }
  });

  btnClearSelection?.addEventListener('click', () => {
    state.selection.valid = false;
    state.runState = 'IDLE';
    updateGlobeMarkers();
    notify('selection');
  });

  btnConfirmRun?.addEventListener('click', async () => {
    if (!state.selection.valid) return;
    await startConfirmedRun();
  });

  const syncPlaceUI = () => {
    const sel = state.selection;
    const confirmBar = screenEl.querySelector('#place-confirm-bar');
    const coordTxt = screenEl.querySelector('#confirm-coord-text');
    const subTxt = screenEl.querySelector('#confirm-sub-text');

    if (demoPill) {
      demoPill.textContent = state.demoMode ? `Demo: ON (${state.demoCity})` : 'Demo: OFF';
      demoPill.classList.toggle('active-toggle', state.demoMode);
    }

    if (sel && sel.valid) {
      confirmBar?.classList.add('visible');
      const ns = sel.lat >= 0 ? 'N' : 'S';
      const ew = sel.lon >= 0 ? 'E' : 'W';
      if (coordTxt) {
        coordTxt.textContent = `${Math.abs(sel.lat).toFixed(2)}°${ns} ${Math.abs(sel.lon).toFixed(2)}°${ew} · ${sel.nation || 'UK Land'}`;
      }
      if (subTxt) {
        subTxt.textContent = `~1–25 km model grid · Grid ${sel.grid_cell || ''}`;
      }
      if (inputLat && document.activeElement !== inputLat) inputLat.value = sel.lat.toFixed(4);
      if (inputLon && document.activeElement !== inputLon) inputLon.value = sel.lon.toFixed(4);
    } else {
      confirmBar?.classList.remove('visible');
    }

    screenEl.querySelectorAll('.city-pill').forEach((pill) => {
      const pLat = parseFloat(pill.getAttribute('data-lat'));
      const pLon = parseFloat(pill.getAttribute('data-lon'));
      const isMatch = sel.valid && Math.hypot(sel.lat - pLat, sel.lon - pLon) < 0.15;
      pill.classList.toggle('selected', Boolean(isMatch));
    });
  };

  subscribe(syncPlaceUI);
  syncPlaceUI();
}

export async function handleCoordinateSelection(lat, lon) {
  try {
    const res = await apiValidatePoint(lat, lon);
    if (!res.valid) {
      showNotUkToast(res.reason || 'Not UK land. No data requested.');
      return;
    }

    hideNotUkToast();
    state.selection = {
      valid: true,
      lat: res.lat,
      lon: res.lon,
      nation: res.nation || 'UK Land',
      grid_cell: res.grid_cell,
      label: res.label,
      context: res.context,
    };
    state.runState = 'SELECTED';

    // Match closest demo city if within 0.25 deg
    const matchedCity = CITY_SHORTCUTS.find((c) => Math.hypot(c.lat - res.lat, c.lon - res.lon) < 0.25);
    if (matchedCity) {
      state.demoCity = matchedCity.id;
    }

    updateGlobeMarkers();
    focusGlobeOn(res.lat, res.lon, 0.66, 600);
    notify('selection');
  } catch (err) {
    console.error('Coordinate validation failed:', err);
  }
}

export async function startConfirmedRun() {
  if (!state.selection.valid) return;
  navigateTo('analysis');

  if (state.demoMode) {
    await triggerDemoRun(state.demoCity || 'cambridge', true);
    return;
  }

  try {
    const startResp = await apiStartRun(
      state.selection.lat,
      state.selection.lon,
      state.forceModelFail
    );
    connectLiveRunStream(startResp.run_id);
  } catch (err) {
    console.warn('Live run start failed; falling back to cached demo:', err);
    await triggerDemoRun(state.demoCity || 'cambridge', true);
  }
}

export async function triggerDemoRun(cityName = 'cambridge', animateWheel = true) {
  try {
    const demoResult = await apiGetDemo(cityName);
    state.selection = {
      valid: true,
      lat: demoResult.location.lat,
      lon: demoResult.location.lon,
      nation: demoResult.location.nation,
      grid_cell: demoResult.location.grid_cell,
      label: demoResult.location.label,
      context: '~1–25 km model grid · Cached Demo',
    };
    updateGlobeMarkers();
    if (animateWheel) {
      navigateTo('analysis');
      runChoreographedDemoWheel(demoResult, true);
    } else {
      state.result = demoResult;
      state.runId = demoResult.run_id;
      state.runState = 'DONE';
      state.scenarioActive = false;
      notify('result');
    }
  } catch (err) {
    console.error('Demo load failed:', err);
  }
}

function showNotUkToast(msg) {
  const toast = document.getElementById('place-toast');
  if (!toast) return;
  toast.textContent = msg || 'Not UK land. No data requested.';
  toast.classList.add('visible');
  if (toastTimer) clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    toast.classList.remove('visible');
  }, 2600);
}

function hideNotUkToast() {
  const toast = document.getElementById('place-toast');
  if (!toast) return;
  toast.classList.remove('visible');
}
