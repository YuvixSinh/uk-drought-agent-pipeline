/**
 * Three-Segment SVG Arc Gauges — Orbital Agronomist (v5)
 * Encodes LOW / WATCH / ELEVATED / INCONCLUSIVE by arc position, stroke weight,
 * and needle angle using strictly `--accent` (#FFB454) and `--ink` shades.
 */

import { renderGlyphSVG } from '../glyphs.js';

function riskToAngleAndSeg(riskWord) {
  switch (String(riskWord || 'WATCH').toUpperCase()) {
    case 'LOW':
      return { angleDeg: -52, activeSeg: 1 };
    case 'ELEVATED':
      return { angleDeg: 52, activeSeg: 3 };
    case 'INCONCLUSIVE':
    case 'UNAVAILABLE':
      return { angleDeg: 0, activeSeg: 0 };
    case 'WATCH':
    default:
      return { angleDeg: 0, activeSeg: 2 };
  }
}

export function renderSingleGaugeSVG(riskWord, label, glyphKind = 'LIVE', tooltip = '') {
  const { angleDeg, activeSeg } = riskToAngleAndSeg(riskWord);
  const isUncertain = activeSeg === 0;

  // Semi-circle arc from (-64, 72) to (64, 72) centred at (82, 74), r = 56
  // Segment 1 (LOW): left third; Segment 2 (WATCH): middle third; Segment 3 (ELEVATED): right third
  const seg1Stroke = activeSeg === 1 ? 'var(--accent)' : 'rgba(255,255,255,0.16)';
  const seg2Stroke = activeSeg === 2 ? 'var(--accent)' : 'rgba(255,255,255,0.22)';
  const seg3Stroke = activeSeg === 3 ? 'var(--accent)' : 'rgba(255,255,255,0.16)';

  return `
    <div style="display:flex;flex-direction:column;align-items:center;gap:2px;" data-tooltip="${String(tooltip).replace(/"/g, '&quot;')}">
      <svg width="164" height="106" viewBox="0 0 164 106" role="img" aria-label="${label}: ${riskWord}">
        <!-- Segment 1: LOW (-165 deg to -118 deg) -->
        <path d="M 27.9 59.5 A 56 56 0 0 1 55.7 24.5" fill="none" stroke="${seg1Stroke}" stroke-width="${activeSeg === 1 ? '7' : '4.5'}" stroke-linecap="round" />
        <!-- Segment 2: WATCH (-112 deg to -68 deg) -->
        <path d="M 61.0 22.1 A 56 56 0 0 1 103.0 22.1" fill="none" stroke="${seg2Stroke}" stroke-width="${activeSeg === 2 ? '7' : '4.5'}" stroke-linecap="round" />
        <!-- Segment 3: ELEVATED (-62 deg to -15 deg) -->
        <path d="M 108.3 24.5 A 56 56 0 0 1 136.1 59.5" fill="none" stroke="${seg3Stroke}" stroke-width="${activeSeg === 3 ? '7' : '4.5'}" stroke-linecap="round" />

        <!-- Needle -->
        ${
          isUncertain
            ? `<circle cx="82" cy="72" r="5" fill="none" stroke="var(--accent)" stroke-width="2" stroke-dasharray="2 2" />`
            : `
              <g transform="translate(82, 72) rotate(${angleDeg})" style="transition: transform 800ms cubic-bezier(0.22, 1, 0.36, 1);">
                <line x1="0" y1="0" x2="0" y2="-44" stroke="var(--accent)" stroke-width="2.5" stroke-linecap="round" />
                <circle cx="0" cy="0" r="4.5" fill="var(--accent)" />
              </g>
            `
        }

        <text x="82" y="96" text-anchor="middle" fill="var(--ink)" font-family="var(--font-mono)" font-size="15" font-weight="500">${riskWord}</text>
      </svg>
      <div style="display:flex;align-items:center;gap:6px;">
        <span class="micro-label">${label}</span>
        ${renderGlyphSVG(glyphKind, tooltip)}
      </div>
    </div>
  `;
}

export function renderDualHorizonGaugesSVG(q2) {
  const g1 = renderCompactGauge(q2.chip_7_15, '7–15 DAYS', q2.glyph_7_15, q2.tooltip_7_15);
  const g2 = renderCompactGauge(q2.chip_1_3m, '1–3 MONTHS', q2.glyph_1_3m, q2.tooltip_1_3m);
  return `
    <div style="display:flex;flex-direction:column;gap:8px;width:100%;">
      ${g1}
      ${g2}
    </div>
  `;
}

function renderCompactGauge(riskWord, horizonLabel, glyphKind, tooltip) {
  const { activeSeg } = riskToAngleAndSeg(riskWord);
  const fillPct = activeSeg === 1 ? 33 : activeSeg === 2 ? 66 : activeSeg === 3 ? 100 : 20;
  const isUncertain = activeSeg === 0;

  return `
    <div style="background:rgba(5,7,11,0.55);border:1px solid var(--line);border-radius:10px;padding:7px 10px;display:flex;flex-direction:column;gap:5px;" data-tooltip="${String(tooltip || '').replace(/"/g, '&quot;')}">
      <div style="display:flex;align-items:center;justify-content:space-between;">
        <span class="micro-label">${horizonLabel}</span>
        <div style="display:flex;align-items:center;gap:5px;">
          <span class="mono" style="font-size:14px;font-weight:500;color:var(--accent);">${riskWord}</span>
          ${renderGlyphSVG(glyphKind, tooltip)}
        </div>
      </div>
      <svg width="160" height="10" viewBox="0 0 160 10" style="width:100%;height:10px;">
        <rect x="0" y="2" width="50" height="6" rx="3" fill="${activeSeg >= 1 ? 'var(--accent)' : 'rgba(255,255,255,0.12)'}" opacity="${activeSeg === 1 ? '1' : activeSeg > 1 ? '0.45' : '1'}" />
        <rect x="55" y="2" width="50" height="6" rx="3" fill="${activeSeg >= 2 ? 'var(--accent)' : 'rgba(255,255,255,0.12)'}" opacity="${activeSeg === 2 ? '1' : activeSeg > 2 ? '0.65' : '1'}" />
        <rect x="110" y="2" width="50" height="6" rx="3" fill="${activeSeg === 3 ? 'var(--accent)' : 'rgba(255,255,255,0.12)'}" stroke="${isUncertain ? 'var(--accent)' : 'none'}" stroke-dasharray="${isUncertain ? '3 2' : 'none'}" />
      </svg>
    </div>
  `;
}
