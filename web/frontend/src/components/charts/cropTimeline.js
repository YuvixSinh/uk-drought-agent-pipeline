/**
 * Q3 Visuals: UK Crop Tiles with Oct–Apr Timeline Bar (`cropTimeline.js`) — Orbital Agronomist (v5)
 * Renders 3 candidate UK crop tiles. Each tile shows:
 * - Crop name + provenance glyph
 * - 3 confidence dots (`● ● ○`)
 * - 3 SVG constraint icons (`water`, `temp`, `drainage`) with hover tooltips
 * - 7-month `Oct–Apr` timeline bar highlighting the sowing/establishment window in `--accent`.
 */

import { renderGlyphSVG, renderConstraintIconSVG } from '../glyphs.js';

const MONTHS = ['Oct', 'Nov', 'Dec', 'Jan', 'Feb', 'Mar', 'Apr'];

function renderConfidenceDots(count = 3, word = '') {
  const dots = [1, 2, 3]
    .map(
      (i) =>
        `<span style="display:inline-block;width:7px;height:7px;border-radius:50%;background:${
          i <= count ? 'var(--accent)' : 'rgba(255,255,255,0.18)'
        };"></span>`
    )
    .join('');
  return `<span class="interactive" data-tooltip="Regional weather confidence: ${word} (${count}/3)" style="display:inline-flex;align-items:center;gap:4px;">${dots}</span>`;
}

function renderTimelineSVG(startIdx = 0, endIdx = 1, windowLabel = 'Oct–Nov') {
  const W = 440;
  const H = 30;
  const segW = W / MONTHS.length;

  const cells = MONTHS.map((m, i) => {
    const x = i * segW;
    const isActive = i >= startIdx && i <= endIdx;
    return `
      <g>
        <rect
          x="${(x + 2).toFixed(1)}"
          y="2"
          width="${(segW - 4).toFixed(1)}"
          height="10"
          rx="3"
          fill="${isActive ? 'var(--accent)' : 'rgba(255,255,255,0.10)'}"
          opacity="${isActive ? '0.92' : '1'}"
        />
        <text
          x="${(x + segW / 2).toFixed(1)}"
          y="27"
          text-anchor="middle"
          fill="${isActive ? 'var(--ink)' : 'var(--ink-3)'}"
          font-family="var(--font-mono)"
          font-size="14"
        >${m}</text>
      </g>
    `;
  }).join('');

  return `
    <svg width="100%" height="30" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Sowing window ${windowLabel}">
      ${cells}
    </svg>
  `;
}

export function renderCropTilesHTML(crops = []) {
  return (crops || [])
    .slice(0, 3)
    .map((c) => {
      const iconsHTML = (c.constraints || [])
        .map((ci) => renderConstraintIconSVG(ci.kind, `${ci.label}: ${ci.tooltip}`))
        .join('');
      const tip = `${c.provenance} · ${c.name}: ${c.why} Watch-out: ${c.watch}`;
      return `
        <div class="crop-tile interactive" data-crop-id="${c.id}" data-tooltip="${String(tip).replace(/"/g, '&quot;')}">
          <div class="crop-tile-top">
            <div style="display:flex;align-items:center;gap:8px;">
              <span class="crop-name">${c.name}</span>
              ${renderGlyphSVG(c.glyph || 'FALLBACK', `${c.provenance} · Rule-table regional candidate`)}
            </div>
            <div class="crop-meta-right">
              ${renderConfidenceDots(c.confidence_dots, c.confidence_word)}
              <div style="display:flex;align-items:center;gap:4px;">${iconsHTML}</div>
            </div>
          </div>
          ${renderTimelineSVG(c.start_month_idx ?? 0, c.end_month_idx ?? 1, c.window_label)}
        </div>
      `;
    })
    .join('');
}
