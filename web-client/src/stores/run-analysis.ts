/**
 * The analyses behind the shown result version of a Run. A superseded response is ignored and
 * a failed read names its request; nothing here retries on its own (hard rule 7).
 */
import { atom } from 'nanostores';

import { api } from '../api/client';
import type { components } from '../api/schema';

type AnalysisOut = components['schemas']['AnalysisOut'];

export interface RunAnalysisState {
  runId: string;
  version: number | null;
  status: 'idle' | 'loading' | 'ready' | 'failed';
  items: AnalysisOut[];
  failed: { path: string; status: number | null } | null;
}

const INITIAL: RunAnalysisState = {
  runId: '',
  version: null,
  status: 'idle',
  items: [],
  failed: null,
};

export const $runAnalysis = atom<RunAnalysisState>(INITIAL);

let seq = 0;

export async function loadRunAnalysis(runId: string, v: number): Promise<void> {
  const mine = ++seq;
  const held = $runAnalysis.get();
  $runAnalysis.set(
    held.runId === runId && held.version === v
      ? { ...held, status: 'loading' }
      : { ...INITIAL, runId, version: v, status: 'loading' },
  );
  const path = `/api/runs/${runId}/analysis?v=${v}`;
  let next: Partial<RunAnalysisState>;
  try {
    const { data, response } = await api.GET('/runs/{run_id}/analysis', {
      params: { path: { run_id: runId }, query: { v } },
    });
    next = data
      ? { status: 'ready', items: data.items, failed: null }
      : { status: 'failed', failed: { path, status: response.status } };
  } catch {
    next = { status: 'failed', failed: { path, status: null } };
  }
  if (mine !== seq) return;
  $runAnalysis.set({ ...$runAnalysis.get(), ...next });
}
