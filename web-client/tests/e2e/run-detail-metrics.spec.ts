import { readFile } from 'node:fs/promises';

import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * Epic 3 of orchestrator-run-metrics, end to end in the built web-client: the Run label as
 * title, the cost block's figure pair and figures-differ card, hints and the origin drawer,
 * the METRICS tab's URL state and version selector, RECALCULATE METRICS, the CHART view and a
 * real PNG download, and the one hint on the runs-history `cost` head.
 *
 * Every metrics route is answered with `page.route()` (the stub backend holds no Run), the
 * `run-detail-tabs.spec.ts` precedent. The catalogue below is a fixture this spec owns.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939ab';
const URL = `/workflows/${RUN_ID}`;
const LABEL = 'familio familio-snake-v2 bench-v1-staged 2026-11-10 10:23';
const BRANCH = 'feat/snake-v2';
const LIVE_LINE = 'Run running · values so far, stored as each attempt ends';

const LABELS: Record<string, string> = {
  'cost.gateway': 'gateway cost',
  'cost.harness': 'harness cost',
  'cost.figure_gap': 'figure gap',
  'cost.retries': 'retry cost',
  'tokens.input': 'uncached input tokens',
  'tokens.output': 'output tokens',
  'tokens.cache_read': 'cache read tokens',
  'tokens.cache_write': 'cache write tokens',
  'time.wall': 'wall-clock',
  'time.parked': 'waiting on you',
  'time.retries': 'retry time',
  'process.attempts': 'attempts',
  'process.retries': 'retries',
  'process.failures': 'failures',
  'spend.recorded': 'recorded spend',
};

const UNITS: Record<string, string> = { tokens: 'tokens', time: 'seconds', process: 'count' };

function entry(id: string): Record<string, unknown> {
  const group = id.split('.')[0]!;
  return {
    additive: true,
    component_of: null,
    fingerprint_group: false,
    group,
    id,
    label: LABELS[id],
    level: 'H',
    limits: null,
    methods: [{ description: `method text of ${id}`, n: 1, parameters: {} }],
    missing_words: ['not recorded', 'not available'],
    scopes: ['run', 'epic', 'story', 'step', 'attempt', 'role', 'model'],
    source: `source text of ${id}`,
    unit: UNITS[group] ?? 'USD',
  };
}

const CATALOGUE = { items: Object.keys(LABELS).map(entry) };

function value(
  metric_id: string,
  value_num: string | null,
  over: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    attempt_n: null,
    carried_from: null,
    method_id: `${metric_id}@1`,
    metric_id,
    missing: value_num === null ? 'not recorded' : null,
    model: null,
    origin: {
      base_commit: 'b'.repeat(40),
      base_commit_na: null,
      branch: BRANCH,
      branch_na: null,
      commit: 'c'.repeat(40),
      commit_na: null,
      harness: 'claude',
      harness_na: null,
      origin_model: null,
      origin_model_na: 'spans_models',
      origin_repository: 'rebecamurillo/my-family-app',
      origin_repository_na: null,
      project_id: '11111111-1111-1111-1111-111111111111',
      run_id: RUN_ID,
      template_name: 'initiative-hub-story',
      template_version: 3,
    },
    partial_m: null,
    partial_n: null,
    repository: null,
    role: null,
    scope_key: RUN_ID,
    scope_label: null,
    scope_type: 'run',
    source: null,
    unit: metric_id.startsWith('tokens') ? 'tokens' : 'USD',
    value_num,
    ...over,
  };
}

const role = (name: string, gateway: string, harness: string) => [
  value('cost.gateway', gateway, { scope_type: 'role', scope_key: name, role: name }),
  value('cost.harness', harness, { scope_type: 'role', scope_key: name, role: name }),
];
const model = (name: string, harness: string) => [
  value('cost.harness', harness, { scope_type: 'model', scope_key: name, model: name }),
];

/** v2, the latest: the figures differ ($15.35 vs $16.01). */
const STORY = 'epics[0].stories[0]';
const V2_ITEMS = [
  value('cost.gateway', '15.35'),
  value('cost.harness', '16.01'),
  value('cost.gateway', '15.35', { scope_type: 'epic', scope_key: 'epics[0]' }),
  value('cost.gateway', '15.35', { scope_type: 'story', scope_key: STORY, scope_label: '1-1' }),
  value('cost.harness', '16.01', { scope_type: 'story', scope_key: STORY, scope_label: '1-1' }),
  value('tokens.input', null),
  value('tokens.output', '42000'),
  ...role('builder', '4.00', '4.20'),
  ...role('senior', '9.00', '9.40'),
  ...role('reviewer', '2.35', '2.41'),
  ...model('claude-opus-5-5', '12.00'),
  ...model('claude-sonnet-5-5', '4.01'),
];

