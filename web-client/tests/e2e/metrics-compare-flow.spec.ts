import { readFile } from 'node:fs/promises';

import { expect, test, type Download, type Page, type Route } from '@playwright/test';

import { SPEND_ID } from './projects-fixtures.mjs';

/**
 * Epic 4 of orchestrator-run-metrics, end to end in the built web-client: the Metrics rail
 * item and `/metrics` (Runs table, selection in the URL, spend this month), then
 * `/metrics/compare` in TABLE view (method headers, remove, blind, export) and in CHART view
 * (TOTAL dot plot, ROLE breakdown, ROLE FAMILY flag, follow a Run, PNG per chart and all).
 *
 * The stub backend holds no `/metrics/*` route, so every metrics read is answered with
 * `page.route()` from fixtures this spec owns (the `run-detail-metrics.spec.ts` precedent).
 * The comparison payload is built from the request's own `runs` and `blind`, so a remove or
 * a blind toggle reads what a real backend would return for that query.
 */

const PROJECT_ID = '0199aaaa-0000-7000-8000-000000000001';
const OTHER_PROJECT_ID = '0199bbbb-0000-7000-8000-000000000002';
const PROJECT = 'familio';

const RUN_A = 'a1a1a1a1-0000-7000-8000-00000000000a';
const RUN_B = 'b2b2b2b2-0000-7000-8000-00000000000b';
const RUN_C = 'c3c3c3c3-0000-7000-8000-00000000000c';
const RUN_LIVE = 'd4d4d4d4-0000-7000-8000-00000000000d';

const HIDDEN = 'hidden · blind';
const TODAY = new Date().toISOString().slice(0, 10);

// ---------------------------------------------------------------- catalogue

const CATALOGUE_ROWS: [id: string, label: string, group: string, unit: string, level: string][] = [
  ['cost.gateway', 'gateway cost', 'cost', 'USD', 'H'],
  ['cost.harness', 'harness cost', 'cost', 'USD', 'H'],
  ['tokens.output', 'output tokens', 'tokens', 'tokens', 'H'],
  ['tokens.cache_read', 'cache read tokens', 'tokens', 'tokens', 'H'],
  ['tokens.cache_hit_share', 'cache hit share', 'tokens', 'ratio', 'A'],
  ['time.machine', 'machine time', 'time', 'seconds', 'H'],
  ['time.parked', 'waiting on you', 'time', 'seconds', 'H'],
  ['process.attempts', 'attempts', 'process', 'count', 'H'],
  ['process.retries', 'retries', 'process', 'count', 'H'],
  ['spend.month', 'spend this month', 'spend', 'USD', 'H'],
  ['spend.month_cancelled', 'cancelled spend this month', 'spend', 'USD', 'H'],
];

const CATALOGUE = {
  items: CATALOGUE_ROWS.map(([id, label, group, unit, level]) => ({
    additive: true,
    component_of: null,
    fingerprint_group: false,
    group,
    id,
    label,
    level,
    limits: null,
    methods: [{ description: `method text of ${id}`, n: 1, parameters: {} }],
    missing_words: ['not recorded', 'not available'],
    scopes: ['run', 'role', 'model'],
    source: `source text of ${id}`,
    unit,
  })),
};
/** The comparison payload's metrics: the catalogue's run metrics, spend excluded. */
const COMPARED = CATALOGUE_ROWS.filter(([id]) => !id.startsWith('spend.'));
const HEADLINE_COUNT = COMPARED.filter(([, , , , level]) => level === 'H').length;

// ---------------------------------------------------------------- /metrics home

function metricsRun(id: string, over: Record<string, unknown>): Record<string, unknown> {
  return {
    id,
    label: `label of ${id.slice(0, 8)}`,
    label_set_by_operator: false,
    status: 'done',
    selectable: true,
    template_name: 'initiative-hub-story',
    template_version: 3,
    harness: 'claude',
    base_branch: 'main',
    branch: `feat/${id.slice(0, 4)}`,
    wall_clock_seconds: 5400,
    gateway: '15.35',
    harness_spend: '16.01',
    latest_version: 2,
    subscription: false,
    ...over,
  };
}

