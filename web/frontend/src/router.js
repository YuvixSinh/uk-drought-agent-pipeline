/**
 * Hash Router & Page Transition Controller — Orbital Agronomist (v5)
 * Manages `#place`, `#analysis`, and `#outlook` routes and drives the
 * 700 ms horizontal parallax track + persistent globe transform.
 */

import { state, notify } from './state.js';

const VALID_ROUTES = ['place', 'analysis', 'outlook'];

export function navigateTo(route, updateHash = true) {
  const clean = String(route || 'place').replace(/^#/, '').toLowerCase();
  const target = VALID_ROUTES.includes(clean) ? clean : 'place';

  state.route = target;
  if (updateHash && window.location.hash !== `#${target}`) {
    window.history.pushState(null, '', `#${target}`);
  }
  applyRouteDOM(target);
  notify('route');
}

export function applyRouteDOM(route) {
  const track = document.getElementById('pages-track');
  const globeLayer = document.getElementById('globe-persistent-layer');

  const idx = VALID_ROUTES.indexOf(route);
  const offsetVw = idx >= 0 ? -idx * 100 : 0;

  if (track) {
    track.style.transform = `translate3d(${offsetVw}vw, 0, 0)`;
  }

  if (globeLayer) {
    globeLayer.classList.remove('mode-place', 'mode-analysis', 'mode-outlook');
    globeLayer.classList.add(`mode-${route}`);
  }
}

export function initRouter(onKeyboardShortcut) {
  const syncFromHash = () => {
    const raw = window.location.hash.replace(/^#/, '').toLowerCase();
    const target = VALID_ROUTES.includes(raw) ? raw : 'place';
    if (!window.location.hash) {
      window.history.replaceState(null, '', '#place');
    }
    state.route = target;
    applyRouteDOM(target);
    notify('route');
  };

  window.addEventListener('hashchange', syncFromHash);
  syncFromHash();

  window.addEventListener('keydown', (e) => {
    const tag = (e.target && e.target.tagName) ? e.target.tagName.toUpperCase() : '';
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || e.target?.isContentEditable) {
      if (e.key === 'Escape') {
        e.target.blur();
      }
      return;
    }

    if (e.key === 'ArrowRight') {
      e.preventDefault();
      const idx = VALID_ROUTES.indexOf(state.route);
      if (idx < VALID_ROUTES.length - 1) {
        navigateTo(VALID_ROUTES[idx + 1]);
      }
    } else if (e.key === 'ArrowLeft') {
      e.preventDefault();
      const idx = VALID_ROUTES.indexOf(state.route);
      if (idx > 0) {
        navigateTo(VALID_ROUTES[idx - 1]);
      }
    } else if (onKeyboardShortcut) {
      onKeyboardShortcut(e);
    }
  });
}