/** v1: the figures agree, so no card. */
const V1_ITEMS = [value('cost.gateway', '12.00'), value('cost.harness', '12.00')];

function version(n: number): Record<string, unknown> {
  return {
    calculated_at: `2026-11-1${n}T09:00:00Z`,
    entry_point: ['manual'],
    methods_changed: [],
    n,
  };
}

function detail(run: Record<string, unknown>): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'familio',
        repository: 'my-family-app',
        base_branch: 'main',
        folder: 'initiatives/snake',
        template: 'initiative-hub-story',
        version: 3,
        harness: 'claude',
        started_at: '2026-11-10T10:23:00Z',
        worktree_path: null,
      },
    },
    alert: null,
    steps: [stepRow(1, 'epics[0].stories[0].build'), stepRow(2, 'epics[0].stories[0].verify')],
    stories: [],
    cost: {
      spent_usd: '16.01',
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
      branch: BRANCH,
      label: LABEL,
      label_set_by_operator: false,
      budget_usd: '100.00',
      compare_urls: [],
      created_at: '2026-11-10T10:23:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: '11111111-1111-1111-1111-111111111111',
      repository: '22222222-2222-2222-2222-222222222222',
      spend_usd: '16.01',
      template: 'initiative-hub-story',
      terminal_session: false,
      version: 3,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
      ...run,
    },
  };
}

function stepRow(seq: number, path: string): Record<string, unknown> {
  return {
    seq,
    path,
    label: path.split('.').pop(),
    kind: 'agent',
    gate: 'deterministic',
    status: 'done',
    token: 'DON',
    reason: null,
    attempts: 1,
    latest: null,
  };
}

interface Backend {
  run: Record<string, unknown>;
  versions: number[];
  /** `null` for a live Run with no stored version. */
  latest: number | null;
  calcState: 'running' | 'done' | 'failed';
  calcOutput: string;
  patches: unknown[];
  metricUrls: string[];
}

const json = (route: Route, body: unknown, status = 200) =>
  route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });

function calculation(state: string, output = ''): Record<string, unknown> {
  return {
    id: '01a06887-79ab-759b-97a0-71c32ad93999',
    run_id: RUN_ID,
    state,
    target_n: 3,
    entry_point: ['manual'],
    queued_at: '2026-11-13T10:00:00Z',
    started_at: '2026-11-13T10:00:01Z',
    ended_at: null,
    output,
  };
}

/** The METRICS tab's own version selector; the cost block carries a second one. */
const tabVersion = (page: Page, name: string | RegExp) =>
  page.getByTestId('wf-metrics-head').getByRole('button', { name, exact: true });

async function mockBackend(page: Page, over: Partial<Backend> = {}): Promise<Backend> {
  const state: Backend = {
    run: {},
    versions: [1, 2],
    latest: 2,
    calcState: 'running',
    calcOutput: '',
    patches: [],
    metricUrls: [],
    ...over,
  };
  await page.route('**/api/metrics/catalogue*', (route) => json(route, CATALOGUE));
  await page.route(`**/api/runs/${RUN_ID}**`, async (route) => {
    const request = route.request();
    const { pathname, searchParams } = new globalThis.URL(request.url());
    const rest = pathname.slice(`/api/runs/${RUN_ID}`.length);
    if (rest === '/detail') return json(route, detail(state.run));
    if (rest === '' && request.method() === 'PATCH') {
      const body = request.postDataJSON() as { label: string | null };
      state.patches.push(body);
      state.run = {
        ...state.run,
        label: body.label ?? LABEL,
        label_set_by_operator: body.label !== null,
      };
      return json(route, detail(state.run).run);
    }
    if (rest === '/metrics/versions') {
      return json(route, { items: state.versions.map(version), next_cursor: null });
    }
    if (rest === '/metrics') {
      state.metricUrls.push(request.url());
      const live = state.latest === null;
      const v = Number(searchParams.get('v') ?? state.latest);
      return json(route, {
        items: v === 1 ? V1_ITEMS : V2_ITEMS,
        latest: state.latest,
        run_id: RUN_ID,
        values_so_far: live,
        version: live ? null : v,
      });
    }
    if (rest === '/metrics/calculate' && request.method() === 'POST') {
      return json(route, calculation('queued'), 202);
    }
    if (rest === '/metrics/calculations/3') {
      if (state.calcState === 'done') {
        state.versions = [1, 2, 3];
        state.latest = 3;
      }
      return json(route, calculation(state.calcState, state.calcOutput));
    }
    return route.fallback();
  });
  return state;
}

