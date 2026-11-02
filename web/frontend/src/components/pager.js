/**
 * Persistent Bottom-Centre Pager & Edge Chevrons — Orbital Agronomist (v5)
 * Renders `● Place   ○ Analysis   ○ Outlook` and left/right edge chevrons.
 */

import { state, subscribe } from '../state.js';
import { navigateTo } from '../router.js';

const PAGES = [
  { id: 'place', label: 'Place' },
  { id: 'analysis', label: 'Analysis' },
  { id: 'outlook', label: 'Outlook' },
];

export function initPager() {
  const pagerMount = document.getElementById('global-pager');
  const leftChevron = document.getElementById('chevron-left');
  const rightChevron = document.getElementById('chevron-right');

  if (!pagerMount) return;

  pagerMount.innerHTML = PAGES.map(
    (p) => `
      <button type="button" class="pager-btn interactive" data-route="${p.id}" aria-label="Go to ${p.label} page">
        <span class="pager-dot" data-dot="${p.id}">○</span>
        <span>${p.label}</span>
      </button>
    `
  ).join('');

  pagerMount.querySelectorAll('.pager-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const target = btn.getAttribute('data-route');
      navigateTo(target);
    });
  });

  if (leftChevron) {
    leftChevron.addEventListener('click', () => {
      const idx = PAGES.findIndex((p) => p.id === state.route);
      if (idx > 0) navigateTo(PAGES[idx - 1].id);
    });
  }

  if (rightChevron) {
    rightChevron.addEventListener('click', () => {
      const idx = PAGES.findIndex((p) => p.id === state.route);
      if (idx < PAGES.length - 1) navigateTo(PAGES[idx + 1].id);
    });
  }

  const updatePagerUI = () => {
    const idx = PAGES.findIndex((p) => p.id === state.route);
    pagerMount.querySelectorAll('.pager-btn').forEach((btn) => {
      const r = btn.getAttribute('data-route');
      const isAct = r === state.route;
      btn.classList.toggle('active', isAct);
      const dot = btn.querySelector('.pager-dot');
      if (dot) dot.textContent = isAct ? '●' : '○';
    });

    if (leftChevron) leftChevron.disabled = idx <= 0;
    if (rightChevron) rightChevron.disabled = idx >= PAGES.length - 1;
  };

  subscribe(updatePagerUI);
  updatePagerUI();
}