const HOME_RUNS = [
  metricsRun(RUN_LIVE, {
    label: 'snake bench live',
    status: 'running',
    selectable: false,
    latest_version: null,
  }),
  metricsRun(RUN_A, { label: 'snake bench staged', label_set_by_operator: true }),
  metricsRun(RUN_B, { label: 'snake bench direct', status: 'failed', latest_version: 1 }),
];

const spendRow = (id: string, name: string, gateway: string, harness: string) => ({
  project_id: id,
  project_name: name,
  gateway,
  gateway_reported: true,
  harness,
  harness_reported: true,
  runs: 4,
  cancelled: { gateway: '1.25', harness: '1.40', runs: 1 },
  subscription: name === PROJECT,
});

// listed other-project first: the page puts the chosen project's row first itself
const SPEND = {
  items: [
    spendRow(OTHER_PROJECT_ID, 'orchestrator', '7.10', '7.30'),
    spendRow(PROJECT_ID, PROJECT, '42.50', '44.75'),
  ],
  next_cursor: null,
};

// ---------------------------------------------------------------- /metrics/compare

interface RunFixture {
  label: string;
  template: [string, string];
  models: Record<string, string[]>;
  baseCommit: string;
  values: Record<string, string>;
  /** Role → [gateway, harness, output tokens]; a template without the role has no entry. */
  roles: Record<string, [string, string, string]>;
  method: number;
}

const RUNS: Record<string, RunFixture> = {
  [RUN_A]: {
    label: 'snake bench staged',
    template: ['initiative-hub-story', '3'],
    models: { implement: ['claude-opus-5-5'], review: ['claude-sonnet-5-5'] },
    baseCommit: 'aaaa1111'.repeat(5),
    values: {
      'cost.gateway': '15.35',
      'cost.harness': '16.01',
      'tokens.output': '42000',
      'tokens.cache_read': '900000',
      'tokens.cache_hit_share': '0.91',
      'time.machine': '3600',
      'time.parked': '600',
      'process.attempts': '6',
      'process.retries': '1',
    },
    roles: { implement: ['10.00', '10.40', '30000'], review: ['5.35', '5.61', '12000'] },
    method: 1,
  },
  [RUN_B]: {
    label: 'snake bench direct',
    template: ['initiative-hub-story', '3'],
    models: { implement: ['claude-opus-5-5'], review: ['claude-opus-5-5'] },
    baseCommit: 'aaaa1111'.repeat(5),
    values: {
      'cost.gateway': '12.00',
      'cost.harness': '12.50',
      'tokens.output': '38000',
      'tokens.cache_read': '700000',
      'tokens.cache_hit_share': '0.88',
      'time.machine': '3000',
      'time.parked': '300',
      'process.attempts': '5',
      'process.retries': '0',
    },
    roles: { implement: ['8.00', '8.20', '28000'], review: ['4.00', '4.30', '10000'] },
    method: 2,
  },
  [RUN_C]: {
    label: 'snake bench solo',
    template: ['story', '2'],
    models: { implement: ['claude-opus-5-5'] },
    baseCommit: 'cccc2222'.repeat(5),
    values: {
      'cost.gateway': '18.00',
      'cost.harness': '18.90',
      'tokens.output': '51000',
      'tokens.cache_read': '1200000',
      'tokens.cache_hit_share': '0.93',
      'time.machine': '4200',
      'time.parked': '0',
      'process.attempts': '4',
      'process.retries': '0',
    },
    roles: { implement: ['18.00', '18.90', '51000'] },
    method: 1,
  },
};

const unitOf = (metricId: string): string => COMPARED.find(([id]) => id === metricId)?.[3] ?? 'USD';

function cell(
  metricId: string,
  scope: 'run' | 'role',
  key: string,
  value: string,
  method = 1,
): Record<string, unknown> {
  return {
    attempt_n: null,
    carried_from: null,
    method_id: `${metricId}@${method}`,
    missing: null,
    model: null,
    partial_m: null,
    partial_n: null,
    repository: null,
    role: scope === 'role' ? key : null,
    scope_key: key,
    scope_label: null,
    scope_type: scope,
    source: null,
    unit: unitOf(metricId),
    value_num: value,
  };
}