test.describe('/workflows/[id] — Run page metrics (orchestrator-run-metrics epic 3)', () => {
  test('an ended Run opens on METRICS with its label as title and the branch first', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(URL);

    await expect(page.getByTestId('wf-title')).toHaveText(LABEL);
    await expect(page.getByTestId('wf-meta')).toContainText(new RegExp(`^${BRANCH} · `));
    await expect(page.getByRole('button', { name: 'METRICS', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByTestId('wf-metrics')).toBeVisible();
    // the arrival URL is left alone until the Operator changes something
    expect(page.url()).not.toContain('tab=');
  });

  test('the cost block shows both figures and the figures-differ card', async ({ page }) => {
    await mockBackend(page);
    await page.goto(URL);

    const glance = page.getByTestId('wf-glance');
    await expect(glance).toContainText('GATEWAY');
    await expect(glance).toContainText('HARNESS');
    await expect(
      glance.getByRole('button', { name: `${LABEL} gateway cost $15.35` }),
    ).toBeVisible();
    await expect(
      glance.getByRole('button', { name: `${LABEL} harness cost $16.01` }),
    ).toBeVisible();

    const card = page.getByTestId('wf-figures-differ');
    await expect(card).toContainText(
      'gateway $15.35 · harness $16.01 · harness is $0.66 higher (4.3 %)',
    );
    await expect(card).toContainText('the budget gate uses the higher figure');
  });

  test('equal figures at cent precision show no figures-differ card', async ({ page }) => {
    await mockBackend(page);
    await page.goto(`${URL}?tab=metrics&view=table&v=1`);

    await expect(page.getByTestId('wf-glance')).toContainText('showing v1 of 2 · latest is v2');
    await expect(page.getByTestId('wf-figures-differ')).toHaveCount(0);
  });

  test('a hint opens on click and Enter, never on hover, and Escape returns focus', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(URL);

    const control = page
      .getByTestId('wf-glance')
      .getByRole('button', { name: 'how gateway cost is calculated' });
    const dialog = page.getByRole('dialog', { name: 'how gateway cost is calculated' });

    await control.hover();
    await expect(dialog).toHaveCount(0);

    await control.click();
    await expect(dialog).toBeVisible();
    await expect(dialog).toContainText('method text of cost.gateway');
    await expect(dialog).toContainText('source text of cost.gateway');

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(control).toBeFocused();

    await page.keyboard.press('Enter');
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
  });

  test('a value opens its origin drawer, which names the n/a reason', async ({ page }) => {
    await mockBackend(page);
    await page.goto(URL);

    await page
      .getByTestId('wf-glance')
      .getByRole('button', { name: `${LABEL} gateway cost $15.35` })
      .click();

    const drawer = page.getByTestId('origin-drawer');
    await expect(drawer).toBeVisible();
    await expect(drawer).toContainText(`${LABEL} · ${RUN_ID}`);
    await expect(drawer).toContainText('n/a — a Run total spans 2 models');
    await expect(drawer).toContainText(BRANCH);

    await page.keyboard.press('Escape');
    await expect(drawer).toHaveCount(0);
  });

  test('the by-role table is sorted by gateway descending with senior as a row', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(URL);

    const metrics = page.getByTestId('wf-metrics');
    await expect(metrics.getByText('BY ROLE')).toBeVisible();
    const roleTable = metrics.locator('table', { has: page.getByText('senior') }).first();
    const rows = roleTable.locator('tbody tr');
    await expect(rows).toHaveCount(3);
    await expect(rows.nth(0)).toContainText('senior');
    await expect(rows.nth(1)).toContainText('builder');
    await expect(rows.nth(2)).toContainText('reviewer');
    // a missing value prints its word, never 0
    await expect(metrics.getByText('not recorded').first()).toBeVisible();
  });

  test('a view change is written to the URL; ?v=1 reads v1 and says so', async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto(`${URL}?v=1`);

    await expect(page.getByTestId('wf-metrics-head')).toContainText(
      'showing v1 of 2 · latest is v2',
    );
    await expect(tabVersion(page, 'v1')).toHaveAttribute('aria-pressed', 'true');
    expect(backend.metricUrls.some((u) => u.includes('v=1'))).toBe(true);

    await page.getByRole('button', { name: 'CHART' }).click();
    await expect(page).toHaveURL(/[?&]tab=metrics(&|$)/);
    await expect(page).toHaveURL(/[?&]view=chart(&|$)/);
    await expect(page).toHaveURL(/[?&]v=1(&|$)/);

    await page.getByRole('button', { name: 'ALL METRICS' }).click();
    await expect(page).toHaveURL(/[?&]metrics=all(&|$)/);

    await tabVersion(page, 'v2 latest').click();
    await expect(page).not.toHaveURL(/[?&]v=/);
    await expect(page.getByTestId('wf-metrics-head')).not.toContainText('showing v1');
  });

  test('edit label: Enter saves through PATCH, Escape sends nothing', async ({ page }) => {
    const backend = await mockBackend(page);
    await page.goto(URL);
    await expect(page.getByTestId('wf-title')).toHaveText(LABEL);

    await page.getByTestId('wf-label-edit').click();
    const field = page.getByRole('textbox', { name: 'Run label' });
    await field.fill('never sent');
    await field.press('Escape');
    await expect(page.getByTestId('wf-title')).toHaveText(LABEL);
    expect(backend.patches).toEqual([]);

    await page.getByTestId('wf-label-edit').click();
    await field.fill('snake round 1');
    await field.press('Enter');
    await expect(page.getByTestId('wf-title')).toHaveText('snake round 1');
    expect(backend.patches).toEqual([{ label: 'snake round 1' }]);
    await expect(page.getByTestId('wf-header')).toContainText('your label');

    await page.getByTestId('wf-label-edit').click();
    await field.fill('');
    await field.press('Enter');
    await expect(page.getByTestId('wf-title')).toHaveText(LABEL);
    expect(backend.patches).toEqual([{ label: 'snake round 1' }, { label: null }]);
    await expect(page.getByTestId('wf-header')).toContainText('default label');
  });

  test('RECALCULATE METRICS confirms, shows the calculation, then selects v3 latest', async ({
    page,
  }) => {
    const backend = await mockBackend(page);
    await page.goto(URL);

    await page.getByTestId('wf-signal-recalculate').click();
    await expect(page.getByTestId('wf-confirm-recalculate-line')).toHaveText(
      "Creates v3 of this Run's metrics: part A from the Run record. v1 to v2 are kept.",
    );
    await page.getByTestId('wf-confirm-recalculate-yes').click();

    await expect(page.getByTestId('wf-calc-line')).toHaveText('calculating v3 · started 10:00:01');
    await expect(page.getByTestId('wf-signal-recalculate')).toHaveCount(0);

    backend.calcState = 'done';
    await expect(tabVersion(page, 'v3 latest')).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId('wf-calc-line')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-recalculate')).toBeVisible();
  });

  test('a failed calculation prints its line and output and creates no version', async ({
    page,
  }) => {
    await mockBackend(page, { calcState: 'failed', calcOutput: 'MethodError: tokens.input@1' });
    await page.goto(URL);

    await page.getByTestId('wf-signal-recalculate').click();
    await page.getByTestId('wf-confirm-recalculate-yes').click();

    await expect(page.getByTestId('wf-calc-line')).toHaveText(
      'calculation v3 failed · no version created ·',
    );
    await expect(page.getByTestId('wf-calc-output')).toHaveText('MethodError: tokens.input@1');
    await expect(page.getByRole('button', { name: /^v3/ })).toHaveCount(0);
    await expect(tabVersion(page, 'v2 latest')).toBeVisible();
  });

  test('a running Run has no RECALCULATE METRICS and states its values so far', async ({
    page,
  }) => {
    await mockBackend(page, { run: { status: 'running' }, versions: [], latest: null });
    await page.goto(URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByRole('button', { name: 'GATE', exact: true })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    await expect(page.getByTestId('wf-signal-recalculate')).toHaveCount(0);

    await page.getByRole('button', { name: 'METRICS', exact: true }).click();
    await expect(page.getByTestId('wf-metrics')).toContainText(LIVE_LINE);
  });

  test('the CHART view draws figures whose marks are focusable and show a tooltip', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(`${URL}?tab=metrics&view=chart`);

    const charts = page.getByTestId('wf-metrics-charts');
    await expect(charts).toBeVisible();
    const byRole = page.getByRole('figure', { name: 'cost by role' });
    await expect(byRole).toBeVisible();
    await expect(page.getByRole('figure', { name: 'where the money went, by scope' })).toHaveCount(
      1,
    );

    const senior = byRole.getByRole('button', { name: new RegExp(`^${LABEL} .*\\$9\\.00`) });
    await expect(senior).toHaveCount(1);
    await senior.focus();
    await expect(byRole.getByRole('tooltip')).toContainText('$9.00');
  });

  test('PNG downloads a 1640 px wide PNG named after project, label, chart and date', async ({
    page,
  }) => {
    await mockBackend(page);
    await page.goto(`${URL}?tab=metrics&view=chart`);

    await expect(page.getByRole('group', { name: 'PNG background' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'TRANSPARENT' })).toHaveAttribute(
      'aria-pressed',
      'true',
    );

    const control = page.getByRole('button', { name: 'PNG cost by role' });
    await control.focus();
    const [download] = await Promise.all([page.waitForEvent('download'), control.press('Enter')]);
    expect(download.suggestedFilename()).toMatch(
      /^familio-familio-familio-snake-v2-bench-v1-staged-2026-11-10-1023-cost-by-role-\d{4}-\d{2}-\d{2}\.png$/,
    );
    const path = await download.path();
    const png = await readFile(path);
    // PNG signature, then the IHDR chunk: width is the big-endian uint32 at byte 16
    expect(png.subarray(1, 4).toString('ascii')).toBe('PNG');
    expect(png.readUInt32BE(16)).toBe(1640);
    await expect(page.getByText(/^PNG not written/)).toHaveCount(0);
  });

  test('the PNG control takes a mouse click', async ({ page }) => {
    // A real pointer click (no force, no dispatchEvent): Playwright's actionability check
    // fails if the chart head paints over the control (epic 3 retro E1).
    await mockBackend(page);
    await page.goto(`${URL}?tab=metrics&view=chart`);

    const control = page.getByRole('button', { name: 'PNG cost by role' });
    await expect(control).toBeVisible();
    const [download] = await Promise.all([
      page.waitForEvent('download', { timeout: 5_000 }),
      control.click({ timeout: 5_000 }),
    ]);
    expect(download.suggestedFilename()).toMatch(/-cost-by-role-\d{4}-\d{2}-\d{2}\.png$/);
    await expect(page.getByText(/^PNG not written/)).toHaveCount(0);
  });

  test('the preview switch swaps the screen chart for the export image', async ({ page }) => {
    await mockBackend(page);
    await page.goto(`${URL}?tab=metrics&view=chart`);

    await expect(page.getByRole('figure', { name: 'cost by role' })).toBeVisible();
    await page.getByRole('button', { name: 'DARK PAGE' }).click();
    await expect(page.getByRole('img', { name: 'cost by role' })).toBeVisible();
    await expect(page.getByRole('figure', { name: 'cost by role' })).toHaveCount(0);
  });
});

