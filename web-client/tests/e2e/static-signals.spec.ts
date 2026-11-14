import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Epic 5 of orchestrator-run-metrics, story 5, end to end in the built web-client: STATIC
 * SIGNALS ON THE CHANGE on the Run page's METRICS tab (the Run row and one row per repository
 * with its detail line, `raw only`, the tier heads, the footer, the findings drawer with its
 * SARIF link, the not-run line), and the comparison's static rows (`≠ tool versions differ`,
 * the tool version under the cell, the bar charts with the rate as value label).
 *
 * The stub backend holds no Run and no `/metrics/*` route, so every read is answered with
 * `page.route()` from fixtures this spec owns (the `run-detail-metrics.spec.ts` precedent).
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ab';
const RUN_A = 'a1a1a1a1-0000-7000-8000-00000000000a';
const RUN_B = 'b2b2b2b2-0000-7000-8000-00000000000b';
const RUN_C = 'c3c3c3c3-0000-7000-8000-00000000000c';
const PROJECT_ID = '0199aaaa-0000-7000-8000-000000000001';
const HUB_ANALYSIS = '01a06887-0000-7000-8000-0000000000a1';
const APP_ANALYSIS = '01a06887-0000-7000-8000-0000000000a2';
const APP = 'repos/app';
const LOOKUP_DATE = '2026-11-12';

// ---------------------------------------------------------------- catalogue

const CATALOGUE_ROWS: [id: string, label: string, group: string, unit: string][] = [
  ['cost.gateway', 'gateway cost', 'cost', 'USD'],
  ['cost.harness', 'harness cost', 'cost', 'USD'],
  ['code.lines_added', 'lines added', 'code', 'count'],
  ['code.type_escapes_added', 'type escapes added', 'code', 'count'],
  ['code.suppressions_added', 'suppressions added', 'code', 'count'],
  ['code.possible_secrets', 'possible secrets', 'code', 'count'],
  ['code.duplication_added', 'duplicated lines added', 'code', 'count'],
  ['code.functions_over_cyclomatic', 'functions over cyclomatic threshold', 'code', 'count'],
];

const CATALOGUE = {
  items: CATALOGUE_ROWS.map(([id, label, group, unit]) => ({
    additive: true,
    component_of: null,
    fingerprint_group: false,
    group,
    id,
    label,
    level: 'H',
    limits: null,
    methods: [{ description: `method text of ${id}`, n: 1, parameters: {} }],
    missing_words: ['not recorded', 'not run', 'raw only', 'small change'],
    scopes: ['run', 'repository'],
    source: `source text of ${id}`,
    unit,
  })),
};

// ---------------------------------------------------------------- the Run page

function value(
  metric_id: string,
  scope_key: string,
  value_num: string | null,
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  const run = scope_key === 'run';
  return {
    attempt_n: null,
    carried_from: null,
    method_id: `${metric_id}@1`,
    metric_id,
    missing: null,
    model: null,
    origin: null,
    partial_m: null,
    partial_n: null,
    repository: run ? null : scope_key,
    role: null,
    scope_key,
    scope_label: null,
    scope_type: run ? 'run' : 'repository',
    source: null,
    unit: metric_id.startsWith('cost.') ? 'USD' : 'count',
    value_num,
    ...over,
  };
}

/** One scope's code values: 40 added production lines, so every rate reads `raw only`. */
function codeValues(key: string, secrets: string): Record<string, unknown>[] {
  return [
    value('code.lines_added', key, '40', { source: 'production' }),
    value('code.type_escapes_added', key, '3', { source: 'production' }),
    value('code.type_escapes_added', key, null, {
      source: 'production:per_100',
      missing: 'raw only',
    }),
    value('code.possible_secrets', key, secrets),
    value('code.duplication_added', key, '12'),
    value('code.duplication_added', key, null, { source: 'small_change', missing: 'small change' }),
    value('code.functions_over_cyclomatic', key, '0'),
  ];
}

