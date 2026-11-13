import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Epic 6 of orchestrator-run-metrics, story 4, end to end in the built web-client: the
 * `TIER 2 · OPT-IN` and `TIER 3 · FROM WORKFLOW STEPS` rows of STATIC SIGNALS ON THE CHANGE on
 * the Run page's METRICS tab — the partial hub total said in words, `possible` findings by
 * severity, their list in the origin drawer with the SARIF download, the test-first line with
 * its limits, and a step-produced metric by its catalogue label.
 *
 * The stub backend holds no Run and no `/metrics/*` route, so every read is answered with
 * `page.route()` from fixtures this spec owns (the `static-signals.spec.ts` precedent).
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939cd';
const PROJECT_ID = '0199aaaa-0000-7000-8000-000000000001';
const HUB_ANALYSIS = '01a06887-0000-7000-8000-0000000000b1';
const APP_ANALYSIS = '01a06887-0000-7000-8000-0000000000b2';
const APP = 'repos/app';

const LINT = 'code.linter_warnings_new';
const SECURITY = 'code.findings_security';
const FIRST = 'code.test_first_order';
const HELDOUT = 'step.bench-v1.heldout_tests';
const LIMITS =
  'it says nothing of test quality · a template that orders the work decides it · tests weakened later go unseen';
const PARTIAL = { missing: 'partial', partial_n: 1, partial_m: 2 };

// ---------------------------------------------------------------- catalogue

function entry(
  id: string,
  label: string,
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    additive: true,
    component_of: null,
    fingerprint_group: false,
    group: 'code',
    id,
    label,
    level: 'A',
    limits: null,
    methods: [{ description: `method text of ${id}`, n: 1, parameters: {} }],
    missing_words: ['n/a', 'not run', 'partial'],
    scopes: ['run', 'repository'],
    source: `source text of ${id}`,
    unit: 'count',
    ...over,
  };
}

const CATALOGUE = {
  items: [
    entry('cost.gateway', 'gateway cost', { group: 'cost', unit: 'USD' }),
    entry(LINT, 'new linter warnings'),
    entry('code.typecheck_errors_new', 'new type-check errors'),
    entry('code.coverage_changed_lines', 'coverage of changed lines'),
    entry('code.tests_executed', 'test cases executed'),
    entry('code.fail_to_pass', 'fail-to-pass'),
    entry(SECURITY, 'possible security findings'),
    entry('code.findings_bug', 'possible bug findings'),
    entry(FIRST, 'test-first order', { unit: 'stories', scopes: ['run'], limits: LIMITS }),
  ],
};

const STEP_ENTRY = entry(HELDOUT, 'held-out tests', {
  group: 'step',
  unit: 'tests',
  scopes: ['run'],
  additive: false,
});

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

/** Repository `.` declared no Tier 2; `repos/app` did, so every Run total is partial. */
const ITEMS = [
  value('cost.gateway', 'run', '1.20'),
  value(LINT, 'run', '1', PARTIAL),
  value(LINT, '.', null, { missing: 'n/a — tier 2 not declared' }),
  value(LINT, APP, '1'),
  value(SECURITY, 'run', '3', { source: 'high', ...PARTIAL }),
  value(SECURITY, 'run', '0', { source: 'medium', ...PARTIAL }),
  value(SECURITY, 'run', '0', { source: 'low', ...PARTIAL }),
  value(SECURITY, 'run', '1', { source: 'unchanged', ...PARTIAL }),
  value(SECURITY, APP, '3', { source: 'high' }),
  ...(
    [
      ['test_first', '4'],
      ['test_with_code', '2'],
      ['test_after', '0'],
      ['not_readable', '2'],
      ['readable', '6'],
      ['stories', '8'],
    ] as const
  ).map(([source, n]) => value(FIRST, 'run', n, { source, unit: 'stories' })),
  value(HELDOUT, 'run', '18', { source: 'passed', unit: 'count' }),
  value(HELDOUT, 'run', '2', { source: 'failed', unit: 'count' }),
];

