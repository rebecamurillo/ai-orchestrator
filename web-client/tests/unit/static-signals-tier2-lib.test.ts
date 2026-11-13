import { describe, expect, it } from 'vitest';

import {
  FINDING_IDS,
  FINDING_TOOLS,
  SEVERITIES,
  TEST_FIRST,
  TIER_2,
  TIER_2_IDS,
  cellWords,
  footerLines,
  hasAnalysisCode,
  isEmptyTier,
  staticTable,
  testFirstLine,
  tierThree,
} from '../../src/lib/metrics/static-signals';
import { entry } from './metrics-fixtures';
import { SECRETS, analysis, code } from './static-fixtures';
import {
  BUG,
  COVERAGE,
  F2P,
  FIRST,
  HELDOUT,
  LINT,
  SECURITY,
  firstEntry,
  opengrepAnalysis,
  run,
  stepEntry,
  tierEntries,
} from './static-tier-fixtures';

const entries = () =>
  Object.fromEntries(
    [...tierEntries(), firstEntry(), entry(SECRETS, { group: 'code' })].map((e) => [e.id, e]),
  );

describe('Tier 2 shape', () => {
  it('lists the seven Tier 2 ids in story order and maps the finding ids to a kind', () => {
    expect(TIER_2_IDS).toHaveLength(7);
    expect(TIER_2_IDS[0]).toBe(LINT);
    expect(TIER_2_IDS[6]).toBe(BUG);
    expect(FINDING_IDS[SECURITY]).toBe('security');
    expect(FINDING_IDS[BUG]).toBe('bug');
    expect(FINDING_TOOLS[SECURITY]).toBe('opengrep');
    expect(FINDING_TOOLS[BUG]).toBe('opengrep');
    expect(SEVERITIES).toEqual(['high', 'medium', 'low']);
  });

  it('puts Tier 2 rows in story order and keeps them out of Tier 1a', () => {
    const tiers = staticTable([], [analysis()], entries(), 'all');
    expect(tiers.map((t) => t.tier)).toEqual(['1a', '1b', '2']);
    expect(tiers[2]!.head).toBe(TIER_2);
    expect(tiers[2]!.scopes[0]!.rows.map((r) => r.metricId)).toEqual(TIER_2_IDS);
    expect(tiers[0]!.scopes[0]!.rows.map((r) => r.metricId)).toEqual([SECRETS]);
  });

  it('keeps the headline filter on Tier 2', () => {
    const e = entries();
    e[LINT] = entry(LINT, { group: 'code', level: 'H' });
    const tier = staticTable([], [], e, 'headline')[2]!;
    expect(tier.scopes[0]!.rows.map((r) => r.metricId)).toEqual([LINT]);
  });

  it('knows a tier with no cell at any scope', () => {
    const empty = staticTable([], [analysis()], entries(), 'all')[2]!;
    expect(isEmptyTier(empty)).toBe(true);
    const held = staticTable([run(LINT, null, '3')], [analysis()], entries(), 'all')[2]!;
    expect(isEmptyTier(held)).toBe(false);
  });
});

describe('cell words', () => {
  it('says possible after a severity and the source before any other', () => {
    expect(cellWords(SECURITY, 'high')).toEqual({ before: null, after: 'possible high' });
    expect(cellWords(BUG, 'fixed')).toEqual({ before: 'fixed', after: null });
    expect(cellWords(COVERAGE, 'covered')).toEqual({ before: 'covered', after: null });
    expect(cellWords(LINT, null)).toEqual({ before: null, after: null });
  });
});

describe('test-first line', () => {
  it('reads n of m from the stored figures', () => {
    expect(testFirstLine('6', '8')).toBe(
      'test-first order · method followed, not quality · 6 of 8 stories readable from the logs',
    );
  });
  it('falls back to the plain words', () => {
    const plain = 'test-first order · method followed, not quality';
    expect(testFirstLine(null, '8')).toBe(plain);
    expect(testFirstLine('6', null)).toBe(plain);
  });
});

describe('tier three', () => {
  const items = [
    run(FIRST, 'test_first', '4', { unit: 'stories' }),
    run(FIRST, 'readable', '6', { unit: 'stories' }),
    run(FIRST, 'stories', '8', { unit: 'stories' }),
    run(FIRST, 'story-x', '1', { scope_type: 'story', scope_key: 'stories[0]' }),
    run(HELDOUT, 'passed', '18'),
    run(HELDOUT, 'failed', '2'),
    run(HELDOUT, 'passed', '9', { scope_type: 'repository', scope_key: '.' }),
  ];

  it('keeps run-scope outcome cells apart from readable and stories', () => {
    const three = tierThree(items, [stepEntry()], 'all');
    expect(three.testFirst!.map((c) => c.source)).toEqual(['test_first']);
    expect(three.steps).toHaveLength(1);
    expect(three.steps[0]!.metricId).toBe(HELDOUT);
    expect(three.steps[0]!.cells.map((c) => c.source)).toEqual(['passed', 'failed']);
  });

  it('has no test-first cells without a run row and keeps a step entry without values', () => {
    const three = tierThree([], [stepEntry()], 'all');
    expect(three.testFirst).toBeNull();
    expect(three.steps).toEqual([{ metricId: HELDOUT, cells: [] }]);
  });

  it('drops a level A step from the headline set', () => {
    expect(tierThree(items, [stepEntry()], 'headline').steps).toEqual([]);
    expect(tierThree(items, [stepEntry({ level: 'H' })], 'headline').steps).toHaveLength(1);
  });

  it('counts analysis code without the test-first rows', () => {
    expect(hasAnalysisCode([run(FIRST, 'readable', '6')])).toBe(false);
    expect(hasAnalysisCode([run(FIRST, 'readable', '6'), code(SECRETS)])).toBe(true);
    expect(TEST_FIRST).toBe(FIRST);
  });
});

describe('footer rule pack line', () => {
  it('names the opengrep rule packs when an analysis holds one', () => {
    const lines = footerLines([
      opengrepAnalysis(),
      opengrepAnalysis({ rule_pack_hash: 'ffffffff00' }),
    ]);
    expect(lines[1]).toBe('rule packs: opengrep abcdef12/ffffffff');
  });
  it('keeps the Tier 1 sentence without one', () => {
    expect(footerLines([analysis()])[1]).toBe('rule packs: n/a — Tier 1 runs no rule pack');
    expect(F2P).toBe(TIER_2_IDS[4]);
  });
});
