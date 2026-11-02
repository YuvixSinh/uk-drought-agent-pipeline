/**
 * Main Application Entrypoint — Orbital Agronomist (v5)
 * Bootstraps the persistent 3D globe, 3-page parallax router (`#place`, `#analysis`, `#outlook`),
 * bottom pager, edge chevrons, Details drawer, global tooltips, and keyboard shortcuts.
 */

import { state, notify } from './state.js';
import { initRouter } from './router.js';
import { initPager } from './components/pager.js';
import { initGlobalTooltips } from './components/glyphs.js';
import { initPersistentGlobe } from './components/globe.js';
import { initDrawer } from './components/drawer.js';
import { initPlacePage, handleCoordinateSelection, startConfirmedRun, triggerDemoRun } from './pages/place.js';
import { initAnalysisPage } from './pages/analysis.js';
import { initOutlookPage, toggleScenarioMode } from './pages/outlook.js';

function handleGlobalShortcut(e) {
  if (e.key === 'Escape') {
    if (state.drawerOpen) {
      state.drawerOpen = false;
      notify('drawer');
    }
    return;
  }

  if (e.key === 'd' || e.key === 'D') {
    e.preventDefault();
    state.demoMode = !state.demoMode;
    notify('demo');
    if (state.demoMode) {
      triggerDemoRun(state.demoCity || 'cambridge', true);
    }
    return;
  }

  if ((e.key === 's' || e.key === 'S') && state.route === 'outlook') {
    e.preventDefault();
    toggleScenarioMode();
    return;
  }

  if (e.key === 'Enter' && state.route === 'place' && state.selection.valid) {
    e.preventDefault();
    startConfirmedRun();
  }
}

document.addEventListener('DOMContentLoaded', () => {
  initPlacePage();
  initAnalysisPage();
  initOutlookPage();
  initDrawer();
  initPager();
  initGlobalTooltips();
  initRouter(handleGlobalShortcut);
  initPersistentGlobe(handleCoordinateSelection);
});