function analysis(id: string, path: string, opengrep: boolean): Record<string, unknown> {
  return {
    analysis_id: id,
    repository_path: path,
    status: 'ok',
    reason: '',
    base: 'a'.repeat(40),
    head: path === '.' ? 'b'.repeat(40) : 'c'.repeat(40),
    base_branch: 'main',
    languages: ['Python'],
    commits_outside_run: 0,
    tools: [
      { tool: 'gitleaks', version: '8.21.2' },
      ...(opengrep ? [{ tool: 'opengrep', version: '1.10.0' }] : []),
    ],
    vulnerability_db_date: null,
    lookup_date: null,
    declaration_hash: opengrep ? 'd'.repeat(64) : null,
    sarif_tools: opengrep ? ['opengrep'] : [],
    rule_pack_hash: opengrep ? 'abcdef1234567890' : null,
  };
}

const ANALYSES = [analysis(HUB_ANALYSIS, '.', false), analysis(APP_ANALYSIS, APP, true)];

const finding = (rule: string, line: number, over: Record<string, unknown> = {}) => ({
  kind: 'security',
  rule,
  path: 'src/view.py',
  line,
  severity: 'high',
  cwe: ['CWE-79'],
  state: 'new',
  ...over,
});

/** Three new high security findings, one unchanged, one new bug: only the three are listed. */
const FINDINGS = {
  analysis_id: APP_ANALYSIS,
  items: [
    finding('r.xss-a', 4),
    finding('r.xss-b', 9),
    finding('r.sqli', 12, { cwe: ['CWE-89'] }),
    finding('r.old', 20, { state: 'unchanged' }),
    finding('r.none-check', 30, { kind: 'bug', severity: 'medium', cwe: [] }),
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
        template: 'bench-v1',
        version: 1,
        harness: 'claude',
        started_at: '2026-11-12T10:23:00Z',
        worktree_path: null,
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '1.20',
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
      label: 'snake bench',
      label_set_by_operator: true,
      budget_usd: '100.00',
      compare_urls: [],
      created_at: '2026-11-12T10:23:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: PROJECT_ID,
      repository: '22222222-2222-2222-2222-222222222222',
      spend_usd: '1.20',
      template: 'bench-v1',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
  };
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

interface RunBackend {
  findingsUrls: string[];
}

async function mockRun(page: Page): Promise<RunBackend> {
  const backend: RunBackend = { findingsUrls: [] };
  await page.route('**/api/metrics/catalogue*', (route) => json(route, CATALOGUE));
  await page.route(`**/api/runs/${RUN_ID}**`, (route) => {
    const request = route.request();
    const rest = new URL(request.url()).pathname.slice(`/api/runs/${RUN_ID}`.length);
    if (rest === '/detail') return json(route, detail());
    if (rest === '/metrics/versions') {
      return json(route, {
        items: [
          {
            n: 1,
            calculated_at: '2026-11-12T09:00:00Z',
            entry_point: ['run_end'],
            methods_changed: [],
          },
        ],
        next_cursor: null,
      });
    }
    if (rest === '/metrics') {
      return json(route, {
        items: ITEMS,
        latest: 1,
        run_id: RUN_ID,
        values_so_far: false,
        version: 1,
      });
    }
    if (rest === '/analysis') {
      return json(route, {
        run_id: RUN_ID,
        version: 1,
        items: ANALYSES,
        step_entries: [STEP_ENTRY],
      });
    }
    if (rest === `/analysis/${APP_ANALYSIS}/findings`) {
      backend.findingsUrls.push(request.url());
      return json(route, FINDINGS);
    }
    return route.fallback();
  });
  return backend;
}

const RUN_URL = `/workflows/${RUN_ID}?tab=metrics`;
/** Tier 2 and step-produced rows are not headline metrics: they show under ALL METRICS. */
async function openAll(page: Page): Promise<void> {
  await page.goto(RUN_URL);
  await page.getByRole('button', { name: 'ALL METRICS' }).click();
}

const row = (page: Page, scope: string, metricId: string) =>
  page.getByTestId(`static-row-${scope}-${metricId}`).first();

// ---------------------------------------------------------------- tests

test.describe('/workflows/[id] METRICS — Tier 2 and Tier 3 (epic 6 story 4)', () => {
  test('a Tier 2 total one of two repositories ran reads partial · 1 of 2 repositories', async ({
    page,
  }) => {
    await mockRun(page);
    await openAll(page);

    const table = page.getByTestId('static-signals-table');
    await expect(table.locator('tr.tier')).toContainText(['TIER 2 · OPT-IN']);

    const total = row(page, 'run', LINT);
    await expect(total).toContainText('1');
    await expect(total).toContainText('partial · 1 of 2 repositories');
    await expect(row(page, '.', LINT)).toContainText('n/a — tier 2 not declared');
    await expect(row(page, APP, LINT)).not.toContainText('partial');
  });

  test('new security findings read possible by severity, and the total is partial', async ({
    page,
  }) => {
    await mockRun(page);
    await openAll(page);

    const security = row(page, 'run', SECURITY);
    await expect(security).toContainText('3 possible high');
    await expect(security).toContainText('0 possible medium');
    await expect(security).toContainText('0 possible low');
    await expect(security).toContainText('unchanged 1');
    await expect(security).toContainText('partial · 1 of 2 repositories');
  });

  test('a finding count opens the new findings with CWE in the drawer and the SARIF download', async ({
    page,
  }) => {
    const backend = await mockRun(page);
    await openAll(page);

    await row(page, 'run', SECURITY).locator('.metric-value-cell').first().click();

    const findings = page.getByTestId('origin-drawer').getByTestId('findings-opengrep');
    await expect(findings.getByRole('listitem')).toHaveText([
      'r.xss-a · src/view.py:4 · high · CWE-79',
      'r.xss-b · src/view.py:9 · high · CWE-79',
      'r.sqli · src/view.py:12 · high · CWE-89',
    ]);
    await expect(findings.getByRole('link', { name: `SARIF · opengrep · ${APP}` })).toHaveAttribute(
      'href',
      `/api/runs/${RUN_ID}/analysis/${APP_ANALYSIS}/sarif/opengrep`,
    );
    expect(backend.findingsUrls.length).toBeGreaterThan(0);
  });

  test('the footer names the opengrep rule pack the Tier 2 repository declared', async ({
    page,
  }) => {
    await mockRun(page);
    await openAll(page);

    await expect(page.getByTestId('static-foot')).toContainText('rule packs: opengrep abcdef12');
  });

  test('the test-first line counts readable stories and its hint holds the three limits', async ({
    page,
  }) => {
    await mockRun(page);
    await openAll(page);

    await expect(page.getByTestId('static-signals-table').locator('tr.tier')).toContainText([
      'TIER 3 · FROM WORKFLOW STEPS',
    ]);
    const line = row(page, 'run', FIRST);
    await expect(line).toContainText(
      'test-first order · method followed, not quality · 6 of 8 stories readable from the logs',
    );
    await expect(line).toContainText('test first');
    await expect(line).toContainText('test with code');
    await expect(line).toContainText('not readable');

    await line.locator('button.metric-hint-control').first().click();
    await expect(page.getByText(LIMITS)).toBeVisible();
  });

  test('a step-produced metric reads by its catalogue label with each count', async ({ page }) => {
    await mockRun(page);
    await openAll(page);

    const step = row(page, 'run', HELDOUT);
    await expect(step).toContainText('held-out tests');
    await expect(step).toContainText('passed 18');
    await expect(step).toContainText('failed 2');
  });
});
