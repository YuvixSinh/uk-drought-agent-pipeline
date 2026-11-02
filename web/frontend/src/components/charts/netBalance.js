/**
 * Q2 Chart 1: 15-Day Cumulative Water Balance (`netBalance.js`) — Orbital Agronomist (v5)
 * Renders cumulative `Rain - ET₀` line in `--accent`, zero baseline, diagonal hatch
 * fill where cumulative balance is below zero, faint daily bars, and ghost baseline in Scenario mode.
 */

export function renderNetBalanceSVG(series = [], isScenario = false) {
  const pts = series.length
    ? series
    : [
        { date: 'D+1', rain_mm: 0, et0_mm: 1.2, cum_net_mm: -1.2, baseline_cum_net_mm: -1.2 },
        { date: 'D+15', rain_mm: 2.0, et0_mm: 1.1, cum_net_mm: 3.2, baseline_cum_net_mm: 3.2 },
      ];

  const W = 500;
  const H = 108;
  const padL = 10;
  const padR = 54;
  const padT = 14;
  const padB = 22;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  const allVals = pts.flatMap((p) => [
    Number(p.cum_net_mm || 0),
    Number(p.baseline_cum_net_mm ?? p.cum_net_mm ?? 0),
    0,
  ]);
  const minV = Math.min(-8, ...allVals);
  const maxV = Math.max(8, ...allVals);
  const span = Math.max(1, maxV - minV);

  const xOf = (i) => padL + (i / Math.max(1, pts.length - 1)) * plotW;
  const yOf = (v) => padT + plotH - ((v - minV) / span) * plotH;
  const zeroY = yOf(0);

  const lineCoords = pts.map((p, i) => `${xOf(i).toFixed(1)},${yOf(Number(p.cum_net_mm || 0)).toFixed(1)}`);
  const polylinePts = lineCoords.join(' ');

  // Polygon closed to zeroY for diagonal hatch clip below zero
  const areaPts = [
    `${xOf(0).toFixed(1)},${zeroY.toFixed(1)}`,
    ...lineCoords,
    `${xOf(pts.length - 1).toFixed(1)},${zeroY.toFixed(1)}`,
  ].join(' ');

  let ghostPolyline = '';
  if (isScenario) {
    const ghostCoords = pts.map((p, i) =>
      `${xOf(i).toFixed(1)},${yOf(Number(p.baseline_cum_net_mm ?? p.cum_net_mm ?? 0)).toFixed(1)}`
    );
    ghostPolyline = `<polyline points="${ghostCoords.join(' ')}" fill="none" stroke="rgba(244,246,250,0.42)" stroke-width="1.5" stroke-dasharray="4 4" />`;
  }

  // Faint daily rain ticks along bottom
  const dailyTicks = pts.map((p, i) => {
    const r = Number(p.rain_mm || 0);
    const h = Math.min(18, r * 2.2);
    const x = xOf(i) - 3;
    return h > 0.5
      ? `<rect x="${x.toFixed(1)}" y="${(H - padB - h).toFixed(1)}" width="6" height="${h.toFixed(1)}" rx="1.5" fill="rgba(244,246,250,0.18)" />`
      : '';
  }).join('');

  const lastVal = Number(pts[pts.length - 1]?.cum_net_mm || 0);
  const lastY = yOf(lastVal);

  return `
    <svg width="100%" height="108" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="15-day cumulative net water balance">
      <defs>
        <pattern id="deficit-hatch" width="8" height="8" patternTransform="rotate(45 0 0)" patternUnits="userSpaceOnUse">
          <line x1="0" y1="0" x2="0" y2="8" stroke="rgba(255, 180, 84, 0.28)" stroke-width="2" />
        </pattern>
        <clipPath id="below-zero-clip">
          <rect x="${padL}" y="${zeroY.toFixed(1)}" width="${plotW}" height="${Math.max(0, H - zeroY).toFixed(1)}" />
        </clipPath>
      </defs>

      <!-- Zero baseline -->
      <line x1="${padL}" y1="${zeroY.toFixed(1)}" x2="${W - padR}" y2="${zeroY.toFixed(1)}" stroke="var(--line-strong)" stroke-width="1.2" stroke-dasharray="3 3" />
      <text x="${W - padR + 6}" y="${(zeroY + 4).toFixed(1)}" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">0mm</text>

      ${dailyTicks}

      <!-- Hatched deficit area below 0 mm -->
      <polygon points="${areaPts}" fill="url(#deficit-hatch)" clip-path="url(#below-zero-clip)" />

      ${ghostPolyline}

      <!-- Main cumulative net P - ET0 curve -->
      <polyline points="${polylinePts}" fill="none" stroke="var(--accent)" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" />
      <circle cx="${xOf(pts.length - 1).toFixed(1)}" cy="${lastY.toFixed(1)}" r="4" fill="var(--accent)" />
      <text x="${W - padR + 6}" y="${Math.max(14, Math.min(H - 8, lastY + 4)).toFixed(1)}" fill="var(--accent)" font-family="var(--font-mono)" font-size="14" font-weight="500">${lastVal >= 0 ? '+' : ''}${lastVal.toFixed(1)}</text>

      <text x="${padL}" y="${H - 4}" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">Day +1</text>
      <text x="${W - padR}" y="${H - 4}" text-anchor="end" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">Day +15</text>
    </svg>
  `;
}
