/**
 * Persistent 3D Dot-Matrix Globe (`globe.gl`) — Orbital Agronomist (v5)
 * Renders a dark obsidian sphere (`#05070B`) with hex-dot landmasses,
 * crisp `--accent` (`#FFB454`) UK border, 5 city beacons, selection light beam,
 * pulse ring, 2-second frame-time monitor (`lowQuality` fallback), and 2D Canvas fallback.
 */

import { state, CITY_SHORTCUTS, notify } from '../state.js';

let globeInstance = null;

export async function initPersistentGlobe(onCoordinateClick) {
  const mount = document.getElementById('globe-mount');
  if (!mount) return;

  try {
    const [worldResp, ukResp] = await Promise.all([
      fetch('/vendor/world_110m.geojson'),
      fetch('/vendor/uk_10m.geojson'),
    ]);
    const worldGeo = await worldResp.json();
    const ukGeo = await ukResp.json();

    if (typeof window.Globe !== 'function') {
      throw new Error('Globe.gl vendor library not loaded');
    }

    const g = window.Globe()(mount)
      .width(window.innerWidth)
      .height(window.innerHeight)
      .backgroundColor('rgba(0,0,0,0)')
      .showGlobe(true)
      .showAtmosphere(true)
      .atmosphereColor('#FFB454')
      .atmosphereAltitude(0.11)
      .hexPolygonsData(worldGeo.features || [])
      .hexPolygonResolution(3)
      .hexPolygonMargin(0.38)
      .hexPolygonColor(() => 'rgba(244, 246, 250, 0.24)')
      .polygonsData(ukGeo.features || [])
      .polygonCapColor(() => 'rgba(255, 180, 84, 0.16)')
      .polygonSideColor(() => 'rgba(255, 180, 84, 0.08)')
      .polygonStrokeColor(() => '#FFB454')
      .polygonAltitude(0.008)
      .onGlobeClick(({ lat, lng }) => {
        if (state.route === 'place' && onCoordinateClick) {
          onCoordinateClick(lat, lng);
        }
      })
      .onPolygonClick((poly, event, { lat, lng }) => {
        if (state.route === 'place' && onCoordinateClick) {
          onCoordinateClick(lat, lng);
        }
      })
      .onHexPolygonClick((hex, event, { lat, lng }) => {
        if (state.route === 'place' && onCoordinateClick) {
          onCoordinateClick(lat, lng);
        }
      });

    // Dark obsidian sphere material
    try {
      const mat = g.globeMaterial();
      if (mat && mat.color) {
        mat.color.set('#070A10');
      }
    } catch (_) {}

    // Camera focused on UK
    g.pointOfView({ lat: 54.3, lng: -2.2, altitude: 0.72 }, 0);

    // Controls configuration
    try {
      const controls = g.controls();
      if (controls) {
        controls.enableDamping = true;
        controls.dampingFactor = 0.08;
        controls.minDistance = 125;
        controls.maxDistance = 380;
      }
    } catch (_) {}

    globeInstance = g;
    updateGlobeMarkers();

    window.addEventListener('resize', () => {
      if (globeInstance) {
        globeInstance.width(window.innerWidth).height(window.innerHeight);
      }
    });

    // 2-second frame-time monitor per Section 5
    monitorFrameRate(g);
  } catch (err) {
    console.warn('WebGL Globe fallback activated:', err);
    render2DCanvasFallback(mount, onCoordinateClick);
  }
}

export function updateGlobeMarkers() {
  if (!globeInstance) return;

  const sel = state.selection;
  const pts = CITY_SHORTCUTS.map((c) => ({
    lat: c.lat,
    lng: c.lon,
    name: c.name,
    isSelected: sel.valid && Math.hypot(sel.lat - c.lat, sel.lon - c.lon) < 0.15,
    isPin: false,
  }));

  if (sel && sel.valid) {
    pts.push({
      lat: sel.lat,
      lng: sel.lon,
      name: 'Selected Point',
      isSelected: true,
      isPin: true,
    });
  }

  globeInstance
    .pointsData(pts)
    .pointLat('lat')
    .pointLng('lng')
    .pointColor(() => '#FFB454')
    .pointAltitude((d) => (d.isPin ? 0.045 : 0.014))
    .pointRadius((d) => (d.isPin ? 0.28 : 0.20))
    .onPointClick((pt) => {
      if (state.route === 'place') {
        const evt = new CustomEvent('globe-city-select', { detail: { lat: pt.lat, lon: pt.lng } });
        window.dispatchEvent(evt);
      }
    });

  if (sel && sel.valid) {
    globeInstance
      .ringsData([{ lat: sel.lat, lng: sel.lon }])
      .ringLat('lat')
      .ringLng('lng')
      .ringColor(() => () => '#FFB454')
      .ringMaxRadius(2.4)
      .ringPropagationSpeed(1.5)
      .ringRepeatPeriod(950);
  } else {
    globeInstance.ringsData([]);
  }
}

export function focusGlobeOn(lat, lon, altitude = 0.66, durationMs = 650) {
  if (!globeInstance) return;
  try {
    globeInstance.pointOfView({ lat: Number(lat), lng: Number(lon), altitude }, durationMs);
  } catch (_) {}
}

function monitorFrameRate(g) {
  let frames = 0;
  const t0 = performance.now();
  function tick() {
    frames += 1;
    const elapsed = performance.now() - t0;
    if (elapsed < 2000) {
      requestAnimationFrame(tick);
    } else {
      const avgFrameMs = elapsed / Math.max(1, frames);
      if (avgFrameMs > 25 && !state.lowQuality) {
        state.lowQuality = true;
        try {
          g.hexPolygonResolution(2);
        } catch (_) {}
        notify('quality');
      }
    }
  }
  requestAnimationFrame(tick);
}

function render2DCanvasFallback(mount, onCoordinateClick) {
  mount.innerHTML = `<canvas id="fallback-globe-canvas" width="${window.innerWidth}" height="${window.innerHeight}" style="width:100%;height:100%;cursor:crosshair;"></canvas>`;
  const canvas = mount.querySelector('#fallback-globe-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const cx = canvas.width * 0.54;
  const cy = canvas.height * 0.50;
  const r = Math.min(canvas.width, canvas.height) * 0.36;

  ctx.fillStyle = '#070A10';
  ctx.beginPath();
  ctx.arc(cx, cy, r, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = 'rgba(255, 180, 84, 0.35)';
  ctx.lineWidth = 2;
  ctx.stroke();

  canvas.addEventListener('click', (e) => {
    if (state.route !== 'place' || !onCoordinateClick) return;
    const rect = canvas.getBoundingClientRect();
    const dx = (e.clientX - rect.left - cx) / r;
    const dy = (e.clientY - rect.top - cy) / r;
    const lat = 54.0 - dy * 6.0;
    const lon = -2.0 + dx * 6.0;
    onCoordinateClick(lat, lon);
  });
}
