/**
 * Q2 Chart 2: Seasonal Ensemble Range Bar (`seasonalRange.js`) — Orbital Agronomist (v5)
 * Renders the 1–3 month 50-member seasonal anomaly range (`p25` to `p75` IQR band + median
 * marker) around the `0%` baseline. Explicitly labels `"No clear signal"` when crossing zero,
 * or `"Unavailable"` with the fallback glyph if the endpoint failed.
 */

export function renderSeasonalRangeSVG(seasonal = {}) {
  const W = 500;
  const H = 96;
  const padL = 16;
  const padR = 16;
  const trackW = W - padL - padR;
  const trackY = 42;

  if (!seasonal || !seasonal.available) {
    return `
      <svg width="100%" height="96" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Seasonal ensemble unavailable">
        <rect x="${padL}" y="${trackY - 6}" width="${trackW}" height="12" rx="6" fill="rgba(255,255,255,0.06)" stroke="var(--line-strong)" stroke-dasharray="4 4" />
        <text x="${W / 2}" y="${trackY + 26}" text-anchor="middle" fill="var(--ink-2)" font-family="var(--font-mono)" font-size="14">Unavailable · 1–3m horizon INCONCLUSIVE</text>
      </svg>
    `;
  }

  // Scale -40% .. +40%
  const minPct = -40;
  const maxPct = 40;
  const xOf = (pct) => {
    const clamped = Math.max(minPct, Math.min(maxPct, Number(pct || 0)));
    return padL + ((clamped - minPct) / (maxPct - minPct)) * trackW;
  };

  const zeroX = xOf(0);
  const p25X = xOf(seasonal.p25_pct ?? -15);
  const p75X = xOf(seasonal.p75_pct ?? 10);
  const medX = xOf(seasonal.median_pct ?? -5);
  const bandW = Math.max(8, p75X - p25X);
  const medVal = Number(seasonal.median_pct ?? 0);

  return `
    <svg width="100%" height="96" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="1 to 3 month seasonal ensemble anomaly range">
      <!-- Background scale track -->
      <rect x="${padL}" y="${trackY - 5}" width="${trackW}" height="10" rx="5" fill="rgba(255,255,255,0.08)" />

      <!-- 0% Climatology Reference Tick -->
      <line x1="${zeroX.toFixed(1)}" y1="${trackY - 16}" x2="${zeroX.toFixed(1)}" y2="${trackY + 16}" stroke="var(--ink-2)" stroke-width="1.5" stroke-dasharray="3 3" />
      <text x="${zeroX.toFixed(1)}" y="${trackY - 20}" text-anchor="middle" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">0% norm</text>

      <!-- Interquartile (p25 to p75) Spread Band -->
      <rect
        x="${p25X.toFixed(1)}"
        y="${trackY - 7}"
        width="${bandW.toFixed(1)}"
        height="14"
        rx="7"
        fill="rgba(255, 180, 84, 0.28)"
        stroke="var(--accent)"
        stroke-width="1.2"
        style="transition: x 800ms cubic-bezier(0.22,1,0.36,1), width 800ms cubic-bezier(0.22,1,0.36,1);"
      />

      <!-- Median Marker -->
      <circle
        cx="${medX.toFixed(1)}"
        cy="${trackY}"
        r="6.5"
        fill="var(--accent)"
        style="transition: cx 800ms cubic-bezier(0.22,1,0.36,1);"
      />

      <!-- Scale Labels & Status -->
      <text x="${padL}" y="${H - 8}" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">-40% Drier</text>
      <text x="${W / 2}" y="${H - 8}" text-anchor="middle" fill="var(--accent)" font-family="var(--font-mono)" font-size="14" font-weight="500">Median ${medVal >= 0 ? '+' : ''}${medVal}% · ${seasonal.status || 'No clear signal'}</text>
      <text x="${W - padR}" y="${H - 8}" text-anchor="end" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">+40% Wetter</text>
    </svg>
  `;
}
