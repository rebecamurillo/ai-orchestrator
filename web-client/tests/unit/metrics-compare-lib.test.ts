import { describe, expect, it } from 'vitest';

import {
  addRunsHref,
  cellTarget,
  compareQuery,
  compareSearch,
  deltaOf,
  exportFailedLine,
  exportLine,
  fileNameOf,
  groupRows,
  headerView,
  methodsLine,
  parseCompare,
  recalcHref,
  removeRun,
  runCells,
  sameWorkView,
  setVersion,
  type CompareState,
} from '../../src/lib/metrics/compare';
import { entry } from './metrics-fixtures';
import { A, B, C, cell, comparePayload, header, metric, PROJECT } from './metrics-compare-fixtures';

const base: CompareState = {
  runIds: [A, B],
  versions: {},
  view: 'table',
  set: 'headline',
  blind: false,
};

describe('parseCompare / compareSearch', () => {
  it('round trips every field', () => {
    const state: CompareState = {
      runIds: [A, B],
      versions: { [A]: 1, [B]: 2 },
      view: 'chart',
      set: 'all',
      blind: true,
    };
    const search = compareSearch(state);
    expect(search).toBe(`?runs=${A},${B}&v=${A}:1,${B}:2&view=chart&metrics=all&blind=1`);
    expect(parseCompare(search)).toEqual(state);
  });

  it('writes only runs for the default state', () => {
    expect(compareSearch(base)).toBe(`?runs=${A},${B}`);
    expect(parseCompare(`?runs=${A},${B}`)).toEqual(base);
  });

  it('drops empties and duplicates, trims, keeps order', () => {
    expect(parseCompare(`?runs=${B}, ${A},,${B}`).runIds).toEqual([B, A]);
    expect(parseCompare('').runIds).toEqual([]);
  });

  it('keeps only valid v tokens of selected runs', () => {
    const state = parseCompare(`?runs=${A},${B}&v=${A}:1,${B}:0,${B}:x,${C}:2,junk,${B}:3`);
    expect(state.versions).toEqual({ [A]: 1, [B]: 3 });
    expect(parseCompare(`?runs=${A}&v=${A}:99999999999999999999`).versions).toEqual({});
  });

  it('orders v by runIds', () => {
    const state = { ...base, versions: { [B]: 2, [A]: 1 } };
    expect(compareSearch(state)).toContain(`&v=${A}:1,${B}:2`);
  });
});

describe('compareQuery, removeRun, setVersion, hrefs', () => {
  it('carries blind and v only when set', () => {
    expect(compareQuery(base)).toEqual({ runs: `${A},${B}` });
    expect(compareQuery({ ...base, blind: true, versions: { [A]: 1 } })).toEqual({
      runs: `${A},${B}`,
      v: `${A}:1`,
      blind: true,
    });
  });

  it('removeRun drops the run and its v entry', () => {
    const next = removeRun({ ...base, runIds: [A, B, C], versions: { [B]: 1, [C]: 2 } }, B);
    expect(next.runIds).toEqual([A, C]);
    expect(next.versions).toEqual({ [C]: 2 });
  });

  it('setVersion pins, and the latest drops the entry', () => {
    const pinned = setVersion(base, A, 1, 2);
    expect(pinned.versions).toEqual({ [A]: 1 });
    expect(setVersion(pinned, A, 2, 2).versions).toEqual({});
  });

  it('builds the add-runs and recalculate links', () => {
    expect(addRunsHref(PROJECT, [A, B])).toBe(`/metrics?project=${PROJECT}&select=${A},${B}`);
    expect(recalcHref(A)).toBe(`/workflows/${A}?tab=metrics&recalculate=1`);
  });
});

describe('headerView', () => {
  it('shapes a header', () => {
    const view = headerView(header(A, { label_set_by_operator: true }));
    expect(view).toEqual({
      id: A,
      token: 'DON',
      shortId: A.slice(0, 8),
      href: `/workflows/${A}`,
      label: `label a`,
      ownLabel: true,
      template: 'story@3',
      harness: 'claude',
      models: ['coder: m1 · m2'],
      base: 'base main',
      status: 'done',
      stories: '3/4 stories',
      versions: [1, 2],
      selected: 2,
      latest: 2,
    });
  });

  it('collapses the blind template, and fills absent fields', () => {
    const view = headerView(
      header(A, {
        template_name: 'hidden · blind',
        template_version: 'hidden · blind',
        harness: null,
        base_branch: null,
        stories_done: null,
        versions_available: [],
        selected_version: null,
      }),
    );
    expect(view.template).toBe('hidden · blind');
    expect(view.harness).toBe('—');
    expect(view.base).toBe('base —');
    expect(view.stories).toBeNull();
    expect(view.latest).toBeNull();
    expect(view.versions).toEqual([]);
  });

  it('keeps a half-blind template as name@version', () => {
    const view = headerView(header(A, { template_name: 'hidden · blind' }));
    expect(view.template).toBe('hidden · blind@3');
  });
});

