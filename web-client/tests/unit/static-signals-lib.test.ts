import { describe, expect, it } from 'vitest';

import {
  detailLine,
  footerLines,
  lookupDate,
  notRunLine,
  sourceWord,
  splitCells,
  staticTable,
  tier1bHead,
  toolFlag,
  toolLine,
} from '../../src/lib/metrics/static-signals';
import { staticRows } from '../../src/lib/metrics/compare';
import { entry } from './metrics-fixtures';
import { A, B, C, metric } from './metrics-compare-fixtures';
import { DUP, SECRETS, SUPP, analysis, code, codeEntries } from './static-fixtures';

const entries = Object.fromEntries(codeEntries().map((e) => [e.id, e]));

describe('splitCells and sourceWord', () => {
  it('separates raw, rate and small-change cells in payload order', () => {
    const cells = [
      { source: 'test' },
      { source: 'per_100' },
      { source: 'test:per_100' },
      { source: 'small_change' },
      { source: null },
    ];
    const split = splitCells(cells);
    expect(split.raws).toEqual([{ source: 'test' }, { source: null }]);
    expect(split.rates).toHaveLength(2);
    expect(split.small).toEqual([{ source: 'small_change' }]);
  });
  it('words a source', () => {
    expect(sourceWord('test_unit:added')).toBe('test unit added');
    expect(sourceWord(null)).toBeNull();
  });
});

describe('heads, lines and footer', () => {
  it('words the tier-1b head and the not-run line', () => {
    expect(tier1bHead('2026-11-13')).toBe('TIER 1B · LOOKUPS 2026-11-13');
    expect(tier1bHead(null)).toBe('TIER 1B · LOOKUPS not run');
    expect(notRunLine(3)).toBe('not run in v3 · RECALCULATE METRICS runs it');
  });
  it('words every detail line variant', () => {
    expect(detailLine(analysis())).toBe(
      'Python, CSS · base bbbbbbb (merge base with main) → head hhhhhhh · head holds no commits outside this Run',
    );
    expect(detailLine(analysis({ commits_outside_run: 1 }))).toContain(
      'head holds 1 commit this Run did not make',
    );
    expect(detailLine(analysis({ commits_outside_run: 4 }))).toContain(
      'head holds 4 commits this Run did not make',
    );
    expect(
      detailLine(
        analysis({ commits_outside_run: null, languages: null, base: null, base_branch: null }),
      ),
    ).toBe(
      'languages not recorded · base — (merge base with —) → head hhhhhhh · commits outside this Run not recorded',
    );
    expect(detailLine(analysis({ status: 'failed', reason: 'commit missing: x' }))).toBe(
      'commit missing: x',
    );
  });
  it('prints tools, versions and dates in the footer', () => {
    const lines = footerLines([
      analysis(),
      analysis({
        repository_path: 'repos/app',
        declaration_hash: null,
        tools: [
          { tool: 'jscpd', version: '4.1.0' },
          { tool: 'other', version: '1' },
        ],
        lookup_date: null,
        vulnerability_db_date: null,
      }),
    ]);
    expect(lines[0]).toBe(
      'tools: gitleaks 8.30.1 · jscpd 4.0.5/4.1.0 · lizard 1.17 · osv-scanner 2.0 · other 1',
    );
    expect(lines[1]).toBe('rule packs: n/a — Tier 1 runs no rule pack');
    expect(lines[2]).toBe('vulnerability database 2026-11-12');
    expect(lines[3]).toBe('registry lookup 2026-11-13');
    expect(lines[4]).toBe('declaration orchestrator-analysis.yaml abcdef12/absent');
    expect(footerLines([analysis({ lookup_date: null })])[3]).toBe('registry lookup not run');
    expect(lookupDate([analysis({ lookup_date: null })])).toBeNull();
    expect(lookupDate([analysis(), analysis({ lookup_date: '2026-11-14' })])).toBe(
      '2026-11-13, 2026-11-14',
    );
  });
});

