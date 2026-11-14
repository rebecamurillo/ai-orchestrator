import type { RunDetailOut } from '../../src/lib/run/detail';
import { $catalogue } from '../../src/stores/catalogue';
import { TABLE_COLUMNS } from '../../src/lib/run/metrics-tab';
import type { RunMetricsState } from '../../src/stores/run-metrics';
import { entry, version } from './metrics-fixtures';
import type { Entry } from './metrics-fixtures';

export function seedCatalogue(extra: Entry[] = []): void {
  const all = [...TABLE_COLUMNS.map((id) => entry(id)), entry('spend.recorded'), ...extra];
  $catalogue.set({ status: 'ready', entries: Object.fromEntries(all.map((e) => [e.id, e])) });
}

export function detailOf(status = 'done'): RunDetailOut {
  return {
    run: { id: '1', status, branch: 'chore/x', label: 'my run', compare_urls: [], project: 'p1' },
    header: { meta: { project: 'familio' } },
    steps: [
      { seq: 2, path: 'epics[0].stories[0].verify' },
      { seq: 1, path: 'epics[0].stories[0].build' },
    ],
  } as unknown as RunDetailOut;
}

export function glanceOf(over: Partial<RunMetricsState> = {}): RunMetricsState {
  return {
    runId: '1',
    status: 'ready',
    failed: null,
    metrics: { items: [], latest: 1, run_id: '1', values_so_far: false, version: 1 },
    versions: [version(1)],
    selected: null,
    calc: null,
    calcError: null,
    ...over,
  };
}