const COST = [value('cost.gateway', 'run', '1.20'), value('cost.harness', 'run', '1.30')];
const V2_ITEMS = [
  ...COST,
  ...codeValues('run', '1'),
  ...codeValues('.', '1'),
  ...codeValues(APP, '0'),
];

const TOOLS = [
  { tool: 'gitleaks', version: '8.21.2' },
  { tool: 'osv-scanner', version: '2.0.2' },
  { tool: 'jscpd', version: '4.0.5' },
  { tool: 'lizard', version: '1.17.13' },
];

function analysis(
  id: string,
  path: string,
  outside: number,
  sarif: string[],
): Record<string, unknown> {
  return {
    analysis_id: id,
    repository_path: path,
    status: 'ok',
    reason: '',
    base: 'a'.repeat(40),
    head: path === '.' ? 'b'.repeat(40) : 'c'.repeat(40),
    base_branch: 'main',
    languages: ['TypeScript'],
    commits_outside_run: outside,
    tools: TOOLS,
    vulnerability_db_date: LOOKUP_DATE,
    lookup_date: LOOKUP_DATE,
    declaration_hash: null,
    sarif_tools: sarif,
  };
}

const ANALYSES = [
  analysis(HUB_ANALYSIS, '.', 0, ['gitleaks', 'jscpd']),
  analysis(APP_ANALYSIS, APP, 2, ['jscpd']),
];

const SARIF = {
  version: '2.1.0',
  runs: [
    {
      tool: { driver: { name: 'gitleaks' } },
      results: [
        {
          ruleId: 'generic-api-key',
          message: { text: 'possible generic API key' },
          locations: [
            {
              physicalLocation: {
                artifactLocation: { uri: 'src/config.ts' },
                region: { startLine: 3 },
              },
            },
          ],
        },
      ],
    },
  ],
};

