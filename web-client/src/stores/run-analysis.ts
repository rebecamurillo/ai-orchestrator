/**
 * The analyses behind the shown result version of a Run. A superseded response is ignored and
 * a failed read names its request; nothing here retries on its own (hard rule 7).
 */
import { atom } from 'nanostores';

import { api } from '../api/client';
import type { components } from '../api/schema';
import { addEntries } from './catalogue';

type AnalysisOut = components['schemas']['AnalysisOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

export interface RunAnalysisState {
  runId: string;
  version: number | null;
  status: 'idle' | 'loading' | 'ready' | 'failed';
  items: AnalysisOut[];
  stepEntries?: CatalogueEntryOut[];
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
      ? { status: 'ready', items: data.items, stepEntries: data.step_entries, failed: null }
      : { status: 'failed', failed: { path, status: response.status } };
  } catch {
    next = { status: 'failed', failed: { path, status: null } };
  }
  if (mine !== seq) return;
  if (next.stepEntries) addEntries(next.stepEntries);
  $runAnalysis.set({ ...$runAnalysis.get(), ...next });
}