const ROLE_SLOT: Record<string, number> = {
  'cost.gateway': 0,
  'cost.harness': 1,
  'tokens.output': 2,
};

function header(id: string, position: number, blind: boolean): Record<string, unknown> {
  const run = RUNS[id]!;
  return {
    run_id: id,
    short_id: id.slice(0, 8),
    label: blind ? `R${position}` : run.label,
    label_set_by_operator: false,
    template_name: blind ? HIDDEN : run.template[0],
    template_version: blind ? HIDDEN : run.template[1],
    harness: 'claude',
    models_by_role: blind
      ? Object.fromEntries(Object.keys(run.models).map((r) => [r, [HIDDEN]]))
      : run.models,
    base_branch: 'main',
    status: 'done',
    stories_done: { done: 3, planned: 3 },
    selected_version: 2,
    versions_available: [1, 2],
    subscription: false,
  };
}

function metric(metricId: string, ids: string[]): Record<string, unknown> {
  const machine = metricId === 'time.machine';
  const methods = Object.fromEntries(
    ids.map((id) => [id, [`${metricId}@${machine ? RUNS[id]!.method : 1}`]]),
  );
  const slot = ROLE_SLOT[metricId];
  const cells = Object.fromEntries(
    ids.map((id) => {
      const run = RUNS[id]!;
      const own = cell(metricId, 'run', id, run.values[metricId]!, machine ? run.method : 1);
      const roles =
        slot === undefined
          ? []
          : Object.entries(run.roles).map(([role, v]) => cell(metricId, 'role', role, v[slot]));
      return [id, [own, ...roles]];
    }),
  );
  const families =
    slot === undefined
      ? []
      : [
          {
            family: 'story work',
            source: null,
            step_structure_differs: true,
            cells: Object.fromEntries(
              ids.map((id) => [
                id,
                {
                  value_num: RUNS[id]!.values[metricId]!,
                  missing: null,
                  roles: Object.keys(RUNS[id]!.roles),
                },
              ]),
            ),
          },
        ];
  const harnessDelta =
    metricId === 'cost.harness'
      ? Object.fromEntries(
          ids.map((id) => {
            const run = RUNS[id]!;
            const gap = Number(run.values['cost.harness']) - Number(run.values['cost.gateway']);
            return [id, `+$${gap.toFixed(2)} vs gateway`];
          }),
        )
      : {};
  const distinct = new Set(Object.values(methods).map((m) => m[0]));
  return {
    metric_id: metricId,
    cells,
    methods,
    methods_differ: distinct.size > 1,
    harness_delta: harnessDelta,
    families,
  };
}

function comparePayload(ids: string[], blind: boolean): Record<string, unknown> {
  const commits = new Set(ids.map((id) => RUNS[id]!.baseCommit));
  return {
    project_id: PROJECT_ID,
    project_name: PROJECT,
    runs: ids.map((id, i) => header(id, i + 1, blind)),
    same_work: {
      differs: commits.size > 1,
      runs: Object.fromEntries(
        ids.map((id) => [
          id,
          {
            base_commits: { 'my-family-app': RUNS[id]!.baseCommit },
            initiative_folder: 'initiatives/snake',
            stories_planned: 3,
          },
        ]),
      ),
    },
    metrics: COMPARED.map(([id]) => metric(id, ids)),
    diff_size: Object.fromEntries(ids.map((id) => [id, 'not run'])),
  };
}

function exportJson(ids: string[], blind: boolean): Record<string, unknown> {
  const runs = ids.map((id, i) => header(id, i + 1, blind));
  return {
    runs,
    rows: ids.flatMap((id, i) =>
      COMPARED.map(([metricId]) => ({
        run_id: id,
        run_label: blind ? `R${i + 1}` : RUNS[id]!.label,
        metric_id: metricId,
        value_num: RUNS[id]!.values[metricId],
      })),
    ),
    // the export is the server's full list, whatever the page shows
    catalogue: CATALOGUE.items.filter((e) => !e.id.startsWith('spend.')),
  };
}

