/**
 * Provenance SVG Glyphs & Global Tooltip — Orbital Agronomist (v5)
 * Implements the 5 geometric provenance glyphs in `--accent` (#FFB454):
 * - LIVE         : solid 8px circle
 * - CACHED       : hollow 8px circle (1.5px stroke)
 * - SIMULATED    : hollow diamond
 * - FALLBACK     : hollow triangle
 * - AI-GENERATED : 4-point spark
 */

export function renderGlyphSVG(kind = 'LIVE', tooltip = '') {
  const safeTip = String(tooltip || kind).replace(/"/g, '&quot;');
  let inner = '';
  switch (kind) {
    case 'LIVE':
      inner = `<circle cx="9" cy="9" r="4.5" fill="var(--accent)" />`;
      break;
    case 'CACHED':
      inner = `<circle cx="9" cy="9" r="4.5" fill="none" stroke="var(--accent)" stroke-width="1.6" />`;
      break;
    case 'SIMULATED':
      inner = `<polygon points="9,3.2 14.8,9 9,14.8 3.2,9" fill="none" stroke="var(--accent)" stroke-width="1.6" />`;
      break;
    case 'FALLBACK':
      inner = `<polygon points="9,3.5 14.8,14 3.2,14" fill="none" stroke="var(--accent)" stroke-width="1.6" stroke-linejoin="round" />`;
      break;
    case 'AI-GENERATED':
    default:
      inner = `<path d="M9 2.5 L10.7 7.3 L15.5 9 L10.7 10.7 L9 15.5 L7.3 10.7 L2.5 9 L7.3 7.3 Z" fill="var(--accent)" />`;
      break;
  }
  return `<span class="prov-glyph interactive" data-tooltip="${safeTip}" aria-label="${kind}"><svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">${inner}</svg></span>`;
}

export function renderConstraintIconSVG(kind = 'water', tooltip = '') {
  const safeTip = String(tooltip || kind).replace(/"/g, '&quot;');
  let path = '';
  if (kind === 'water') {
    path = `<path d="M9 2.8 C9 2.8 4.2 8.2 4.2 11.4 C4.2 14.1 6.3 16 9 16 C11.7 16 13.8 14.1 13.8 11.4 C13.8 8.2 9 2.8 9 2.8 Z" fill="none" stroke="var(--ink-2)" stroke-width="1.5"/>`;
  } else if (kind === 'temp') {
    path = `<path d="M9 3 V10.5 M9 14.2 A2.2 2.2 0 1 0 9 9.8 A2.2 2.2 0 1 0 9 14.2 Z" fill="none" stroke="var(--ink-2)" stroke-width="1.5" stroke-linecap="round"/>`;
  } else {
    path = `<path d="M3.5 6.5 H14.5 M5 10 H13 M6.8 13.5 H11.2" fill="none" stroke="var(--ink-2)" stroke-width="1.5" stroke-linecap="round"/>`;
  }
  return `<span class="prov-glyph interactive" data-tooltip="${safeTip}"><svg width="18" height="18" viewBox="0 0 18 18" aria-hidden="true">${path}</svg></span>`;
}

export function initGlobalTooltips() {
  const tipEl = document.getElementById('global-tooltip');
  if (!tipEl) return;

  document.addEventListener('mouseover', (e) => {
    const target = e.target.closest?.('[data-tooltip]');
    if (!target) return;
    const text = target.getAttribute('data-tooltip');
    if (!text) return;
    tipEl.textContent = text;
    tipEl.classList.add('visible');
  });

  document.addEventListener('mousemove', (e) => {
    if (!tipEl.classList.contains('visible')) return;
    const pad = 16;
    let x = e.clientX + pad;
    let y = e.clientY + pad;
    const rect = tipEl.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 12) {
      x = e.clientX - rect.width - pad;
    }
    if (y + rect.height > window.innerHeight - 12) {
      y = e.clientY - rect.height - pad;
    }
    tipEl.style.left = `${Math.max(12, x)}px`;
    tipEl.style.top = `${Math.max(12, y)}px`;
  });

  document.addEventListener('mouseout', (e) => {
    const target = e.target.closest?.('[data-tooltip]');
    if (!target) return;
    tipEl.classList.remove('visible');
  });
}