test.describe('/runs — the runs-history cost head hint (epic 3 story 4)', () => {
  test('the cost head carries a hint; the cell text is unchanged', async ({ page }) => {
    await page.route('**/api/metrics/catalogue*', (route) => json(route, CATALOGUE));
    await page.route('**/api/queue*', (route) =>
      json(route, { items: [], next_cursor: null, max_active_runs: 2 }),
    );
    await page.route('**/api/steps*', (route) =>
      json(route, {
        items: [
          {
            attempt_id: '00000000-0000-0000-0000-000000000001',
            run_id: RUN_ID,
            seq: 7,
            started_at: '2026-09-09T08:04:05Z',
            ended_at: '2026-09-09T08:06:35Z',
            seconds: 150,
            project_name: 'familio',
            run_label: LABEL,
            path: 'epics[0].stories[0].build',
            kind: 'agent',
            harness: 'claude',
            model: 'claude-opus-5-5',
            session_id: 'sess-1',
            status: 'done',
            token: 'DON',
            tokens_in: 100,
            tokens_out: 20,
            cost_usd: '0.250000',
            cost_provisional: false,
            trace_url: null,
            log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
          },
        ],
        next_cursor: null,
      }),
    );
    await page.goto('/runs');

    const control = page.getByRole('button', { name: 'how recorded spend is calculated' });
    await expect(control).toBeVisible();
    const dialog = page.getByRole('dialog', { name: 'how recorded spend is calculated' });
    await control.hover();
    await expect(dialog).toHaveCount(0);
    await control.click();
    await expect(dialog).toContainText('method text of spend.recorded');
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);

    await expect(page.getByText('$0.250000')).toBeVisible();
  });
});