// ---------------------------------------------------------------- routing

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

interface Backend {
  compareUrls: URL[];
  exportUrls: URL[];
}

async function mockBackend(page: Page): Promise<Backend> {
  const backend: Backend = { compareUrls: [], exportUrls: [] };
  await page.route('**/api/metrics/catalogue*', (route) => json(route, CATALOGUE));
  await page.route('**/api/metrics/spend*', (route) => json(route, SPEND));
  await page.route('**/api/metrics/runs*', (route) => {
    const project = new URL(route.request().url()).searchParams.get('project');
    return json(route, { items: project === PROJECT_ID ? HOME_RUNS : [], next_cursor: null });
  });
  await page.route('**/api/metrics/compare**', (route) => {
    const url = new URL(route.request().url());
    const ids = (url.searchParams.get('runs') ?? '').split(',').filter((id) => id in RUNS);
    const blind = url.searchParams.get('blind') === 'true';
    if (url.pathname.endsWith('/compare')) {
      backend.compareUrls.push(url);
      return json(route, comparePayload(ids, blind));
    }
    backend.exportUrls.push(url);
    if (url.pathname.endsWith('/compare.csv')) {
      return route.fulfill({
        status: 200,
        contentType: 'text/csv',
        headers: {
          'Content-Disposition': `attachment; filename="${PROJECT}-compare-${TODAY}.csv"`,
        },
        body: 'run_id,run_label,result_version,metric_id\n',
      });
    }
    return route.fulfill({
      status: 200,
      contentType: 'application/json',
      headers: {
        'Content-Disposition': `attachment; filename="${PROJECT}-compare-${TODAY}.json"`,
      },
      body: JSON.stringify(exportJson(ids, blind)),
    });
  });
  // CHART reads the first Run's detail only to order roles by its plan
  await page.route('**/api/runs/*/detail', (route) => json(route, { steps: [] }));
  return backend;
}

/** Every download the page starts while `action` runs, in order. */
async function downloadsDuring(
  page: Page,
  expected: number,
  action: () => Promise<void>,
): Promise<Download[]> {
  const seen: Download[] = [];
  const listener = (d: Download) => seen.push(d);
  page.on('download', listener);
  await action();
  await expect.poll(() => seen.length, { timeout: 15_000 }).toBe(expected);
  page.off('download', listener);
  return seen;
}

async function expectPng(download: Download): Promise<void> {
  const png = await readFile(await download.path());
  expect(png.subarray(1, 4).toString('ascii')).toBe('PNG');
  // IHDR width: 820 px export at scale 2
  expect(png.readUInt32BE(16)).toBe(1640);
}

const compareUrl = (ids: string[], extra = '') => `/metrics/compare?runs=${ids.join(',')}${extra}`;
const columns = (page: Page) => page.getByTestId(/^compare-col-/);

// ---------------------------------------------------------------- tests

