/**
 * Server-Sent Events (SSE) & Choreographed Wheel Streamer — Orbital Agronomist (v5)
 * Connects to `/api/run/{run_id}/events` for live runs, or runs the fast
 * cached choreography when Demo mode (`D`) or Replay is triggered.
 */

import { state, notify } from './state.js';
import { apiGetResult } from './api.js';
import { navigateTo } from './router.js';

let activeEventSource = null;
let demoTimers = [];

export function closeActiveStream() {
  if (activeEventSource) {
    try {
      activeEventSource.close();
    } catch (_) {}
    activeEventSource = null;
  }
  for (const t of demoTimers) {
    clearTimeout(t);
  }
  demoTimers = [];
}

export function resetWheelForNewRun() {
  state.wheel = {
    pct: 4,
    word: 'Gathering',
    ticker: 'Initialising UK water-balance pipeline',
    sources: {
      forecast: { state: 'idle', latency_ms: 0, summary: 'Waiting…' },
      soil: { state: 'idle', latency_ms: 0, summary: 'Waiting…' },
      baseline: { state: 'idle', latency_ms: 0, summary: 'Waiting…' },
      seasonal: { state: 'idle', latency_ms: 0, summary: 'Waiting…' },
    },
    agents: {
      meteorologist: { state: 'idle', model: 'gemini-3-flash-preview', mode: 'LIVE', summary: 'Waiting for weather & soil…', streamText: '' },
      hydrologist: { state: 'idle', model: 'gemini-3-flash-preview', mode: 'LIVE', summary: 'Waiting for Meteorologist…', streamText: '' },
      agronomist: { state: 'idle', model: 'gemini-3-flash-preview', mode: 'LIVE', summary: 'Waiting for Hydrologist…', streamText: '' },
    },
    handoffs: {
      m_to_h: false,
      h_to_a: false,
    },
  };
}

export function connectLiveRunStream(runId) {
  closeActiveStream();
  resetWheelForNewRun();
  state.runId = runId;
  state.runState = 'RUNNING';
  if (state.result) {
    state.result.feed = [];
  }
  notify('wheel');

  const es = new EventSource(`/api/run/${encodeURIComponent(runId)}/events`);
  activeEventSource = es;

  const pushFeed = (source, type, text, ts) => {
    if (!state.result) return;
    if (!Array.isArray(state.result.feed)) state.result.feed = [];
    state.result.feed.push({
      ts: ts || new Date().toISOString().slice(11, 23),
      source,
      type,
      text,
    });
  };

  es.addEventListener('progress', (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    state.wheel.pct = d.pct ?? state.wheel.pct;
    state.wheel.word = d.word || state.wheel.word;
    state.wheel.ticker = d.ticker || state.wheel.ticker;
    notify('wheel');
  });

  es.addEventListener('source', (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    if (d.id && state.wheel.sources[d.id]) {
      state.wheel.sources[d.id] = {
        state: d.state,
        latency_ms: d.latency_ms || 0,
        summary: d.summary || '',
      };
    }
    if (d.state !== 'fetching') {
      pushFeed(d.id.toUpperCase(), 'SOURCE', d.summary || d.state, d.ts);
    }
    notify('wheel');
  });

  es.addEventListener('compute', (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    pushFeed(d.id.toUpperCase(), 'INDICATOR', d.summary || 'Computed', d.ts);
    notify('wheel');
  });

  es.addEventListener('agent', (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    if (d.id && state.wheel.agents[d.id]) {
      const prev = state.wheel.agents[d.id];
      state.wheel.agents[d.id] = {
        ...prev,
        state: d.state,
        model: d.model || prev.model,
        mode: d.mode || prev.mode,
        summary: d.summary || prev.summary,
      };
    }
    if (d.state === 'done' || d.state === 'fallback') {
      pushFeed(`${d.id.toUpperCase()} (${d.model})`, d.state === 'fallback' ? 'FALLBACK' : 'AGENT', d.summary || 'Completed', d.ts);
    }
    notify('wheel');
  });

  es.addEventListener('token', (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    if (d.agent && state.wheel.agents[d.agent]) {
      state.wheel.agents[d.agent].streamText = d.text || '';
      state.wheel.agents[d.agent].model = d.model || state.wheel.agents[d.agent].model;
    }
    notify('token');
  });

  es.addEventListener('handoff', (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    if (d.from === 'meteorologist' && d.to === 'hydrologist') {
      state.wheel.handoffs.m_to_h = true;
    } else if (d.from === 'hydrologist' && d.to === 'agronomist') {
      state.wheel.handoffs.h_to_a = true;
    }
    pushFeed('HANDOFF', 'HANDOFF', `${d.from} -> ${d.to}: ${d.takeaway}`, d.ts);
    notify('wheel');
  });

  es.addEventListener('done', async (e) => {
    if (state.runId !== runId || state.runState === 'CANCELLED') return;
    const d = JSON.parse(e.data);
    closeActiveStream();
    try {
      const fullResult = await apiGetResult(runId);
      if (state.runId !== runId || state.runState === 'CANCELLED') return;
      state.result = fullResult;
      state.scenarioActive = false;
      state.runState = fullResult.state || d.state || 'DONE';
      state.wheel.pct = 100;
      state.wheel.word = 'Done';
      state.wheel.ticker = 'Analysis complete · Opening Outlook';
      notify('result');

      // Auto-advance to #outlook after 900 ms unless user opened the Details drawer
      setTimeout(() => {
        if (state.route === 'analysis' && state.runId === runId && !state.drawerOpen) {
          navigateTo('outlook');
        }
      }, 900);
    } catch (err) {
      console.error('Failed to fetch result after done:', err);
    }
  });

  es.addEventListener('error', (e) => {
    try {
      if (e.data) {
        const d = JSON.parse(e.data);
        state.wheel.ticker = d.message || 'Run interrupted';
      }
    } catch (_) {}
    closeActiveStream();
    notify('wheel');
  });
}

