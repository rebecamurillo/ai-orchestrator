/**
 * The Run page's metric reads: values, result versions and the calculation in flight. A failed
 * read never replaces the page; it keeps the last good data and names the request. Nothing here
 * retries on its own (hard rule 7) — the next poll tick is the only re-read.
 */
import { atom } from 'nanostores';

import { api } from '../api/client';
import type { components } from '../api/schema';

type ProblemDetail = components['schemas']['ProblemDetail'];
type CalculationOut = components['schemas']['CalculationOut'];
type ResultVersionOut = components['schemas']['ResultVersionOut'];
type RunMetricsOut = components['schemas']['RunMetricsOut'];

export interface RunMetricsState {
  runId: string;
  status: 'idle' | 'loading' | 'ready' | 'failed';
  failed: { path: string; status: number | null } | null;
  metrics: RunMetricsOut | null;
  versions: ResultVersionOut[];
  /** `null` follows the latest version. */
  selected: number | null;
  calc: CalculationOut | null;
  calcError: ProblemDetail | null;
}

const INITIAL: RunMetricsState = {
  runId: '',
  status: 'idle',
  failed: null,
  metrics: null,
  versions: [],
  selected: null,
  calc: null,
  calcError: null,
};

export const $runMetrics = atom<RunMetricsState>(INITIAL);

let seq = 0;

function patch(next: Partial<RunMetricsState>): void {
  $runMetrics.set({ ...$runMetrics.get(), ...next });
}

const path = (runId: string, rest: string): string => `/api/runs/${runId}/metrics${rest}`;

export function calcActive(state: RunMetricsState): boolean {
  return state.calc?.state === 'queued' || state.calc?.state === 'running';
}

export function resetRunMetrics(): void {
  seq += 1;
  $runMetrics.set(INITIAL);
}

export async function loadRunMetrics(runId: string): Promise<void> {
  const mine = ++seq;
  const held = $runMetrics.get().runId;
  if (held === '') patch({ runId });
  else if (held !== runId) $runMetrics.set({ ...INITIAL, runId });
  if ($runMetrics.get().status === 'idle') patch({ status: 'loading' });
  const selected = $runMetrics.get().selected;
  let failed: RunMetricsState['failed'] = null;
  let versions: ResultVersionOut[] | null = null;
  let metrics: RunMetricsOut | null = null;
  let reading = '/versions';
  try {
    const v = await api.GET('/runs/{run_id}/metrics/versions', {
      params: { path: { run_id: runId } },
    });
    if (v.data) versions = v.data.items;
    else failed = { path: path(runId, '/versions'), status: v.response.status };
    reading = '';
    const m = await api.GET('/runs/{run_id}/metrics', {
      params: { path: { run_id: runId }, query: selected === null ? undefined : { v: selected } },
    });
    if (m.data) metrics = m.data;
    else failed ??= { path: path(runId, ''), status: m.response.status };
  } catch {
    failed ??= { path: path(runId, reading), status: null };
  }
  if (mine !== seq) return;
  const current = $runMetrics.get();
  patch({
    status: failed ? 'failed' : 'ready',
    failed,
    versions: versions ?? current.versions,
    metrics: metrics ?? current.metrics,
  });
}

export async function selectVersion(runId: string, n: number): Promise<void> {
  const latest = Math.max(0, ...$runMetrics.get().versions.map((v) => v.n));
  patch({ selected: n === latest ? null : n });
  await loadRunMetrics(runId);
}

export async function startCalculation(runId: string): Promise<void> {
  patch({ calcError: null });
  try {
    const { data, error } = await api.POST('/runs/{run_id}/metrics/calculate', {
      params: { path: { run_id: runId } },
    });
    if (data) {
      patch({ calc: data });
      return;
    }
    patch({ calcError: error });
    if (error?.status === 409) await loadRunMetrics(runId);
  } catch {
    patch({
      calcError: {
        status: 0,
        title: 'the request failed',
        type: 'about:blank',
        detail: `POST ${path(runId, '/calculate')} → network error`,
      },
    });
  }
}

export async function pollCalculation(runId: string): Promise<void> {
  const calc = $runMetrics.get().calc;
  if (!calc) return;
  try {
    const { data } = await api.GET('/runs/{run_id}/metrics/calculations/{n}', {
      params: { path: { run_id: runId, n: calc.target_n } },
    });
    if (!data) return;
    if (data.state === 'done') {
      patch({ calc: null });
      await loadRunMetrics(runId);
      return;
    }
    patch({ calc: data });
  } catch {
    // the next tick reads again; the calculation record stays as it was
  }
}