describe('sameWorkView', () => {
  it('prints base commits, initiative and stories per run, with the flag', () => {
    const payload = comparePayload([A, B]);
    payload.same_work.differs = true;
    payload.same_work.runs[B] = {
      base_commits: { r: null, s: '1234567890abcdef' },
      initiative_folder: null,
      stories_planned: null,
    };
    const view = sameWorkView(payload);
    expect(view.flag).toBe('≠ the work differs');
    expect(view.cells[A]).toEqual({
      commits: 'acme/app:abcdef01',
      initiative: 'init',
      stories: '4',
    });
    expect(view.cells[B]).toEqual({ commits: 'r:— s:12345678', initiative: '—', stories: '—' });
  });

  it('has no flag when the work is the same, and a dash for a missing run', () => {
    const payload = comparePayload([A, B]);
    delete payload.same_work.runs[B];
    const view = sameWorkView(payload);
    expect(view.flag).toBeNull();
    expect(view.cells[B]).toEqual({ commits: '—', initiative: '—', stories: '—' });
  });
});

describe('groupRows', () => {
  const entries = {
    'cost.gateway': entry('cost.gateway', { group: 'cost', level: 'H' }),
    'cost.x': entry('cost.x', { group: 'budget', level: 'A' }),
    'tokens.input': entry('tokens.input', { group: 'tokens', level: 'H' }),
    'time.wall': entry('time.wall', { group: 'time', level: 'H' }),
    'process.attempts': entry('process.attempts', { group: 'process', level: 'A' }),
    'activity.t': entry('activity.t', { group: 'activity', level: 'A' }),
    odd: entry('odd', { group: 'weird', level: 'H' }),
  };
  const ids = [A, B];
  const metrics = [
    metric('activity.t', ids),
    metric('time.wall', ids),
    metric('cost.x', ids),
    metric('cost.gateway', ids),
    metric('odd', ids),
    metric('ghost', ids),
    metric('tokens.input', ids),
    metric('process.attempts', ids),
  ];

  it('orders groups, keeps payload order inside, leaves out the unplaceable', () => {
    const all = groupRows(entries, metrics, 'all');
    expect(all.map((g) => g.group)).toEqual([
      'COST',
      'TOKENS',
      'TIME',
      'PROCESS',
      'ACTIVITY IN ATTEMPTS',
    ]);
    expect(all[0].rows.map((r) => r.metric_id)).toEqual(['cost.x', 'cost.gateway']);
  });

  it('headline keeps level H only and drops empty groups', () => {
    const headline = groupRows(entries, metrics, 'headline');
    expect(headline.map((g) => g.group)).toEqual(['COST', 'TOKENS', 'TIME']);
    expect(headline[0].rows.map((r) => r.metric_id)).toEqual(['cost.gateway']);
  });
});

describe('cells, methods, delta, target', () => {
  const m = metric('cost.gateway', [A, B], {
    methods_differ: true,
    methods: { [A]: ['cost.gateway@1', 'cost.gateway@2'] },
    harness_delta: { [A]: '+0.50 vs gateway' },
  });
  m.cells[A].push(cell({ scope_type: 'attempt', scope_key: 'x#1' }));

  it('returns run-scope cells only', () => {
    expect(runCells(m, A)).toHaveLength(1);
    expect(runCells(m, C)).toEqual([]);
  });

  it('methodsLine only when the methods differ', () => {
    expect(methodsLine(m, A)).toBe('cost.gateway@1, cost.gateway@2');
    expect(methodsLine(m, B)).toBe('');
    expect(methodsLine({ ...m, methods_differ: false }, A)).toBeNull();
  });

  it('deltaOf is the payload word or null', () => {
    expect(deltaOf(m, A)).toBe('+0.50 vs gateway');
    expect(deltaOf(m, B)).toBeNull();
  });

  it('cellTarget projects the cell with no origin', () => {
    const h = header(A, { subscription: true });
    const target = cellTarget(m.cells[A][0], 'cost.gateway', h);
    expect(target.value.metric_id).toBe('cost.gateway');
    expect(target.value.origin).toBeNull();
    expect(target.value.value_num).toBe('1.5');
    expect(target.runLabel).toBe(h.label);
    expect(target.version).toBeNull();
    expect(target.latest).toBe(2);
    expect(target.subscription).toBe(true);
    expect(cellTarget(m.cells[A][0], 'cost.gateway', header(A)).subscription).toBe(false);
  });
});

describe('export wording', () => {
  it('reads the quoted file name, else the fallback', () => {
    expect(fileNameOf('attachment; filename="p-compare-2026-11-13.csv"', 'fb.csv')).toBe(
      'p-compare-2026-11-13.csv',
    );
    expect(fileNameOf(null, 'fb.csv')).toBe('fb.csv');
    expect(fileNameOf('attachment', 'fb.csv')).toBe('fb.csv');
  });

  it('prints the done line in both blind states', () => {
    expect(exportLine('p-compare-2026-11-13', 3, 12, false)).toBe(
      'exported p-compare-2026-11-13.csv and .json · 3 Runs · 12 metrics · run labels included · each description once',
    );
    expect(exportLine('p', 2, 1, true)).toContain('run labels hidden');
  });

  it('prints the failed line', () => {
    expect(exportFailedLine('/api/metrics/compare.csv', 500)).toBe(
      'export failed · GET /api/metrics/compare.csv · 500',
    );
  });
});