test.describe('/metrics — rail, Runs table, selection and spend (epic 4 story 2)', () => {
  test('the rail reads Workflows, Runs, Metrics, then CONFIGURE Projects, Templates', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto('/metrics');

    const rail = page.getByRole('navigation', { name: 'Surfaces' });
    await expect(rail.getByRole('link')).toHaveText([
      /^Workflows/,
      /^Runs/,
      /^Metrics/,
      /^Projects/,
      /^Templates/,
    ]);
    await expect(rail).toHaveText(/Metrics.*CONFIGURE.*Projects/s);
    await expect(rail.getByRole('link', { name: 'Metrics' })).toHaveAttribute(
      'aria-current',
      'page',
    );
    await expect(page.getByTestId('surface-title')).toHaveText('METRICS');

    await expect(page.getByTestId('metrics-runs')).toContainText(
      'choose a project above to list its Runs',
    );
    await expect(page.getByTestId('metrics-runs-table')).toHaveCount(0);
  });

  test('pick two ended Runs, compare them, and the selection stays in the URL', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(`/metrics?project=${PROJECT_ID}`);

    const table = page.getByTestId('metrics-runs-table');
    await expect(table.getByRole('checkbox')).toHaveCount(2);
    const live = page.getByTestId(`metrics-run-row-${RUN_LIVE}`);
    await expect(live).toContainText('running');
    await expect(live).toContainText('values so far');
    await expect(live.getByRole('checkbox')).toHaveCount(0);
    await expect(page.getByTestId(`metrics-run-row-${RUN_A}`)).toContainText('your label');

    const compare = page.getByTestId('metrics-compare');
    await expect(compare).toHaveText('COMPARE 0 RUNS');
    await expect(compare).toBeDisabled();

    await page.getByRole('checkbox', { name: 'select snake bench staged' }).click();
    await expect(compare).toHaveText('COMPARE 1 RUNS');
    await expect(compare).toBeDisabled();
    await expect(page).toHaveURL(`/metrics?project=${PROJECT_ID}&select=${RUN_A}`);

    await page.getByRole('checkbox', { name: 'select snake bench direct' }).click();
    const link = page.getByRole('link', { name: 'COMPARE 2 RUNS' });
    await expect(link).toHaveAttribute('href', `/metrics/compare?runs=${RUN_A},${RUN_B}`);
    await expect(page.getByTestId('metrics-selection-count')).toHaveText('2 selected');
    await expect(page).toHaveURL(`/metrics?project=${PROJECT_ID}&select=${RUN_A},${RUN_B}`);

    // the URL is the selection: a reload comes back with both ticked
    await page.reload();
    await expect(page.getByRole('checkbox', { name: 'select snake bench staged' })).toHaveAttribute(
      'aria-checked',
      'true',
    );
    await expect(page.getByRole('checkbox', { name: 'select snake bench direct' })).toHaveAttribute(
      'aria-checked',
      'true',
    );

    await link.click();
    await expect(page).toHaveURL(`/metrics/compare?runs=${RUN_A},${RUN_B}`);
    await expect(page.getByTestId('surface-title')).toHaveText('COMPARE');
    await expect(columns(page)).toHaveCount(2);

    await page.goBack();
    await page.getByTestId('metrics-clear').click();
    await expect(page.getByTestId('metrics-selection-count')).toHaveText('0 selected');
    await expect(page).toHaveURL(`/metrics?project=${PROJECT_ID}`);
  });

  test('spend this month lists the chosen project first with cancelled figures', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(`/metrics?project=${PROJECT_ID}`);

    const spend = page.getByTestId('metrics-spend');
    await expect(spend.getByRole('heading')).toHaveText(`SPEND THIS MONTH · ${TODAY.slice(0, 7)}`);
    const rows = page.getByTestId('metrics-spend-table').locator('tbody tr');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0)).toHaveAttribute('data-testid', `metrics-spend-row-${PROJECT_ID}`);
    await expect(rows.nth(0)).toHaveAttribute('data-current', 'true');
    await expect(rows.nth(0)).toContainText(PROJECT);
    await expect(rows.nth(0)).toContainText('$42.50');
    await expect(rows.nth(0)).toContainText('$44.75');
    await expect(rows.nth(0)).toContainText('$1.25');
    await expect(rows.nth(0)).toContainText('$1.40');
    await expect(rows.nth(1)).toContainText('orchestrator');
    await expect(page.getByTestId('metrics-spend-list-price')).toHaveText('list-price equivalent');
    // every head carries a hint
    await expect(
      page
        .getByTestId('metrics-spend-table')
        .getByRole('button', { name: /^how .* is calculated$/ }),
    ).toHaveCount(4);
  });

  test('the project page links to its metrics', async ({ page }) => {
    await mockBackend(page);
    await page.goto(`/projects?id=${SPEND_ID}`);

    await page.getByRole('link', { name: 'metrics for this project' }).click();
    await expect(page).toHaveURL(`/metrics?project=${SPEND_ID}`);
    await expect(page.getByTestId('metrics-runs-table')).toBeVisible();
  });
});

