import { describe, expect, it } from 'vitest';

import {
  calculatedAt,
  countSpans,
  entryPointWords,
  formatValue,
  naWords,
  originRows,
  stateWords,
  versionView,
} from '../../src/lib/metrics/format';
import { PROJECT_ID, RUN_ID, entry, target, value, version } from './metrics-fixtures';

describe('formatValue', () => {
  it.each([
    ['15.345', 'USD', '$15.35'],
    ['1234567', 'tokens', '1,234,567'],
    ['12', 'count', '12'],
    ['3400', 'words', '3,400'],
    ['1260', 'seconds', '0h 21m'],
    ['3725', 'seconds', '1h 02m'],
    ['0.456', 'ratio', '0.46'],
    ['7', 'furlongs', '7'],
  ])('%s %s → %s', (num, unit, text) => {
    expect(formatValue(num, unit)).toBe(text);
  });
});

describe('stateWords', () => {
  it('lists list-price equivalent, partial and carried in that order', () => {
    const v = value({ partial_n: 2, partial_m: 3, carried_from: 1 });
    expect(stateWords(v, true)).toEqual([
      'list-price equivalent',
      'partial · 2 of 3 attempts',
      'from v1',
    ]);
  });
  it('omits list-price equivalent off subscription or off USD', () => {
    expect(stateWords(value(), false)).toEqual([]);
    expect(stateWords(value({ unit: 'tokens' }), true)).toEqual([]);
  });
});

describe('words', () => {
  it('entryPointWords', () => {
    expect(entryPointWords(['at_attempt_end', 'workflow_step', 'manual'])).toBe(
      'at attempt end + workflow step + manual',
    );
  });
  it('calculatedAt', () => {
    expect(calculatedAt('2026-11-19T14:02:33Z')).toBe('2026-11-19 14:02Z');
  });
});

describe('naWords', () => {
  it('spans_models on a run total', () => {
    expect(naWords('spans_models', 'run', { models: 2 })).toBe('a Run total spans 2 models');
  });
  it('spans on another scope and with no count', () => {
    expect(naWords('spans_models', 'story', { models: 3 })).toBe('the story spans 3 models');
    expect(naWords('spans_models', 'run', {})).toBe('more than one model');
    expect(naWords('spans_repositories', 'run', { repositories: 2 })).toBe(
      'a Run total spans 2 repositories',
    );
    expect(naWords('spans_repositories', 'epic', undefined)).toBe('more than one repository');
    expect(naWords('spans_harnesses', 'run', { harnesses: 2 })).toBe(
      'a Run total spans 2 harnesses',
    );
    expect(naWords('spans_harnesses', 'run', {})).toBe('more than one harness');
  });
  it('fixed reasons and passthrough', () => {
    expect(naWords('no_model_called', 'run')).toBe('no model called');
    expect(naWords('no_repository_scope', 'run')).toBe('the value has no repository scope');
    expect(naWords('no_repository_record', 'run')).toBe('no repository record');
    expect(naWords('commit_missing', 'run')).toBe('commit missing');
    expect(naWords('branch_unknown', 'run')).toBe('branch unknown');
    expect(naWords('base_tip_unknown', 'run')).toBe('base tip unknown');
  });
});

describe('countSpans', () => {
  it('counts distinct non-null models and repositories', () => {
    const items = [
      value({ model: 'a', repository: 'r1' }),
      value({ model: 'a', repository: 'r2' }),
      value({ model: 'b', repository: null }),
      value({ model: null }),
    ];
    expect(countSpans(items)).toEqual({ models: 2, repositories: 2 });
  });
});

