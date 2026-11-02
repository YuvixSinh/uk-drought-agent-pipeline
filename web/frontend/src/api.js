/**
 * REST API Client — Orbital Agronomist (v5)
 * Communicates with the same-origin FastAPI server (`http://127.0.0.1:8000`).
 */

export async function apiValidatePoint(lat, lon) {
  const resp = await fetch('/api/validate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ lat: Number(lat), lon: Number(lon) }),
  });
  if (!resp.ok) {
    throw new Error(`Validate failed: ${resp.status}`);
  }
  return resp.json();
}

export async function apiStartRun(lat, lon, forceModelFail = false) {
  const resp = await fetch('/api/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      lat: Number(lat),
      lon: Number(lon),
      force_model_fail: Boolean(forceModelFail),
    }),
  });
  if (!resp.ok) {
    const errObj = await resp.json().catch(() => ({ detail: 'Run start failed' }));
    throw new Error(errObj.detail || `HTTP ${resp.status}`);
  }
  return resp.json();
}

export async function apiGetResult(runId) {
  const resp = await fetch(`/api/run/${encodeURIComponent(runId)}/result`);
  if (!resp.ok) {
    throw new Error(`Result fetch failed: ${resp.status}`);
  }
  return resp.json();
}

export async function apiCancelRun(runId) {
  if (!runId || String(runId).startsWith('demo-')) {
    return { run_id: runId, cancelled: true, status: 'CANCELLED' };
  }
  const resp = await fetch(`/api/run/${encodeURIComponent(runId)}/cancel`, {
    method: 'POST',
  });
  return resp.json();
}

export async function apiToggleScenario(runId, scenarioActive) {
  const resp = await fetch(`/api/run/${encodeURIComponent(runId)}/scenario`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ scenario: scenarioActive ? 'dry30' : 'none' }),
  });
  if (!resp.ok) {
    throw new Error(`Scenario toggle failed: ${resp.status}`);
  }
  return resp.json();
}

export async function apiGetDemo(cityName) {
  const resp = await fetch(`/api/demo/${encodeURIComponent(cityName)}`);
  if (!resp.ok) {
    throw new Error(`Demo fetch failed: ${resp.status}`);
  }
  return resp.json();
}

export function getDossierDownloadUrl(runId, scenarioActive = false) {
  const safeId = encodeURIComponent(runId || 'demo-cambridge');
  return `/api/run/${safeId}/dossier.txt?scenario=${scenarioActive ? 'true' : 'false'}`;
}