describe('staticTable', () => {
  const items = [
    code(SECRETS),
    code(SUPP, { source: 'production' }),
    code(SUPP, { source: 'per_100', missing: 'raw only', value_num: null }),
    code(DUP, { scope_type: 'repository', scope_key: 'repos/app' }),
  ];
  const analyses = [analysis(), analysis({ analysis_id: 'an-2', repository_path: 'repos/app' })];

  it('puts the Run row first, then each repository, per tier', () => {
    const [a, b] = staticTable(items, analyses, entries, 'all');
    expect(a.head).toBe('TIER 1A · OFFLINE');
    expect(b.head).toBe('TIER 1B · LOOKUPS 2026-11-13');
    expect(a.scopes.map((s) => s.name)).toEqual(['all repositories', '.', 'repos/app']);
    expect(a.scopes[0].detail).toBeNull();
    expect(a.scopes[1].detail).toContain('Python, CSS');
    expect(a.scopes[0].rows.map((r) => r.metricId)).toEqual([SECRETS, SUPP]);
    expect(a.scopes[0].rows[1].cells).toHaveLength(2);
    expect(a.scopes[1].rows[0].cells).toEqual([]);
    expect(b.scopes[2].rows.map((r) => r.metricId)).toEqual([DUP]);
    expect(b.scopes[2].rows[0].cells).toHaveLength(1);
  });
  it('keeps level H on the headline set', () => {
    const [a] = staticTable(items, analyses, entries, 'headline');
    expect(a.scopes[0].rows.map((r) => r.metricId)).toEqual([SECRETS]);
  });
});

describe('the comparison helpers', () => {
  const ids = [A, B, C];
  const differ = metric(DUP, ids, {
    tool_versions_differ: true,
    toolsets: {
      [A]: [
        { tool: 'jscpd', version: '4.0.5' },
        { tool: 'lizard', version: '1' },
      ],
      [B]: [
        { tool: 'jscpd', version: '4.1.0' },
        { tool: 'lizard', version: '1' },
      ],
      [C]: [
        { tool: 'jscpd', version: '4.1.0' },
        { tool: 'lizard', version: '1' },
      ],
    },
  });
  const runs = ids.map((run_id) => ({ run_id }));

  it('names the differing tool with the Runs of each version', () => {
    expect(toolFlag(differ, runs)).toBe(
      '≠ tool versions differ: jscpd 4.0.5 (Run 1) vs 4.1.0 (Runs 2, 3)',
    );
    expect(toolLine(differ, A)).toBe('jscpd 4.0.5');
    expect(toolLine(differ, C)).toBe('jscpd 4.1.0');
  });
  it('joins two differing tools', () => {
    const two = metric(DUP, [A, B], {
      tool_versions_differ: true,
      toolsets: {
        [A]: [
          { tool: 'jscpd', version: '1' },
          { tool: 'lizard', version: '1' },
        ],
        [B]: [
          { tool: 'jscpd', version: '2' },
          { tool: 'lizard', version: '2' },
        ],
      },
    });
    expect(toolFlag(two, runs)).toBe(
      '≠ tool versions differ: jscpd 1 (Run 1) vs 2 (Run 2); lizard 1 (Run 1) vs 2 (Run 2)',
    );
    expect(toolLine(two, B)).toBe('jscpd 2 · lizard 2');
  });
  it('is null without a flag or without a differing tool', () => {
    const same = metric(DUP, ids);
    expect(toolFlag(same, runs)).toBeNull();
    expect(toolLine(same, A)).toBeNull();
    const odd = metric(DUP, ids, { tool_versions_differ: true, toolsets: {} });
    expect(toolLine(odd, A)).toBeNull();
  });
  it('lists the code rows, headline keeping level H', () => {
    const rows = [
      metric(DUP, ids),
      metric(SUPP, ids),
      metric('cost.gateway', ids),
      metric('x', ids),
    ];
    const all = { ...entries, [SUPP]: entry(SUPP, { group: 'code', level: 'A' }) };
    expect(staticRows(all, rows, 'all').map((m) => m.metric_id)).toEqual([DUP, SUPP]);
    expect(staticRows(all, rows, 'headline').map((m) => m.metric_id)).toEqual([DUP]);
  });
});