describe('originRows', () => {
  const KEYS = [
    'metric',
    'method',
    'calculated',
    'entry point',
    'result version',
    'project',
    'Run',
    'template',
    'harness',
    'model',
    'repository',
    'branch',
    'commit',
    'base commit',
  ];

  it('returns the 14 rows in order with copy flags', () => {
    const rows = originRows(target(), entry());
    expect(rows.map((r) => r[0])).toEqual(KEYS);
    expect(rows.every((r) => r[1] !== '')).toBe(true);
    expect(rows.filter((r) => r[2]).map((r) => r[0])).toEqual([
      'project',
      'Run',
      'branch',
      'commit',
      'base commit',
    ]);
    const text = Object.fromEntries(rows.map((r) => [r[0], r[1]]));
    expect(text['metric']).toBe('cost.total · label of cost.total');
    expect(text['method']).toBe('cost.total@2');
    expect(text['calculated']).toBe('2026-11-19 14:02Z');
    expect(text['entry point']).toBe('at attempt end + workflow step');
    expect(text['result version']).toBe('v3 (latest)');
    expect(text['project']).toBe(PROJECT_ID);
    expect(text['Run']).toBe(RUN_ID);
    expect(text['template']).toBe('story@3');
    expect(text['harness']).toBe('claude');
    expect(text['model']).toBe('n/a — a Run total spans 2 models');
    expect(text['repository']).toBe('acme/app');
  });

  it('uses the project name, plain version, and n/a for missing version or origin', () => {
    const rows = originRows(target({ projectName: 'Acme', latest: 5 }), entry());
    const text = Object.fromEntries(rows.map((r) => [r[0], r[1]]));
    expect(text['project']).toBe('Acme');
    expect(text['result version']).toBe('v3');

    const bare = originRows(target({ version: null, value: value({ origin: null }) }), entry());
    const t = Object.fromEntries(bare.map((r) => [r[0], r[1]]));
    expect(t['calculated']).toBe('n/a — no result version');
    expect(t['result version']).toBe('n/a — no result version');
    expect(t['Run']).toBe('n/a — no origin recorded');
    expect(t['branch']).toBe('n/a — no origin recorded');
    expect(bare.every((r) => r[1] !== '')).toBe(true);
  });

  it('prints n/a with the reason when a field is null', () => {
    const base = value().origin!;
    const rows = originRows(
      target({
        value: value({
          origin: {
            ...base,
            harness: null,
            harness_na: 'spans_harnesses',
            commit: null,
            commit_na: 'commit_missing',
            origin_model: 'm1',
            origin_model_na: null,
          },
        }),
        spans: { harnesses: 2 },
      }),
      entry(),
    );
    const t = Object.fromEntries(rows.map((r) => [r[0], r[1]]));
    expect(t['harness']).toBe('n/a — a Run total spans 2 harnesses');
    expect(t['commit']).toBe('n/a — commit missing');
    expect(t['model']).toBe('m1');
  });

  it('offers copy only on a shown id, branch or commit, never on a name or an n/a line', () => {
    const copyOf = (rows: ReturnType<typeof originRows>) =>
      rows.filter((r) => r[2]).map((r) => r[0]);
    const base = value().origin!;
    const named = originRows(
      target({
        projectName: 'Acme',
        value: value({ origin: { ...base, commit: null, commit_na: 'commit_missing' } }),
      }),
      entry(),
    );
    expect(copyOf(named)).toEqual(['Run', 'branch', 'base commit']);
    expect(copyOf(originRows(target({ value: value({ origin: null }) }), entry()))).toEqual([]);
  });
});

describe('versionView', () => {
  const three = [version(1), version(2), version(3, { methods_changed: ['cost.total'] })];

  it('shows every segment up to five', () => {
    const view = versionView(three, 3);
    expect(view).toMatchObject({ segments: [1, 2, 3], overflow: false, latest: 3 });
    expect(view.detail).toBe(
      'calculated 2026-11-19 14:02Z · at attempt end + workflow step · methods changed: cost.total',
    );
  });
  it('omits methods changed when none', () => {
    expect(versionView(three, 2).detail).toBe(
      'calculated 2026-11-19 14:02Z · at attempt end + workflow step',
    );
  });
  it('keeps the last four and an overflow past five', () => {
    const seven = [1, 2, 3, 4, 5, 6, 7].map((n) => version(n));
    expect(versionView(seven, 7)).toMatchObject({
      segments: [4, 5, 6, 7],
      overflow: true,
      latest: 7,
    });
  });
  it('is empty for no versions and for an unknown selection', () => {
    expect(versionView([], 1)).toEqual({ segments: [], overflow: false, latest: null, detail: '' });
    expect(versionView(three, 9).detail).toBe('');
  });
});
