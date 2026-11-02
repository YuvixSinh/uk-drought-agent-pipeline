/**
 * Q1 Chart 2: Three-Layer Soil Moisture Profile (`soilProfile.js`) — Orbital Agronomist (v5)
 * Renders 3 horizontal depth bars (0–7 cm, 7–28 cm, 28–100 cm) with volumetric moisture
 * (`m³/m³`) fill in `--accent` and dashed baseline ghost markers in Scenario mode.
 */

export function renderSoilProfileSVG(soilLayers = [], isScenario = false) {
  const W = 500;
  const H = 108;
  const maxSM = 0.45; // volumetric saturation scale 0.00 .. 0.45 m3/m3
  const barX = 96;
  const barMaxW = 310;

  const rows = (soilLayers || []).slice(0, 3).map((layer, idx) => {
    const y = 12 + idx * 32;
    const val = Number(layer.moisture_m3m3 ?? 0.24);
    const baseVal = Number(layer.baseline_m3m3 ?? val);
    const wFill = Math.max(8, Math.min(barMaxW, (val / maxSM) * barMaxW));
    const xGhost = barX + Math.max(8, Math.min(barMaxW, (baseVal / maxSM) * barMaxW));
    const tip = layer.tooltip || `${layer.depth_label}: ${val.toFixed(2)} m³/m³`;

    return `
      <g class="interactive" data-tooltip="${String(tip).replace(/"/g, '&quot;')}">
        <text x="4" y="${y + 15}" fill="var(--ink-2)" font-family="var(--font-mono)" font-size="14">${layer.depth_label}</text>
        <rect x="${barX}" y="${y + 2}" width="${barMaxW}" height="16" rx="4" fill="rgba(255,255,255,0.08)" />
        <rect
          x="${barX}"
          y="${y + 2}"
          width="${wFill.toFixed(1)}"
          height="16"
          rx="4"
          fill="var(--accent)"
          opacity="${0.65 + idx * 0.15}"
          style="transition: width 800ms cubic-bezier(0.22,1,0.36,1);"
        />
        ${
          isScenario && Math.abs(baseVal - val) > 0.005
            ? `<line x1="${xGhost.toFixed(1)}" y1="${y}" x2="${xGhost.toFixed(1)}" y2="${y + 20}" stroke="var(--ink)" stroke-width="2" stroke-dasharray="2 2" />`
            : ''
        }
        <text x="${barX + barMaxW + 10}" y="${y + 15}" fill="var(--ink)" font-family="var(--font-mono)" font-size="14" font-weight="500">${val.toFixed(2)} m³/m³</text>
      </g>
    `;
  }).join('');

  return `
    <svg width="100%" height="108" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Three-layer volumetric soil moisture profile">
      ${rows}
    </svg>
  `;
}
