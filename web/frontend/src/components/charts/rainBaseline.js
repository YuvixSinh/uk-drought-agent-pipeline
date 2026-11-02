/**
 * Q1 Chart 1: 10-Year Baseline Bar Strip (`rainBaseline.js`) — Orbital Agronomist (v5)
 * Renders 10 slim vertical bars (2016–2025) in `--ink-4` + `Now` bar highlighted
 * in `--accent` (#FFB454) + dashed 10-year mean reference line.
 */

export function renderRainBaselineSVG(baselineYears = [], mean30dMm = 58.0) {
  const bars = baselineYears.length
    ? baselineYears
    : [
        { year: '2016', rain_mm: 52, is_current: false },
        { year: 'Now', rain_mm: 46, is_current: true },
      ];

  const W = 500;
  const H = 108;
  const padL = 8;
  const padR = 46;
  const padT = 14;
  const padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const maxVal = Math.max(mean30dMm * 1.35, ...bars.map((b) => Number(b.rain_mm || 0)), 40);
  const stepX = plotW / Math.max(1, bars.length);
  const barW = Math.min(24, stepX * 0.62);

  const meanY = padT + plotH - (mean30dMm / maxVal) * plotH;

  const barsRects = bars.map((b, i) => {
    const val = Number(b.rain_mm || 0);
    const bh = Math.max(4, (val / maxVal) * plotH);
    const x = padL + i * stepX + (stepX - barW) / 2;
    const y = padT + plotH - bh;
    const isNow = Boolean(b.is_current);
    const fill = isNow ? 'var(--accent)' : 'rgba(244, 246, 250, 0.28)';
    const yrShort = isNow ? 'Now' : `'${String(b.year).slice(-2)}`;
    const tip = `${b.year}: ${val.toFixed(1)} mm (10y mean ${mean30dMm.toFixed(1)} mm)`;

    return `
      <g class="interactive" data-tooltip="${tip}">
        <rect
          x="${x.toFixed(1)}"
          y="${y.toFixed(1)}"
          width="${barW.toFixed(1)}"
          height="${bh.toFixed(1)}"
          rx="3"
          fill="${fill}"
          style="transition: y 800ms cubic-bezier(0.22,1,0.36,1), height 800ms cubic-bezier(0.22,1,0.36,1);"
        />
        <text
          x="${(x + barW / 2).toFixed(1)}"
          y="${H - 5}"
          text-anchor="middle"
          fill="${isNow ? 'var(--accent)' : 'var(--ink-3)'}"
          font-family="var(--font-mono)"
          font-size="14"
          font-weight="${isNow ? '500' : '400'}"
        >${yrShort}</text>
      </g>
    `;
  }).join('');

  return `
    <svg width="100%" height="108" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="30-day rainfall vs 10-year baseline">
      <!-- 10-year mean dashed line -->
      <line x1="${padL}" y1="${meanY.toFixed(1)}" x2="${W - padR}" y2="${meanY.toFixed(1)}" stroke="var(--ink-2)" stroke-width="1.2" stroke-dasharray="4 4" />
      <text x="${W - padR + 5}" y="${(meanY + 4).toFixed(1)}" fill="var(--ink-2)" font-family="var(--font-mono)" font-size="14">${mean30dMm.toFixed(0)}mm</text>
      ${barsRects}
    </svg>
  `;
}