test.describe('/metrics/compare TABLE — headers, remove, blind, export (epic 4 story 3)', () => {
  test('three Runs: three columns in selection order with their method headers', async ({
    page,
  }) => {
    const backend = await mockBackend(page);
    await page.goto(compareUrl([RUN_B, RUN_A, RUN_C]));

    await expect(columns(page)).toHaveCount(3);
    await expect(columns(page).nth(0)).toHaveAttribute('data-testid', `compare-col-${RUN_B}`);
    await expect(columns(page).nth(1)).toHaveAttribute('data-testid', `compare-col-${RUN_A}`);
    await expect(columns(page).nth(2)).toHaveAttribute('data-testid', `compare-col-${RUN_C}`);
    expect(backend.compareUrls[0]?.searchParams.get('runs')).toBe(`${RUN_B},${RUN_A},${RUN_C}`);

    const a = page.getByTestId(`compare-col-${RUN_A}`);
    for (const field of [
      RUN_A.slice(0, 8),
      'snake bench staged',
      'initiative-hub-story@3',
      'claude',
      'implement: claude-opus-5-5',
      'review: claude-sonnet-5-5',
      'base main',
      'done',
      '3/3 stories',
    ]) {
      await expect(a).toContainText(field);
    }
    await expect(a.getByRole('button', { name: 'v2 latest' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByTestId(`compare-col-${RUN_C}`)).toContainText('story@2');

    await expect(page.getByTestId('compare-same-work')).toContainText('≠ the work differs');
    const machine = page.getByTestId('compare-row-time.machine');
    await expect(machine.getByRole('rowheader')).toContainText('≠ methods differ');
    await expect(page.getByTestId(`compare-cell-time.machine-${RUN_B}`)).toContainText(
      'time.machine@2',
    );
    await expect(page.getByTestId(`compare-cell-cost.harness-${RUN_A}`)).toContainText(
      '+$0.66 vs gateway',
    );
    await expect(page.getByTestId(`compare-diff-size-${RUN_C}`)).toContainText('not run');
    await expect(page.getByTestId(`compare-diff-size-${RUN_C}`).getByRole('link')).toHaveAttribute(
      'href',
      `/workflows/${RUN_C}?tab=metrics&recalculate=1`,
    );
  });

  test('remove on the second column leaves two and updates the URL', async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C]));
    await expect(columns(page)).toHaveCount(3);

    await page.getByTestId(`compare-remove-${RUN_B}`).click();

    await expect(columns(page)).toHaveCount(2);
    await expect(page.getByTestId(`compare-col-${RUN_B}`)).toHaveCount(0);
    await expect(page).toHaveURL(compareUrl([RUN_A, RUN_C]));
    expect(backend.compareUrls.at(-1)?.searchParams.get('runs')).toBe(`${RUN_A},${RUN_C}`);
    // two is the floor: neither remaining column can be removed
    await expect(page.getByTestId(`compare-remove-${RUN_A}`)).toBeDisabled();
    await expect(page.getByTestId('compare-add-runs')).toHaveAttribute(
      'href',
      `/metrics?project=${PROJECT_ID}&select=${RUN_A},${RUN_C}`,
    );
  });

  test('blind re-requests with blind=true and the header shows R1, R2, R3', async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C]));
    await expect(columns(page).nth(0)).toContainText('snake bench staged');

    const blind = page.getByRole('switch', { name: 'blind' });
    await expect(blind).toHaveAttribute('aria-checked', 'false');
    await blind.click();
    await expect(blind).toHaveAttribute('aria-checked', 'true');

    await expect(columns(page).nth(0)).toContainText('R1');
    await expect(columns(page).nth(1)).toContainText('R2');
    await expect(columns(page).nth(2)).toContainText('R3');
    await expect(columns(page).nth(0)).toContainText(HIDDEN);
    await expect(page.getByTestId('compare-grid')).not.toContainText('snake bench');
    await expect(page.getByTestId('compare-grid')).not.toContainText('initiative-hub-story');
    expect(backend.compareUrls.at(-1)?.searchParams.get('blind')).toBe('true');
    await expect(page).toHaveURL(`${compareUrl([RUN_A, RUN_B, RUN_C])}&blind=1`);
  });

  test('export saves the CSV and JSON of the full query, with ALL METRICS off', async ({
    page,
  }) => {
    const backend = await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C]));

    await expect(page.getByRole('button', { name: 'HEADLINE' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    // the page shows the headline rows only; the export is every metric
    await expect(page.getByTestId(/^compare-row-(cost|tokens|time|process)\./)).toHaveCount(
      HEADLINE_COUNT,
    );

    const downloads = await downloadsDuring(page, 2, () =>
      page.getByRole('button', { name: 'EXPORT CSV + JSON' }).click(),
    );
    expect(downloads.map((d) => d.suggestedFilename()).sort()).toEqual([
      `${PROJECT}-compare-${TODAY}.csv`,
      `${PROJECT}-compare-${TODAY}.json`,
    ]);
    await expect(page.getByTestId('compare-export-line')).toHaveText(
      `exported ${PROJECT}-compare-${TODAY}.csv and .json · 3 Runs · ${COMPARED.length} metrics · ` +
        'run labels included · each description once',
    );

    expect(backend.exportUrls.map((u) => u.pathname.split('/').pop()).sort()).toEqual([
      'compare.csv',
      'compare.json',
    ]);
    for (const url of backend.exportUrls) {
      expect(url.searchParams.get('runs')).toBe(`${RUN_A},${RUN_B},${RUN_C}`);
      expect(url.searchParams.has('metrics')).toBe(false);
      expect(url.searchParams.has('blind')).toBe(false);
    }
    const saved = JSON.parse(
      await readFile(
        await downloads.find((d) => d.suggestedFilename().endsWith('.json'))!.path(),
        'utf8',
      ),
    ) as { catalogue: unknown[] };
    expect(saved.catalogue).toHaveLength(COMPARED.length);
  });

  test('a blind export carries blind=true and says run labels hidden', async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto(`${compareUrl([RUN_A, RUN_B])}&blind=1`);
    await expect(columns(page).nth(0)).toContainText('R1');

    await downloadsDuring(page, 2, () =>
      page.getByRole('button', { name: 'EXPORT CSV + JSON' }).click(),
    );
    await expect(page.getByTestId('compare-export-line')).toContainText('run labels hidden');
    expect(backend.exportUrls).toHaveLength(2);
    for (const url of backend.exportUrls) expect(url.searchParams.get('blind')).toBe('true');
  });
});