export function runChoreographedDemoWheel(demoResult, autoAdvance = true) {
  closeActiveStream();
  resetWheelForNewRun();
  state.result = demoResult;
  state.runId = demoResult.run_id;
  state.scenarioActive = false;
  state.runState = 'RUNNING';
  notify('wheel');

  const steps = [
    {
      ms: 120,
      fn: () => {
        state.wheel.pct = 16;
        state.wheel.word = 'Gathering';
        state.wheel.ticker = 'Loading cached forecast and soil profile';
        state.wheel.sources.forecast = { state: 'fetching', latency_ms: 0, summary: 'Reading disk cache…' };
        state.wheel.sources.soil = { state: 'fetching', latency_ms: 0, summary: 'Reading 3 soil depths…' };
      },
    },
    {
      ms: 420,
      fn: () => {
        state.wheel.pct = 34;
        state.wheel.word = 'Reading soil';
        state.wheel.ticker = 'Sampling 0–100 cm soil moisture';
        state.wheel.sources.forecast = { state: 'cached', latency_ms: 4, summary: 'CACHED · 45 days (4 ms)' };
        state.wheel.sources.soil = { state: 'cached', latency_ms: 4, summary: 'CACHED · 3 depths (0–100 cm)' };
        state.wheel.sources.baseline = { state: 'cached', latency_ms: 3, summary: 'CACHED · 2016–2025 archive' };
        state.wheel.sources.seasonal = { state: 'cached', latency_ms: 5, summary: 'CACHED · 50-member ensemble' };
      },
    },
    {
      ms: 780,
      fn: () => {
        state.wheel.pct = 56;
        state.wheel.word = 'Assessing';
        state.wheel.ticker = 'Meteorologist assessing surface moisture';
        state.wheel.agents.meteorologist = {
          state: 'active',
          model: demoResult.agents.meteorologist.model,
          mode: 'CACHED',
          summary: 'Streaming cached assessment…',
          streamText: demoResult.agents.meteorologist.text.slice(0, 140) + '…',
        };
      },
    },
    {
      ms: 1180,
      fn: () => {
        state.wheel.pct = 74;
        state.wheel.word = 'Assessing';
        state.wheel.ticker = 'Hydrologist evaluating drought horizons';
        state.wheel.agents.meteorologist = {
          state: 'done',
          model: demoResult.agents.meteorologist.model,
          mode: 'CACHED',
          summary: demoResult.agents.meteorologist.takeaway,
          streamText: demoResult.agents.meteorologist.text,
        };
        state.wheel.handoffs.m_to_h = true;
        state.wheel.agents.hydrologist = {
          state: 'active',
          model: demoResult.agents.hydrologist.model,
          mode: 'CACHED',
          summary: 'Evaluating 7–15d & 1–3m horizons…',
          streamText: demoResult.agents.hydrologist.text.slice(0, 140) + '…',
        };
      },
    },
    {
      ms: 1580,
      fn: () => {
        state.wheel.pct = 90;
        state.wheel.word = 'Planning';
        state.wheel.ticker = 'Agronomist matching UK crop windows';
        state.wheel.agents.hydrologist = {
          state: 'done',
          model: demoResult.agents.hydrologist.model,
          mode: 'CACHED',
          summary: demoResult.agents.hydrologist.takeaway,
          streamText: demoResult.agents.hydrologist.text,
        };
        state.wheel.handoffs.h_to_a = true;
        state.wheel.agents.agronomist = {
          state: 'active',
          model: demoResult.agents.agronomist.model,
          mode: 'CACHED',
          summary: 'Matching UK crop rules…',
          streamText: demoResult.agents.agronomist.text.slice(0, 140) + '…',
        };
      },
    },
    {
      ms: 1950,
      fn: () => {
        state.wheel.pct = 100;
        state.wheel.word = 'Done';
        state.wheel.ticker = 'Analysis complete · Ready for Outlook';
        state.wheel.agents.agronomist = {
          state: 'done',
          model: demoResult.agents.agronomist.model,
          mode: 'CACHED',
          summary: demoResult.agents.agronomist.takeaway,
          streamText: demoResult.agents.agronomist.text,
        };
        state.runState = 'DONE';
        notify('result');
        if (autoAdvance) {
          const tAdv = setTimeout(() => {
            if (state.route === 'analysis' && !state.drawerOpen) {
              navigateTo('outlook');
            }
          }, 800);
          demoTimers.push(tAdv);
        }
      },
    },
  ];

  for (const s of steps) {
    const tid = setTimeout(() => {
      s.fn();
      notify('wheel');
    }, s.ms);
    demoTimers.push(tid);
  }
}
