import { describe, expect, it } from 'vitest';

import type { components } from '../../src/api/schema';
import {
  anySubscription,
  compareHref,
  metricsHref,
  monthText,
  orderSpend,
  parseSelect,
  projectsCount,
  pruneSelection,
  runRowView,
  runToken,
  spendTarget,
  toggleSelection,
} from '../../src/lib/metrics/home';
import { entry } from './metrics-fixtures';

type Run = components['schemas']['MetricsRunOut'];
type Spend = components['schemas']['ProjectSpendOut'];

const run = (over: Partial<Run> = {}): Run => ({
  base_branch: 'main',
  branch: 'feat/x',
  gateway: '1.5',
  harness: 'claude',
  harness_spend: '2',
  id: 'abcdef12-0000-7000-8000-000000000001',
  label: 'Run A',
  label_set_by_operator: false,
  latest_version: 2,
  selectable: true,
  status: 'done',
  subscription: null,
  template_name: 'story',
  template_version: 3,
  wall_clock_seconds: 3700,
  ...over,
});

const spend = (id: string, over: Partial<Spend> = {}): Spend => ({
  cancelled: { gateway: '0.5', harness: '0.25', runs: 1 },
  gateway: '10',
  gateway_reported: true,
  harness: '5',
  harness_reported: true,
  project_id: id,
  project_name: `P ${id}`,
  runs: 4,
  subscription: null,
  ...over,
});

describe('monthText / projectsCount', () => {
  it('formats the UTC month', () => {
    expect(monthText(new Date('2026-11-30T23:59:59Z'))).toBe('2026-11');
    expect(monthText(new Date('2026-12-01T00:00:00Z'))).toBe('2026-12');
  });
  it('counts projects', () => {
    expect(projectsCount(1)).toBe('1 project');
    expect(projectsCount(0)).toBe('0 projects');
    expect(projectsCount(3)).toBe('3 projects');
  });
});

describe('selection', () => {
  it('parses, trims, de-duplicates and keeps order', () => {
    expect(parseSelect(null)).toEqual([]);
    expect(parseSelect('')).toEqual([]);
    expect(parseSelect('b, a,,b,c')).toEqual(['b', 'a', 'c']);
  });
  it('prunes to selectable runs of the list', () => {
    const runs = [run({ id: 'a' }), run({ id: 'b', selectable: false })];
    expect(pruneSelection(['b', 'x', 'a'], runs)).toEqual(['a']);
  });
  it('toggles in tick order', () => {
    expect(toggleSelection(['a'], 'b')).toEqual(['a', 'b']);
    expect(toggleSelection(['a', 'b'], 'a')).toEqual(['b']);
  });
  it('builds hrefs', () => {
    expect(metricsHref(null, [])).toBe('/metrics');
    expect(metricsHref('p', [])).toBe('/metrics?project=p');
    expect(metricsHref('p', ['a', 'b'])).toBe('/metrics?project=p&select=a,b');
    expect(compareHref(['a', 'b'])).toBe('/metrics/compare?runs=a,b');
  });
});

describe('runToken', () => {
  it.each([
    ['queued', 'QUE'],
    ['running', 'RUN'],
    ['needs_you', 'BLK'],
    ['done', 'DON'],
    ['failed', 'ERR'],
    ['cancelled', 'CAN'],
    ['weird', 'QUE'],
  ])('%s → %s', (status, token) => expect(runToken(status)).toBe(token));
});

describe('runRowView', () => {
  it('shapes an ended run', () => {
    const v = runRowView(run());
    expect(v).toMatchObject({
      select: 'box',
      token: 'DON',
      shortId: 'abcdef12',
      href: '/workflows/abcdef12-0000-7000-8000-000000000001',
      template: 'story@3',
      harness: 'claude',
      baseBranch: 'main → feat/x',
      wallClock: '1h 01m',
      gateway: '$1.50',
      harnessSpend: '$2.00',
      version: 'v2',
      ownLabel: false,
    });
  });
  it('marks running and needs_you rows', () => {
    const v = runRowView(run({ status: 'running', selectable: false, latest_version: null }));
    expect(v.select).toBe('running');
    expect(v.version).toBe('values so far');
    expect(runRowView(run({ status: 'needs_you', selectable: false })).select).toBe('running');
  });
  it('reads no result version and dashes', () => {
    const v = runRowView(
      run({
        selectable: false,
        status: 'failed',
        latest_version: null,
        harness: null,
        base_branch: null,
        branch: null,
        wall_clock_seconds: null,
        label_set_by_operator: true,
      }),
    );
    expect(v).toMatchObject({
      select: 'none',
      version: 'no result version',
      harness: '—',
      baseBranch: '— → —',
      wallClock: '—',
      ownLabel: true,
    });
    expect(
      runRowView(run({ selectable: false, status: 'queued', latest_version: null })).version,
    ).toBe('—');
    expect(runRowView(run({ selectable: false, latest_version: 1 })).version).toBe('v1');
  });
});

describe('spend', () => {
  it('orders the chosen project first', () => {
    const items = [spend('a'), spend('b'), spend('c')];
    expect(orderSpend(items, 'b').map((i) => i.project_id)).toEqual(['b', 'a', 'c']);
    expect(orderSpend(items, null).map((i) => i.project_id)).toEqual(['a', 'b', 'c']);
    expect(orderSpend(items, 'zzz').map((i) => i.project_id)).toEqual(['a', 'b', 'c']);
  });
  it('detects subscriptions', () => {
    expect(anySubscription([spend('a'), spend('b', { subscription: false })])).toBe(false);
    expect(anySubscription([spend('a'), spend('b', { subscription: true })])).toBe(true);
  });
  it('re-shapes a payload field into an origin target', () => {
    const item = spend('a', { subscription: true });
    const t = spendTarget(item, 'spend.month', '10', entry('spend.month'));
    expect(t).toMatchObject({
      runLabel: 'P a',
      projectName: 'P a',
      version: null,
      latest: null,
      subscription: true,
      value: {
        metric_id: 'spend.month',
        method_id: 'spend.month@2',
        scope_type: 'project',
        scope_key: 'a',
        scope_label: 'P a',
        unit: 'USD',
        value_num: '10',
        origin: null,
        missing: null,
      },
    });
  });
  it('falls back without an entry', () => {
    const t = spendTarget(spend('a'), 'cost.harness', '5', null);
    expect(t.value.method_id).toBe('cost.harness');
    expect(t.subscription).toBe(false);
  });
});