function detail(): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'familio',
        repository: 'my-family-app',
        base_branch: 'main',
        folder: 'initiatives/snake',
        template: 'staged-initiative-hub',
        version: 4,
        harness: 'claude',
        started_at: '2026-11-12T10:23:00Z',
        worktree_path: null,
      },
    },
    alert: null,
    steps: [
      {
        seq: 1,
        path: 'metrics',
        label: 'metrics',
        kind: 'metrics.analyse',
        gate: 'unvalidated',
        status: 'done',
        token: 'DON',
        reason: '2 repositories analysed',
        attempts: 1,
        latest: null,
      },
    ],
    stories: [],
    cost: {
      spent_usd: '1.30',
      budget_usd: '100.00',
      tokens_in: 1000,
      tokens_out: 2000,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
    run: {
      id: RUN_ID,
      status: 'done',
      admitted_signals: [],
      branch: 'feat/snake',
      label: 'snake bench staged',
      label_set_by_operator: true,
      budget_usd: '100.00',
      compare_urls: [],
      created_at: '2026-11-12T10:23:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: PROJECT_ID,
      repository: '22222222-2222-2222-2222-222222222222',
      spend_usd: '1.30',
      template: 'staged-initiative-hub',
      terminal_session: false,
      version: 4,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

interface RunBackend {
  analysisUrls: string[];
  sarifUrls: string[];
}

/** v1 holds no analysis and no code value; v2 holds two repository analyses. */
async function mockRun(page: Page): Promise<RunBackend> {
  const backend: RunBackend = { analysisUrls: [], sarifUrls: [] };
  await page.route('**/api/metrics/catalogue*', (route) => json(route, CATALOGUE));
  await page.route(`**/api/runs/${RUN_ID}**`, (route) => {
    const request = route.request();
    const { pathname, searchParams } = new URL(request.url());
    const rest = pathname.slice(`/api/runs/${RUN_ID}`.length);
    const v = Number(searchParams.get('v') ?? 2);
    if (rest === '/detail') return json(route, detail());
    if (rest === '/metrics/versions') {
      return json(route, {
        items: [1, 2].map((n) => ({
          n,
          calculated_at: `2026-11-1${n}T09:00:00Z`,
          entry_point: n === 1 ? ['run_end'] : ['manual'],
          methods_changed: [],
        })),
        next_cursor: null,
      });
    }
    if (rest === '/metrics') {
      return json(route, {
        items: v === 1 ? COST : V2_ITEMS,
        latest: 2,
        run_id: RUN_ID,
        values_so_far: false,
        version: v,
      });
    }
    if (rest === '/analysis') {
      backend.analysisUrls.push(request.url());
      return json(route, { run_id: RUN_ID, version: v, items: v === 1 ? [] : ANALYSES });
    }
    if (rest.startsWith('/analysis/')) {
      backend.sarifUrls.push(request.url());
      return route.fulfill({
        status: 200,
        contentType: 'application/sarif+json',
        body: JSON.stringify(SARIF),
      });
    }
    return route.fallback();
  });
  return backend;
}

const RUN_URL = `/workflows/${RUN_ID}?tab=metrics`;
const row = (page: Page, scope: string, metricId: string) =>
  page.getByTestId(`static-row-${scope}-${metricId}`).first();

// ---------------------------------------------------------------- the comparison

function header(id: string, label: string): Record<string, unknown> {
  return {
    run_id: id,
    short_id: id.slice(0, 8),
    label,
    label_set_by_operator: true,
    template_name: 'staged-initiative-hub',
    template_version: '4',
    harness: 'claude',
    models_by_role: {},
    base_branch: 'main',
    status: 'done',
    stories_done: { done: 3, planned: 3 },
    selected_version: 1,
    versions_available: [1],
    subscription: false,
  };
}

function cell(metricId: string, value_num: string | null, over: Record<string, unknown> = {}) {
  return {
    attempt_n: null,
    carried_from: null,
    method_id: `${metricId}@1`,
    missing: null,
    model: null,
    partial_m: null,
    partial_n: null,
    repository: null,
    role: null,
    scope_key: 'run',
    scope_label: null,
    scope_type: 'run',
    source: null,
    unit: 'count',
    value_num,
    ...over,
  };
}

const toolset = (jscpd: string) => [
  { tool: 'gitleaks', version: '8.21.2' },
  { tool: 'jscpd', version: jscpd },
  { tool: 'orchestrator-analysis.yaml', version: 'absent' },
];

/** A and B were analysed with different jscpd versions; C holds no analysis. */
function staticMetric(metricId: string, a: string, b: string, differ: boolean) {
  const rate = (raw: string) => cell(metricId, (Number(raw) / 3).toFixed(2), { source: 'per_100' });
  return {
    metric_id: metricId,
    methods_differ: false,
    methods: { [RUN_A]: [`${metricId}@1`], [RUN_B]: [`${metricId}@1`] },
    cells: {
      [RUN_A]: [cell(metricId, a), rate(a)],
      [RUN_B]: [cell(metricId, b), rate(b)],
    },
    harness_delta: {},
    families: [],
    tool_versions_differ: differ,
    toolsets: differ ? { [RUN_A]: toolset('4.0.5'), [RUN_B]: toolset('4.0.6') } : {},
  };
}

const COMPARE = {
  project_id: PROJECT_ID,
  project_name: 'familio',
  runs: [header(RUN_A, 'snake staged'), header(RUN_B, 'snake direct'), header(RUN_C, 'snake old')],
  same_work: {
    differs: false,
    runs: Object.fromEntries(
      [RUN_A, RUN_B, RUN_C].map((id) => [
        id,
        {
          base_commits: { 'my-family-app': 'a'.repeat(40) },
          initiative_folder: 'initiatives/snake',
          stories_planned: 3,
        },
      ]),
    ),
  },
  metrics: [
    staticMetric('code.suppressions_added', '3', '6', false),
    staticMetric('code.duplication_added', '12', '30', true),
  ],
  diff_size: { [RUN_A]: '+300 −20 · 9 files', [RUN_B]: '+310 −12 · 8 files', [RUN_C]: 'not run' },
};

async function mockCompare(page: Page): Promise<void> {
  await page.route('**/api/metrics/catalogue*', (route) => json(route, CATALOGUE));
  await page.route('**/api/metrics/compare**', (route) => json(route, COMPARE));
  await page.route('**/api/runs/*/detail', (route) => json(route, { steps: [] }));
}

const COMPARE_URL = `/metrics/compare?runs=${[RUN_A, RUN_B, RUN_C].join(',')}`;
const FLAG = '≠ tool versions differ: jscpd 4.0.5 (Run 1) vs 4.0.6 (Run 2)';

// ---------------------------------------------------------------- tests

test.describe('/workflows/[id] METRICS — static signals on the change (epic 5 story 5)', () => {
  test('a version with two analyses shows the Run row and one row per repository', async ({
    page,
  }) => {
    const backend = await mockRun(page);
    await page.goto(RUN_URL);

    const block = page.getByTestId('static-signals');
    await expect(
      block.getByRole('heading', { name: 'STATIC SIGNALS ON THE CHANGE' }),
    ).toBeVisible();
    await expect(block).toContainText('findings are possible, leads to review · no single score');
    expect(backend.analysisUrls.some((u) => u.includes('v=2'))).toBe(true);

    const scopes = block.getByTestId(/^static-scope-/);
    // two tiers, each with the Run row then the repositories in the order the API gave them
    await expect(scopes).toHaveCount(6);
    await expect(scopes.nth(0)).toHaveAttribute('data-testid', 'static-scope-run');
    await expect(scopes.nth(0)).toContainText('all repositories');
    await expect(scopes.nth(1)).toHaveAttribute('data-testid', 'static-scope-.');
    await expect(scopes.nth(1)).toContainText(
      'TypeScript · base aaaaaaa (merge base with main) → head bbbbbbb · head holds no commits outside this Run',
    );
    await expect(scopes.nth(2)).toHaveAttribute('data-testid', `static-scope-${APP}`);
    await expect(scopes.nth(2)).toContainText(
      'base aaaaaaa (merge base with main) → head ccccccc · head holds 2 commits this Run did not make',
    );
  });

  test('raw and per-100 columns: 40 production lines read raw only, duplication small change', async ({
    page,
  }) => {
    await mockRun(page);
    await page.goto(RUN_URL);

    const table = page.getByTestId('static-signals-table');
    await expect(table.locator('thead').getByRole('columnheader')).toHaveText([
      'signal',
      'raw',
      'per 100 prod. lines',
    ]);

    const escapes = row(page, 'run', 'code.type_escapes_added').getByRole('cell');
    await expect(escapes.nth(1)).toContainText('3');
    await expect(escapes.nth(2)).toHaveText('raw only');
    await expect(row(page, 'run', 'code.duplication_added').getByRole('cell').nth(1)).toContainText(
      'small change',
    );
  });

  test('tier heads: 1A offline, 1B with the lookup date, 2 and 3 read n/a', async ({ page }) => {
    await mockRun(page);
    await page.goto(RUN_URL);

    const heads = page.getByTestId('static-signals-table').locator('tr.tier');
    await expect(heads).toHaveText([
      'TIER 1A · OFFLINE',
      `TIER 1B · LOOKUPS ${LOOKUP_DATE}`,
      'TIER 2 · OPT-IN',
      'TIER 3 · FROM WORKFLOW STEPS',
    ]);
    // Tier 1b holds the dependency, duplication and complexity rows, never a Tier 1a one
    await expect(page.getByTestId('static-row-run-code.duplication_added')).toHaveCount(1);
    await expect(page.getByTestId('static-row-run-code.lines_added')).toHaveCount(1);
  });

  test('the footer prints tools, versions, rule packs and lookup dates without a hint', async ({
    page,
  }) => {
    await mockRun(page);
    await page.goto(RUN_URL);

    const foot = page.getByTestId('static-foot');
    await expect(foot).toBeVisible();
    await expect(foot).toContainText(
      'tools: gitleaks 8.21.2 · jscpd 4.0.5 · lizard 1.17.13 · osv-scanner 2.0.2',
    );
    await expect(foot).toContainText('rule packs: n/a — Tier 1 runs no rule pack');
    await expect(foot).toContainText(`vulnerability database ${LOOKUP_DATE}`);
    await expect(foot).toContainText(`registry lookup ${LOOKUP_DATE}`);
    await expect(foot).toContainText('declaration orchestrator-analysis.yaml absent');
  });

  test('a finding count opens its list in the origin drawer with the SARIF download', async ({
    page,
  }) => {
    const backend = await mockRun(page);
    await page.goto(RUN_URL);

    await row(page, '.', 'code.possible_secrets').locator('.metric-value-cell').click();

    const drawer = page.getByTestId('origin-drawer');
    const findings = drawer.getByTestId('findings-gitleaks');
    await expect(findings.getByRole('listitem')).toHaveText(['generic-api-key · src/config.ts:3']);
    const link = findings.getByRole('link', { name: 'SARIF · gitleaks · .' });
    await expect(link).toHaveAttribute(
      'href',
      `/api/runs/${RUN_ID}/analysis/${HUB_ANALYSIS}/sarif/gitleaks`,
    );
    expect(backend.sarifUrls).toEqual([
      expect.stringContaining(`/analysis/${HUB_ANALYSIS}/sarif/gitleaks`),
    ]);
  });

  test('a version holding no analysis reads the not-run line', async ({ page }) => {
    await mockRun(page);
    await page.goto(`${RUN_URL}&v=1`);

    const block = page.getByTestId('static-signals');
    await expect(block).toContainText('not run in v1 · RECALCULATE METRICS runs it');
    await expect(block.getByTestId('static-signals-table')).toHaveCount(0);
    await expect(block.getByTestId('static-foot')).toHaveCount(0);
  });
});

test.describe('/metrics/compare — static signals (epic 5 story 5)', () => {
  test('TABLE flags differing tool versions and prints each Run’s version under its cell', async ({
    page,
  }) => {
    await mockCompare(page);
    await page.goto(COMPARE_URL);

    const duplication = page.getByTestId('compare-row-code.duplication_added');
    await expect(duplication.getByRole('rowheader')).toContainText(FLAG);
    await expect(
      page.getByTestId(`compare-cell-code.duplication_added-${RUN_A}`).locator('.compare-under'),
    ).toHaveText('jscpd 4.0.5');
    await expect(
      page.getByTestId(`compare-cell-code.duplication_added-${RUN_B}`).locator('.compare-under'),
    ).toHaveText('jscpd 4.0.6');

    // the same toolset is never flagged
    await expect(
      page.getByTestId('compare-row-code.suppressions_added').getByRole('rowheader'),
    ).not.toContainText('≠ tool versions differ');
  });

  test('TABLE: a Run with no analysis reads not run with recalculate on its page', async ({
    page,
  }) => {
    await mockCompare(page);
    await page.goto(COMPARE_URL);

    const empty = page.getByTestId(`compare-cell-code.suppressions_added-${RUN_C}`);
    await expect(empty).toContainText('not run');
    await expect(empty.getByRole('link', { name: 'recalculate' })).toHaveAttribute(
      'href',
      `/workflows/${RUN_C}?tab=metrics&recalculate=1`,
    );
  });

  test('CHART draws static signals as bars with the rate as label and keeps the flag', async ({
    page,
  }) => {
    await mockCompare(page);
    await page.goto(`${COMPARE_URL}&view=chart&metrics=all`);

    const suppressions = page.getByRole('figure', { name: 'suppressions added' });
    await expect(suppressions).toBeVisible();
    await expect(suppressions).toContainText('per 100');
    await expect(suppressions).toContainText('not run');

    const duplication = page.getByRole('figure', { name: 'duplicated lines added' });
    await expect(duplication.getByTestId('chart-flag')).toContainText('≠ tool versions differ');
  });
});
