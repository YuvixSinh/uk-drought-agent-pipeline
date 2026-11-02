/**
 * The Analysis Wheel (760px SVG Choreography) — Orbital Agronomist (v5)
 * Centre hub (140px) with persistent globe orb + progress ring + mono coord + status word.
 * Outer ring (4 data sources) with inward particle streams.
 * Inner ring (3 sequential Gemini agents, 120 deg apart) with rotating dashed halo & hand-off arcs.
 */

import { state, notify } from '../state.js';

const CX = 380;
const CY = 380;
const R_HUB = 74;
const R_PROGRESS = 84;
const R_INNER = 190;
const R_OUTER = 308;

const OUTER_NODES = [
  { id: 'forecast', label: 'Forecast', angleDeg: -135, targetAgent: 'meteorologist' },
  { id: 'soil', label: 'Soil layers', angleDeg: -45, targetAgent: 'meteorologist' },
  { id: 'baseline', label: '10-year baseline', angleDeg: 45, targetAgent: 'hydrologist' },
  { id: 'seasonal', label: 'Seasonal ensemble', angleDeg: 135, targetAgent: 'hydrologist' },
];

const INNER_AGENTS = [
  { id: 'meteorologist', label: 'Meteorologist', role: 'Weather & Soil', angleDeg: -90 },
  { id: 'hydrologist', label: 'Hydrologist', role: 'Drought Horizons', angleDeg: 30 },
  { id: 'agronomist', label: 'Agronomist', role: 'UK Crop Fit', angleDeg: 150 },
];

function polarToXY(cx, cy, r, angleDeg) {
  const rad = (angleDeg * Math.PI) / 180;
  return {
    x: cx + r * Math.cos(rad),
    y: cy + r * Math.sin(rad),
  };
}

function describeArc(cx, cy, r, startDeg, endDeg) {
  const start = polarToXY(cx, cy, r, startDeg);
  const end = polarToXY(cx, cy, r, endDeg);
  const largeArcFlag = endDeg - startDeg <= 180 ? '0' : '1';
  return `M ${start.x.toFixed(1)} ${start.y.toFixed(1)} A ${r} ${r} 0 ${largeArcFlag} 1 ${end.x.toFixed(1)} ${end.y.toFixed(1)}`;
}