test.describe('/metrics/compare CHART — breakdowns, follow, PNG (epic 4 story 4)', () => {
  test('TOTAL draws cost as a dot plot off zero and every other chart from zero', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C]));
    await page.getByRole('button', { name: 'CHART' }).click();
    await expect(page).toHaveURL(`${compareUrl([RUN_A, RUN_B, RUN_C])}&view=chart`);

    await expect(page.getByRole('button', { name: 'TOTAL' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    const cost = page.getByRole('figure', { name: 'cost · gateway and harness' });
    await expect(cost).toContainText('axis does not start at zero');
    await expect(cost.locator('circle[data-series="gateway"]')).toHaveCount(3);
    await expect(cost.locator('circle[data-series="harness"]')).toHaveCount(3);
    await expect(cost).toContainText('$15.35 · $16.01');

    const others = page.getByRole('figure').filter({ hasNot: page.locator('circle[data-series]') });
    await expect(others).toHaveCount(4);
    for (const figure of await others.all()) {
      await expect(figure).not.toContainText('axis does not start at zero');
      // the first tick label is the axis origin
      await expect(figure.locator('svg > g > text').first()).toHaveText(/^0(h 00m)?$/);
    }
    await expect(cost.locator('svg > g > text').first()).not.toHaveText(/^\$0$/);
  });

  test('ROLE: a missing role reads its words with no mark, machine time is not split', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C], '&view=chart'));
    await page.getByRole('button', { name: 'ROLE', exact: true }).click();

    const byRole = page.getByRole('figure', { name: 'cost by role · gateway and harness' });
    await expect(byRole).toBeVisible();
    await expect(byRole.getByTestId('chart-group-review')).toBeVisible();
    await expect(byRole.getByText('no such step in this template')).toHaveCount(1);
    // R3 (the `story` template) has implement only: two marks, never a review pair
    await expect(byRole.getByRole('button', { name: /^snake bench solo R3 / })).toHaveCount(2);
    await expect(byRole.getByRole('button', { name: /^snake bench staged R1 / })).toHaveCount(4);
    await expect(byRole.getByTestId('chart-run-key')).toContainText(
      `R3 · snake bench solo · ${RUN_C.slice(0, 8)}`,
    );

    await expect(page.getByTestId('compare-not-split')).toHaveText(
      'not split by role: machine time, waiting on you, your interventions, budget, every static signal on the change',
    );
    await expect(page.getByRole('figure', { name: /machine time/ })).toHaveCount(0);

    await page.getByRole('button', { name: 'ROLE FAMILY (proposal)' }).click();
    const family = page.getByRole('figure', {
      name: 'cost by role · gateway and harness · role family',
    });
    await expect(family.getByTestId('chart-flag')).toContainText('≠ step structure differs');
    await expect(family.getByTestId('chart-flag')).toContainText(
      'story work: R1 implement · review; R2 implement · review; R3 implement',
    );
  });

  test('following a Run outlines it in every chart, and its PNG downloads', async ({ page }) => {
    await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C], '&view=chart'));

    const figures = page.getByRole('figure');
    await expect(figures).toHaveCount(5);
    await page.getByTestId(`chart-run-${RUN_B}`).first().click();

    await expect(page.getByTestId('compare-following')).toHaveText(
      'following: snake bench direct · click again to stop',
    );
    for (const figure of await figures.all()) {
      await expect(figure.getByTestId(`chart-run-${RUN_B}`)).toHaveAttribute(
        'aria-pressed',
        'true',
      );
      await expect(figure.locator('[data-follow="1"]').first()).toBeVisible();
    }

    const control = page.getByRole('button', { name: 'PNG output tokens' });
    const [download] = await downloadsDuring(page, 1, () => control.click());
    expect(download!.suggestedFilename()).toBe(`${PROJECT}-compare-output-tokens-${TODAY}.png`);
    await expectPng(download!);
    await expect(page.getByTestId('compare-png-failed')).toHaveCount(0);

    await page.getByTestId(`chart-run-${RUN_B}`).first().click();
    await expect(page.getByTestId('compare-following')).toHaveText('');
    await expect(page.locator('[data-follow="1"]')).toHaveCount(0);
  });

  test('PNG · all charts writes one file per chart', async ({ page }) => {
    await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C], '&view=chart&metrics=all'));

    const figures = page.getByRole('figure');
    await expect(figures).toHaveCount(6);
    const titles = await figures.evaluateAll((els) => els.map((e) => e.getAttribute('aria-label')));

    const downloads = await downloadsDuring(page, 6, () =>
      page.getByRole('button', { name: 'PNG · all charts' }).click(),
    );
    const slug = (t: string) =>
      t
        .toLowerCase()
        .replace(/[ ·]/g, '-')
        .replace(/[^a-z0-9-]/g, '')
        .replace(/-+/g, '-')
        .replace(/^-|-$/g, '');
    expect(downloads.map((d) => d.suggestedFilename()).sort()).toEqual(
      titles.map((t) => `${PROJECT}-compare-${slug(t ?? '')}-${TODAY}.png`).sort(),
    );
    for (const download of downloads) await expectPng(download);
    await expect(page.getByTestId('compare-png-failed')).toHaveCount(0);
  });

  test('blind: chart Run names and the key read R1…Rn only', async ({ page }) => {
    await mockBackend(page);
    await page.goto(compareUrl([RUN_A, RUN_B, RUN_C], '&view=chart&blind=1'));
    await page.getByRole('button', { name: 'ROLE', exact: true }).click();

    const key = page.getByTestId('chart-run-key').first();
    await expect(key).toContainText(`R1 · ${RUN_A.slice(0, 8)}`);
    await expect(page.getByTestId('compare-charts')).not.toContainText('snake bench');
  });
});
