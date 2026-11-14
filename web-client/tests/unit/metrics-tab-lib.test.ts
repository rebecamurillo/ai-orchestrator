import { describe, expect, it } from 'vitest';

import {
  attemptValues,
  ATTEMPT_COLUMNS,
  defaultTab,
  epicFrame,
  FINGERPRINT_LINE,
  flatRows,
  metricList,
  metricsSearch,
  parseMetricsQuery,
  settledVersion,
  scopeTree,
  storyFrame,
  TABLE_COLUMNS,
  valuesAt,
  type ScopeNode,
} from '../../src/lib/run/metrics-tab';
import { entry, value } from './metrics-fixtures';

const at = (type: string, key: string, over = {}) =>
  value({ scope_type: type, scope_key: key, metric_id: 'cost.gateway', ...over });

describe('frames', () => {
  it('reads the last matching segment and never splits inside a bracket', () => {
    expect(storyFrame('epics[0].stories[10].build')).toBe('epics[0].stories[10]');
    expect(storyFrame('stories[1].build')).toBe('stories[1]');
    expect(storyFrame('epics[1].push')).toBeNull();
    expect(epicFrame('epics[1].stories[3].build')).toBe('epics[1]');
    expect(epicFrame('stories[0].build')).toBeNull();
    expect(storyFrame('stories[x].build')).toBeNull();
  });
});

describe('columns', () => {
  it('lists the ten table columns and the six attempt columns', () => {
    expect(TABLE_COLUMNS).toHaveLength(10);
    expect(ATTEMPT_COLUMNS).toEqual(TABLE_COLUMNS.slice(0, 6));
  });
});

describe('valuesAt', () => {
  it('returns every match in response order', () => {
    const a = value({ metric_id: 'process.retries', source: 'gateway' });
    const b = value({ metric_id: 'process.retries', source: 'harness' });
    const c = value({ metric_id: 'process.retries', scope_type: 'epic', scope_key: 'epics[0]' });
    expect(valuesAt([a, c, b], 'process.retries', 'run', a.scope_key)).toEqual([a, b]);
    expect(valuesAt([a], 'cost.total', 'run', a.scope_key)).toEqual([]);
  });
});

function walk(node: ScopeNode): string[] {
  return [node.label, ...node.children.flatMap(walk)];
}

describe('scopeTree', () => {
  const items = [
    at('attempt', 'epics[0].stories[0].build#2', { attempt_n: 2 }),
    at('attempt', 'epics[0].stories[0].build#1', { attempt_n: 1 }),
    at('step', 'epics[0].stories[0].build', { scope_label: 'build' }),
    at('step', 'epics[0].stories[0].verify', { scope_label: 'verify' }),
    at('story', 'epics[0].stories[0]', { scope_label: '1-1' }),
    at('epic', 'epics[0]'),
    at('epic', 'epics[1]'),
    at('run', 'run-1'),
  ];
  const order = ['epics[0].stories[0].verify', 'epics[0].stories[0].build'];

  it('nests attempts under steps, steps under stories, stories under epics', () => {
    const root = scopeTree(items, order);
    expect(root.type).toBe('run');
    expect(root.label).toBe('run');
    expect(walk(root)).toEqual([
      'run',
      'epic 1',
      'epic 1 · story 1-1',
      'verify',
      'build',
      'attempt 1',
      'attempt 2',
      'epic 2',
    ]);
  });

  it('puts unknown steps last by key and creates missing parents', () => {
    const root = scopeTree(
      [
        at('step', 'stories[3].z'),
        at('step', 'stories[3].a'),
        at('step', 'epics[2].push'),
        at('step', 'plain'),
        at('attempt', 'orphan#4'),
        at('attempt', 'stories[3].a#x'),
        at('story', 'stories[10]'),
      ],
      ['stories[3].z'],
    );
    expect(walk(root)).toEqual([
      'run',
      'story 4',
      'stories[3].z',
      'stories[3].a',
      'attempt x',
      'epic 3',
      'epics[2].push',
      'orphan',
      'attempt 4',
      'plain',
      'story 11',
    ]);
  });

  it('keeps the run node when there are no values', () => {
    expect(scopeTree([], [])).toMatchObject({ type: 'run', children: [] });
  });
});

describe('flatRows', () => {
  it('sorts by gateway descending, missing last, ties by key', () => {
    const rows = flatRows(
      [
        at('role', 'implement', { value_num: '4.00' }),
        at('role', 'senior', { value_num: '9.00' }),
        at('role', 'review', { value_num: null, missing: 'not available' }),
        at('role', 'aaa', { value_num: '4.00' }),
        at('role', 'noval', { metric_id: 'tokens.input' }),
        at('model', 'm', { value_num: '1' }),
      ],
      'role',
    );
    expect(rows).toEqual(['senior', 'aaa', 'implement', 'noval', 'review']);
  });
});