export function renderWheelSVG() {
  const w = state.wheel;
  const sel = state.selection;
  const isRunning = state.runState === 'RUNNING';
  const pct = Math.max(0, Math.min(100, Number(w.pct || 0)));
  const circum = 2 * Math.PI * R_PROGRESS;
  const dashOffset = circum * (1 - pct / 100);

  const ns = sel.lat >= 0 ? 'N' : 'S';
  const ew = sel.lon >= 0 ? 'E' : 'W';
  const coordStr = `${Math.abs(sel.lat).toFixed(2)}°${ns} ${Math.abs(sel.lon).toFixed(2)}°${ew}`;

  // Spokes from outer sources to centre & target agents
  const spokesSVG = OUTER_NODES.map((node) => {
    const pOut = polarToXY(CX, CY, R_OUTER, node.angleDeg);
    const pHub = polarToXY(CX, CY, R_PROGRESS + 6, node.angleDeg);
    const agInfo = INNER_AGENTS.find((a) => a.id === node.targetAgent);
    const pAg = polarToXY(CX, CY, R_INNER, agInfo.angleDeg);
    const sObj = w.sources[node.id] || { state: 'idle' };
    const isAct = sObj.state === 'fetching' || sObj.state === 'done' || sObj.state === 'cached';
    const strokeCol = isAct ? 'rgba(255, 180, 84, 0.36)' : 'rgba(255, 255, 255, 0.08)';
    const pathId = `spoke-${node.id}`;

    let particles = '';
    if (isAct && !state.lowQuality) {
      particles = `
        <circle r="3" fill="var(--accent)">
          <animateMotion dur="${sObj.state === 'fetching' ? '1.1s' : '2.4s'}" repeatCount="indefinite" path="M ${pOut.x} ${pOut.y} L ${pAg.x} ${pAg.y}" />
        </circle>
      `;
    }

    return `
      <g>
        <line x1="${pOut.x}" y1="${pOut.y}" x2="${pHub.x}" y2="${pHub.y}" stroke="rgba(255,255,255,0.07)" stroke-width="1" stroke-dasharray="3 4" />
        <line id="${pathId}" x1="${pOut.x}" y1="${pOut.y}" x2="${pAg.x}" y2="${pAg.y}" stroke="${strokeCol}" stroke-width="1.4" />
        ${particles}
      </g>
    `;
  }).join('');

  // Hand-off arcs between inner agents (-90 -> 30 -> 150)
  const arcMtoH = describeArc(CX, CY, R_INNER, -68, 8);
  const arcHtoA = describeArc(CX, CY, R_INNER, 52, 128);
  const mhActive = Boolean(w.handoffs.m_to_h);
  const haActive = Boolean(w.handoffs.h_to_a);

  const handoffsSVG = `
    <g>
      <path d="${arcMtoH}" fill="none" stroke="${mhActive ? 'var(--accent)' : 'rgba(255,255,255,0.10)'}" stroke-width="${mhActive ? '2.5' : '1.2'}" stroke-linecap="round" />
      ${mhActive && !state.lowQuality ? `<circle r="4" fill="var(--accent)"><animateMotion dur="1.8s" repeatCount="indefinite" path="${arcMtoH}" /></circle>` : ''}
      <path d="${arcHtoA}" fill="none" stroke="${haActive ? 'var(--accent)' : 'rgba(255,255,255,0.10)'}" stroke-width="${haActive ? '2.5' : '1.2'}" stroke-linecap="round" />
      ${haActive && !state.lowQuality ? `<circle r="4" fill="var(--accent)"><animateMotion dur="1.8s" repeatCount="indefinite" path="${arcHtoA}" /></circle>` : ''}
    </g>
  `;

  // Outer source nodes
  const outerNodesSVG = OUTER_NODES.map((node) => {
    const pt = polarToXY(CX, CY, R_OUTER, node.angleDeg);
    const sObj = w.sources[node.id] || { state: 'idle', summary: 'Waiting…' };
    const st = sObj.state;
    const isLit = st === 'done' || st === 'cached' || st === 'fetching';
    const isFailed = st === 'failed';
    const borderCol = isLit ? 'var(--accent)' : 'var(--line-strong)';
    const bgFill = st === 'fetching' ? 'rgba(255, 180, 84, 0.16)' : '#0A0E14';
    const badgeTxt = st === 'cached' ? 'CACHED' : st === 'done' ? 'LIVE' : st === 'fetching' ? 'FETCHING' : isFailed ? 'UNAVAILABLE' : 'IDLE';
    const tip = `${node.label} · ${badgeTxt} · ${sObj.summary || ''}`.replace(/"/g, '&quot;');

    return `
      <g class="wheel-node interactive" data-node-kind="source" data-node-id="${node.id}" data-tooltip="${tip}" transform="translate(${pt.x}, ${pt.y})" style="cursor:pointer;">
        <circle r="30" fill="${bgFill}" stroke="${borderCol}" stroke-width="${isLit ? '1.8' : '1.2'}" stroke-dasharray="${isFailed ? '4 3' : 'none'}" />
        ${st === 'fetching' ? `<circle r="35" fill="none" stroke="var(--accent)" stroke-width="1.2" stroke-dasharray="6 4"><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="3s" repeatCount="indefinite"/></circle>` : ''}
        <circle r="5" fill="${isLit ? 'var(--accent)' : 'rgba(244,246,250,0.35)'}" />
        <text y="48" text-anchor="middle" fill="var(--ink)" font-family="var(--font-sans)" font-size="15" font-weight="500">${node.label}</text>
        <text y="66" text-anchor="middle" fill="${isLit ? 'var(--accent)' : 'var(--ink-3)'}" font-family="var(--font-mono)" font-size="14">${badgeTxt}${sObj.latency_ms ? ` · ${sObj.latency_ms}ms` : ''}</text>
      </g>
    `;
  }).join('');

  // Inner sequential agent nodes
  const innerNodesSVG = INNER_AGENTS.map((ag) => {
    const pt = polarToXY(CX, CY, R_INNER, ag.angleDeg);
    const aObj = w.agents[ag.id] || { state: 'idle', model: 'gemini-3-flash-preview', mode: 'LIVE', summary: '' };
    const st = aObj.state;
    const isActive = st === 'active';
    const isDone = st === 'done' || st === 'fallback';
    const borderCol = isActive || isDone ? 'var(--accent)' : 'var(--line-strong)';
    const fillCol = isActive ? 'rgba(255, 180, 84, 0.18)' : isDone ? 'rgba(255, 180, 84, 0.08)' : '#0A0E14';
    const shortModel = String(aObj.model || 'gemini-3-flash').replace('-preview', '');
    const modeTag = aObj.mode === 'FALLBACK' ? 'FALLBACK' : aObj.mode === 'CACHED' ? 'CACHED' : 'LIVE';
    const tip = `${ag.label} (${aObj.model}) · ${modeTag} · ${aObj.summary || 'Click for agent details'}`.replace(/"/g, '&quot;');

    const labelY = ag.angleDeg === -90 ? -54 : 54;
    const subY = ag.angleDeg === -90 ? -38 : 72;

    return `
      <g class="wheel-node interactive" data-node-kind="agent" data-node-id="${ag.id}" data-tooltip="${tip}" transform="translate(${pt.x}, ${pt.y})" style="cursor:pointer;">
        ${isActive ? `<circle r="44" fill="none" stroke="var(--accent)" stroke-width="1.8" stroke-dasharray="7 5"><animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="4s" repeatCount="indefinite"/></circle>` : ''}
        <circle r="36" fill="${fillCol}" stroke="${borderCol}" stroke-width="${isActive || isDone ? '2' : '1.2'}" />
        <path d="M0 -8 L2.5 -2.5 L8 0 L2.5 2.5 L0 8 L-2.5 2.5 L-8 0 L-2.5 -2.5 Z" fill="${isActive || isDone ? 'var(--accent)' : 'var(--ink-3)'}" />
        <text y="${labelY}" text-anchor="middle" fill="var(--ink)" font-family="var(--font-sans)" font-size="16" font-weight="500">${ag.label}</text>
        <text y="${subY}" text-anchor="middle" fill="var(--ink-3)" font-family="var(--font-mono)" font-size="14">${shortModel}${aObj.mode === 'FALLBACK' ? ' · FALLBACK' : ''}</text>
      </g>
    `;
  }).join('');

  // Radar sweep while running
  const radarSVG = isRunning && !state.lowQuality
    ? `
      <g transform="translate(${CX}, ${CY})">
        <line x1="0" y1="0" x2="0" y2="-${R_OUTER}" stroke="rgba(255, 180, 84, 0.28)" stroke-width="1.5">
          <animateTransform attributeName="transform" type="rotate" from="0" to="360" dur="5.5s" repeatCount="indefinite" />
        </line>
      </g>
    `
    : '';

  return `
    <svg class="wheel-svg" viewBox="0 0 760 760" role="img" aria-label="Analysis Wheel">
      <!-- Outer & Inner Orbit Rings -->
      <circle cx="${CX}" cy="${CY}" r="${R_OUTER}" fill="none" stroke="var(--line)" stroke-width="1" />
      <circle cx="${CX}" cy="${CY}" r="${R_INNER}" fill="none" stroke="var(--line)" stroke-width="1" stroke-dasharray="4 6" />

      ${radarSVG}
      ${spokesSVG}
      ${handoffsSVG}

      <!-- Centre Hub Frame & Progress Ring -->
      <circle cx="${CX}" cy="${CY}" r="${R_HUB}" fill="rgba(5, 7, 11, 0.38)" stroke="var(--line-strong)" stroke-width="1.2" />
      <circle cx="${CX}" cy="${CY}" r="${R_PROGRESS}" fill="none" stroke="rgba(255,255,255,0.08)" stroke-width="3" />
      <circle
        cx="${CX}"
        cy="${CY}"
        r="${R_PROGRESS}"
        fill="none"
        stroke="var(--accent)"
        stroke-width="3"
        stroke-linecap="round"
        stroke-dasharray="${circum.toFixed(1)}"
        stroke-dashoffset="${dashOffset.toFixed(1)}"
        transform="rotate(-90 ${CX} ${CY})"
        style="transition: stroke-dashoffset 320ms ease;"
      />

      <!-- Centre Coordinate & Single Status Word -->
      <text x="${CX}" y="${CY - 96}" text-anchor="middle" fill="var(--ink-2)" font-family="var(--font-mono)" font-size="14">${coordStr}</text>
      <text x="${CX}" y="${CY + 112}" text-anchor="middle" fill="var(--accent)" font-family="var(--font-sans)" font-size="18" font-weight="500" letter-spacing="0.04em">${w.word || 'Done'}</text>

      ${outerNodesSVG}
      ${innerNodesSVG}
    </svg>
  `;
}

export function bindWheelNodeClicks(container) {
  if (!container) return;
  container.querySelectorAll('.wheel-node').forEach((nodeEl) => {
    nodeEl.addEventListener('click', () => {
      const kind = nodeEl.getAttribute('data-node-kind');
      const id = nodeEl.getAttribute('data-node-id');
      state.drawerOpen = true;
      state.drawerTab = kind === 'agent' ? 'Agents' : 'Sources';
      state.drawerFocusId = id;
      notify('drawer');
    });
  });
}