describe('metricList', () => {
  const entries = {
    'cost.gateway': entry('cost.gateway', { group: 'cost', level: 'H' }),
    'tokens.input': entry('tokens.input', { group: 'tokens', level: 'A' }),
    'budget.cap': entry('budget.cap', { group: 'budget', level: 'H' }),
    'process.fp': entry('process.fp', { group: 'process', fingerprint_group: true, level: 'A' }),
    'time.wall': entry('time.wall', { group: 'time', level: 'H' }),
    'other.x': entry('other.x', { group: 'other', level: 'H' }),
    'activity.a': entry('activity.a', { group: 'activity', level: 'A' }),
  };
  const items = Object.keys(entries).map((id) =>
    value({ metric_id: id, scope_type: 'run', scope_key: 'r' }),
  );
  const stray = value({ metric_id: 'cost.gateway', scope_type: 'epic', scope_key: 'epics[0]' });

  it('groups the Run values in order, fingerprint last', () => {
    const list = metricList(entries, [...items, stray], 'all');
    expect(list.map((g) => g.group)).toEqual([
      'COST',
      'TOKENS',
      'TIME',
      'ACTIVITY IN ATTEMPTS',
      FINGERPRINT_LINE,
    ]);
    expect(list[0].entries.map((e) => e.entry.id)).toEqual(['cost.gateway', 'budget.cap']);
    expect(list[0].entries[0].values).toHaveLength(1);
  });

  it('keeps level H only for the headline and omits entries with no Run value', () => {
    const list = metricList(entries, items.slice(0, 5), 'headline');
    expect(list.map((g) => g.group)).toEqual(['COST', 'TIME']);
    expect(metricList(entries, [], 'all')).toEqual([]);
  });
});

describe('query', () => {
  it('parses with defaults for anything unknown', () => {
    expect(parseMetricsQuery('')).toEqual({ tab: null, view: 'table', set: 'headline', v: null });
    expect(parseMetricsQuery('?tab=metrics&view=chart&metrics=all&v=2')).toEqual({
      tab: 'metrics',
      view: 'chart',
      set: 'all',
      v: 2,
    });
    expect(parseMetricsQuery('?tab=nope&view=x&metrics=y&v=0').v).toBeNull();
    expect(parseMetricsQuery('?v=1.5&tab=nope')).toMatchObject({ tab: null, v: null });
    expect(parseMetricsQuery('?v=abc').v).toBeNull();
    expect(parseMetricsQuery('?v=1000000000000000000000').v).toBeNull();
  });

  it('writes the state, keeping other parameters', () => {
    const state = { tab: 'metrics' as const, view: 'table' as const, set: 'all' as const, v: 1 };
    const s = metricsSearch('?x=1', state);
    expect(s).toBe('?x=1&tab=metrics&view=table&metrics=all&v=1');
    expect(parseMetricsQuery(s)).toEqual({ ...state, tab: 'metrics' });
    expect(metricsSearch(s, { ...state, set: 'headline', v: null })).toBe(
      '?x=1&tab=metrics&view=table',
    );
    expect(metricsSearch(s, { ...state, tab: 'gate' })).toBe('?x=1&tab=gate&v=1');
    expect(metricsSearch('', { ...state, tab: 'gate', v: null })).toBe('?tab=gate');
  });
});

describe('defaultTab', () => {
  const base = { hashSeq: null, queryTab: null, hasTerminal: false, status: 'running' };
  it('follows the precedence of the spec', () => {
    expect(defaultTab({ ...base, hashSeq: 3, queryTab: 'gate' })).toBe('steps');
    expect(defaultTab({ ...base, queryTab: 'steps' })).toBe('steps');
    expect(defaultTab({ ...base, queryTab: 'session' })).toBe('gate');
    expect(defaultTab({ ...base, queryTab: 'session', hasTerminal: true })).toBe('session');
    expect(defaultTab({ ...base, hasTerminal: true, status: 'done' })).toBe('session');
    for (const status of ['done', 'failed', 'cancelled']) {
      expect(defaultTab({ ...base, status })).toBe('metrics');
    }
    for (const status of ['running', 'queued', 'needs_you']) {
      expect(defaultTab({ ...base, status })).toBe('gate');
    }
  });
});

describe('attemptValues', () => {
  it('keeps the attempt scope of one step path', () => {
    const a = at('attempt', 'a.build#1');
    const b = at('attempt', 'a.build2#1');
    const c = at('step', 'a.build');
    expect(attemptValues([a, b, c], 'a.build')).toEqual([a]);
  });
});

describe('settledVersion', () => {
  const versions = [{ n: 1 }, { n: 2 }];
  it('keeps an older version the Run has', () => {
    expect(settledVersion(1, versions)).toBe(1);
  });
  it('follows the latest for the latest or a version the Run lacks', () => {
    expect(settledVersion(2, versions)).toBeNull();
    expect(settledVersion(99, versions)).toBeNull();
  });
  it('waits while the versions are unknown, and leaves no selection alone', () => {
    expect(settledVersion(3, [])).toBe(3);
    expect(settledVersion(null, versions)).toBeNull();
  });
});
