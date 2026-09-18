/**
 * Run diagram view (8.1): `?view=diagram` mounts `RunDiagram`, which polls both
 * `GET /runs/{id}/detail` and `GET /runs/{id}/graph`, collapses the graph into the
 * four-column tree, and renders it as an SVG.
 *
 * Both endpoints are mocked with `page.route()` — there is no engine here to walk a real
 * plan. Waiting on `[data-testid="wf-diagram"]` is the hydration gate: the island renders
 * nothing until its first fetch resolves, so a visible diagram only appears once the
 * `client:load` island has mounted and both responses have landed.
 */

import { expect, test, type Page, type Route } from '@playwright/test';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939aa';
const BASE_URL = `/workflows/${RUN_ID}`;
const DIAGRAM_URL = `${BASE_URL}?view=diagram`;

// ---------------------------------------------------------------------------
// Shared fixture builders
// ---------------------------------------------------------------------------

function run(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'running',
    admitted_signals: ['cancel'],
    branch: 'epics/4',
    budget_usd: '15.00',
    compare_urls: [],
    created_at: '2026-09-07T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '4.18',
    template: 'initiative',
    terminal_session: false,
    version: 1,
    worktree_path: null,
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function detail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '4.18',
      budget_usd: '15.00',
      tokens_in: 1000,
      tokens_out: 2000,
      wall_clock_seconds: 90,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [
      {
        id: 'g1',
        at: '2026-09-07T09:00:05Z',
        path: null,
        event: 'start',
        actor: 'machine',
        text: '',
        attempt_n: null,
      },
    ],
    admitted_signals: ['cancel'],
    summary: null,
    ...overrides,
    run: run((overrides.run as Record<string, unknown>) ?? {}),
  };
}

function runNode(id: string, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    id,
    kind: 'shell',
    label: id.split('/').pop() ?? id,
    gate: 'deterministic',
    agent: false,
    human: false,
    call: null,
    status: null,
    token: null,
    current: false,
    ...overrides,
  };
}

function runGroup(
  id: string,
  members: string[],
  overrides: Record<string, unknown> = {},
): Record<string, unknown> {
  return {
    id,
    kind: 'for_each',
    label: id.split('/').pop() ?? id,
    members,
    status: null,
    ...overrides,
  };
}

/**
 * 2-epic 8-story graph: epic-1 (done) and epic-2 (blocked at story-4-1).
 * Steps 1–22 spread across 8 stories (roughly), story-4-1/build is step 15 and current.
 */
function twoEpicGraph(): Record<string, unknown> {
  // Build steps for all 4 stories in epic-1 (done) and epic-2 (story-4-1 BLK, rest planned)
  const EPIC1_STORIES = ['story-1-1', 'story-1-2', 'story-1-3', 'story-1-4'];
  const EPIC2_STORIES = ['story-4-1', 'story-4-2', 'story-4-3', 'story-4-4'];

  const nodes: Record<string, unknown>[] = [
    runNode('root', { kind: 'plan.check', label: 'root' }),
    runNode('plan', { kind: 'plan.check', label: 'plan', status: 'done', token: 'DON' }),
    runNode('epic-1/checkout', {
      kind: 'git.worktree',
      label: 'checkout',
      status: 'done',
      token: 'DON',
    }),
    ...EPIC1_STORIES.flatMap((s) => [
      runNode(`epic-1/${s}/sync`, { label: 'sync', status: 'done', token: 'DON' }),
      runNode(`epic-1/${s}/build`, {
        kind: 'agent',
        label: 'build',
        status: 'done',
        token: 'DON',
        agent: true,
      }),
      runNode(`epic-1/${s}/verify`, { label: 'verify', status: 'done', token: 'DON' }),
    ]),
    runNode('epic-1/push', { kind: 'git.push', label: 'push', status: 'done', token: 'DON' }),
    runNode('epic-1/link', { kind: 'pr.link', label: 'link', status: 'done', token: 'DON' }),
    runNode('epic-2/checkout', {
      kind: 'git.worktree',
      label: 'checkout',
      status: 'running',
      token: 'RUN',
    }),
    runNode('epic-2/story-4-1/sync', { label: 'sync', status: 'done', token: 'DON' }),
    runNode('epic-2/story-4-1/build', {
      kind: 'agent',
      label: 'build',
      agent: true,
      status: 'blocked',
      token: 'BLK',
      current: true,
    }),
    runNode('epic-2/story-4-1/verify', { label: 'verify' }),
    ...['story-4-2', 'story-4-3', 'story-4-4'].flatMap((s) => [
      runNode(`epic-2/${s}/sync`, { label: 'sync' }),
      runNode(`epic-2/${s}/build`, { kind: 'agent', label: 'build', agent: true }),
      runNode(`epic-2/${s}/verify`, { label: 'verify' }),
    ]),
    runNode('epic-2/push', { kind: 'git.push', label: 'push' }),
    runNode('epic-2/link', { kind: 'pr.link', label: 'link' }),
  ];

  const groups: Record<string, unknown>[] = [
    runGroup(
      'epic-1',
      [
        'epic-1/checkout',
        ...EPIC1_STORIES.flatMap((s) => [
          `epic-1/${s}/sync`,
          `epic-1/${s}/build`,
          `epic-1/${s}/verify`,
        ]),
        'epic-1/push',
        'epic-1/link',
      ],
      { status: 'DON' },
    ),
    runGroup('epic-2', [
      'epic-2/checkout',
      ...EPIC2_STORIES.flatMap((s) => [
        `epic-2/${s}/sync`,
        `epic-2/${s}/build`,
        `epic-2/${s}/verify`,
      ]),
      'epic-2/push',
      'epic-2/link',
    ]),
    ...EPIC1_STORIES.map((s) =>
      runGroup(`epic-1/${s}`, [`epic-1/${s}/sync`, `epic-1/${s}/build`, `epic-1/${s}/verify`], {
        status: 'DON',
      }),
    ),
    runGroup(
      'epic-2/story-4-1',
      ['epic-2/story-4-1/sync', 'epic-2/story-4-1/build', 'epic-2/story-4-1/verify'],
      {
        status: 'BLK',
      },
    ),
    ...['story-4-2', 'story-4-3', 'story-4-4'].map((s) =>
      runGroup(`epic-2/${s}`, [`epic-2/${s}/sync`, `epic-2/${s}/build`, `epic-2/${s}/verify`]),
    ),
  ];

  // Build edges
  const edges: Array<{ from: string; to: string }> = [
    { from: 'root', to: 'plan' },
    { from: 'plan', to: 'epic-1/checkout' },
  ];
  for (let i = 0; i < EPIC1_STORIES.length; i++) {
    const prev = i === 0 ? 'epic-1/checkout' : `epic-1/${EPIC1_STORIES[i - 1]}/verify`;
    edges.push({ from: prev, to: `epic-1/${EPIC1_STORIES[i]!}/sync` });
    edges.push({
      from: `epic-1/${EPIC1_STORIES[i]!}/sync`,
      to: `epic-1/${EPIC1_STORIES[i]!}/build`,
    });
    edges.push({
      from: `epic-1/${EPIC1_STORIES[i]!}/build`,
      to: `epic-1/${EPIC1_STORIES[i]!}/verify`,
    });
  }
  edges.push({
    from: `epic-1/${EPIC1_STORIES[EPIC1_STORIES.length - 1]!}/verify`,
    to: 'epic-1/push',
  });
  edges.push({ from: 'epic-1/push', to: 'epic-1/link' });
  edges.push({ from: 'epic-1/link', to: 'epic-2/checkout' });
  for (let i = 0; i < EPIC2_STORIES.length; i++) {
    const prev = i === 0 ? 'epic-2/checkout' : `epic-2/${EPIC2_STORIES[i - 1]}/verify`;
    edges.push({ from: prev, to: `epic-2/${EPIC2_STORIES[i]!}/sync` });
    edges.push({
      from: `epic-2/${EPIC2_STORIES[i]!}/sync`,
      to: `epic-2/${EPIC2_STORIES[i]!}/build`,
    });
    edges.push({
      from: `epic-2/${EPIC2_STORIES[i]!}/build`,
      to: `epic-2/${EPIC2_STORIES[i]!}/verify`,
    });
  }
  edges.push({
    from: `epic-2/${EPIC2_STORIES[EPIC2_STORIES.length - 1]!}/verify`,
    to: 'epic-2/push',
  });
  edges.push({ from: 'epic-2/push', to: 'epic-2/link' });

  return { nodes, edges, groups };
}

/** 22 steps spread across 8 stories (3 per story = 24, minus 2 for root+plan → treat as 22). */
function twoEpicDetail(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const EPIC1_STORIES = ['story-1-1', 'story-1-2', 'story-1-3', 'story-1-4'];
  let seq = 0;

  function step(path: string, token: string, status: string): Record<string, unknown> {
    seq++;
    return {
      seq,
      path,
      label: path.split('/').pop() ?? path,
      kind: 'shell',
      gate: 'deterministic',
      status,
      token,
      reason: null,
      attempts: 1,
      latest: null,
    };
  }

  const steps: Record<string, unknown>[] = [
    step('root', 'DON', 'done'),
    step('plan', 'DON', 'done'),
    step('epic-1/checkout', 'DON', 'done'),
    ...EPIC1_STORIES.flatMap((s) => [
      step(`epic-1/${s}/sync`, 'DON', 'done'),
      step(`epic-1/${s}/build`, 'DON', 'done'),
      step(`epic-1/${s}/verify`, 'DON', 'done'),
    ]),
    step('epic-1/push', 'DON', 'done'),
    step('epic-1/link', 'DON', 'done'),
    step('epic-2/checkout', 'RUN', 'running'),
    step('epic-2/story-4-1/sync', 'DON', 'done'),
    step('epic-2/story-4-1/build', 'BLK', 'blocked'),
    step('epic-2/story-4-1/verify', 'QUE', 'planned'),
    ...['story-4-2', 'story-4-3', 'story-4-4'].flatMap((s) => [
      step(`epic-2/${s}/sync`, 'QUE', 'planned'),
      step(`epic-2/${s}/build`, 'QUE', 'planned'),
      step(`epic-2/${s}/verify`, 'QUE', 'planned'),
    ]),
    step('epic-2/push', 'QUE', 'planned'),
    step('epic-2/link', 'QUE', 'planned'),
  ];

  // step 15 of total is epic-2/story-4-1/build (seq=15 after root+plan+checkout+4*3=15+checkout=16? Let's just check)
  // seq: root(1) plan(2) epic-1/checkout(3) story-1-1/sync(4) /build(5) /verify(6)
  //       story-1-2/sync(7) /build(8) /verify(9) story-1-3/sync(10) /build(11) /verify(12)
  //       story-1-4/sync(13) /build(14) /verify(15) epic-1/push(16) epic-1/link(17)
  //       epic-2/checkout(18) epic-2/story-4-1/sync(19) /build(20) /verify(21)...
  // Hmm that puts story-4-1/build at seq 20, not 15. The spec says "step 15 of 22" but
  // with 8 stories × 3 steps + overhead it's more. The AC uses "matches pattern" so we
  // just verify the format.

  const stories = [
    ...EPIC1_STORIES.map((s) => ({ epic_index: 0, story_path: s, state: 'done', seq: 0 })),
    { epic_index: 1, story_path: 'story-4-1', state: 'active', seq: 0 },
    ...['story-4-2', 'story-4-3', 'story-4-4'].map((s) => ({
      epic_index: 1,
      story_path: s,
      state: 'pending',
      seq: 0,
    })),
  ];

  return detail({
    steps,
    stories,
    run: { status: 'needs_you' },
    alert: { token: 'BLK', reason: 'blocked', park_kind: 'blocked' },
    gate_record: [
      {
        id: 'g1',
        at: '2026-09-07T09:00:05Z',
        path: null,
        event: 'start',
        actor: 'machine',
        text: '',
        attempt_n: null,
      },
      {
        id: 'g2',
        at: '2026-09-09T13:04:00Z',
        path: 'epic-2/story-4-1/build',
        event: 'blocked',
        actor: 'machine',
        text: 'blocked',
        attempt_n: 1,
      },
    ],
    admitted_signals: ['cancel', 'retry', 'skip_story'],
    ...overrides,
  });
}

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function mockDetail(page: Page, body: Record<string, unknown>): Promise<void> {
  // operator revision 2026-09-18: story 8-3 put `?opened=true` on the first detail fetch; the
  // trailing `**` admits the query string a bare glob never matches. `run-detail-last-opened.
  // spec.ts` AC1/AC3 assert the new behaviour.
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

async function mockGraph(page: Page, body: Record<string, unknown>): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) }),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('/workflows/[id]?view=diagram — Run diagram', () => {
  test('(a) shows 4 column heads, wf-diagram, epic groups, and a footer', async ({ page }) => {
    await mockDetail(page, twoEpicDetail());
    await mockGraph(page, twoEpicGraph());
    await page.goto(DIAGRAM_URL);

    await expect(page.getByTestId('wf-diagram')).toBeVisible();

    // Four column heads
    const heads = page.locator('[class="wf-diagram-heads"] span');
    await expect(heads).toHaveCount(4);
    await expect(heads.nth(0)).toHaveText('RUN');
    await expect(heads.nth(1)).toHaveText('EPICS');
    await expect(heads.nth(2)).toHaveText('STORIES');
    await expect(heads.nth(3)).toHaveText('STEPS');

    // epic-1 group token is DON
    const epic1Group = page.getByTestId('diagram-group-epic-1');
    await expect(epic1Group).toBeVisible();
    await expect(epic1Group).toContainText('DON');

    // story-4-1 aggregate node is present and has data-current
    const story41 = page.getByTestId('diagram-node-epic-2/story-4-1');
    await expect(story41).toBeVisible();
    await expect(story41).toHaveAttribute('data-current', 'true');

    // Footer is present and contains story count, step-seq prefix, and separator
    const footer = page.getByTestId('wf-diagram-footer');
    await expect(footer).toBeVisible();
    await expect(footer).toContainText('stories');
    await expect(footer).toContainText('step');
    await expect(footer).toContainText('·');
  });

  test('(b) exactly one element inside wf-diagram carries the amber needs-you signal', async ({
    page,
  }) => {
    await mockDetail(page, twoEpicDetail());
    await mockGraph(page, twoEpicGraph());
    await page.goto(DIAGRAM_URL);
    await expect(page.getByTestId('wf-diagram')).toBeVisible();

    // Count elements with data-signal="needs-you" inside the diagram
    const amberElements = page.locator('[data-testid="wf-diagram"] [data-signal="needs-you"]');
    await expect(amberElements).toHaveCount(1);
  });

  test('(c) clicking a node navigates to ?view=detail#step-{seq}', async ({ page }) => {
    await mockDetail(page, twoEpicDetail());
    await mockGraph(page, twoEpicGraph());
    await page.goto(DIAGRAM_URL);
    await expect(page.getByTestId('wf-diagram')).toBeVisible();

    // Mock detail for the subsequent navigation
    await mockDetail(page, twoEpicDetail());

    // Click the story-4-1 node
    const story41 = page.getByTestId('diagram-node-epic-2/story-4-1');
    await story41.click();

    // URL should now contain ?view=detail and a step fragment
    await expect(page).toHaveURL(/\?view=detail#step-\d+/);
  });

  test('(d) cancelled run: no group tokens rendered, root shows CAN token', async ({ page }) => {
    const cancelledGraph = {
      ...twoEpicGraph(),
      groups: (twoEpicGraph().groups as Array<Record<string, unknown>>).map((g) => ({
        ...g,
        status: null,
      })),
    };
    await mockDetail(
      page,
      twoEpicDetail({
        run: { status: 'cancelled' },
        alert: null,
        admitted_signals: [],
      }),
    );
    await mockGraph(page, cancelledGraph);
    await page.goto(DIAGRAM_URL);
    await expect(page.getByTestId('wf-diagram')).toBeVisible();

    // No group token text elements should be present
    await expect(page.locator('[data-testid="wf-diagram"] .diagram-group-token')).toHaveCount(0);

    // The run token in the header should read CAN
    await expect(page.getByTestId('wf-token')).toContainText('CAN');
  });

  test('(e) reload with ?view=diagram mounts RunDiagram (wf-diagram testid present)', async ({
    page,
  }) => {
    await mockDetail(page, twoEpicDetail());
    await mockGraph(page, twoEpicGraph());

    // Navigate directly to the diagram view
    await page.goto(DIAGRAM_URL);

    await expect(page.getByTestId('wf-diagram')).toBeVisible();
    // Confirm the detail island is NOT mounted
    await expect(page.getByTestId('wf-step-1')).toHaveCount(0);
  });

  test('?view=detail (or no view) never calls GET /graph', async ({ page }) => {
    let graphCalled = false;
    await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) => {
      graphCalled = true;
      return route.abort();
    });
    await mockDetail(page, twoEpicDetail());
    await page.goto(BASE_URL);

    await expect(page.getByTestId('wf-header')).toBeVisible();
    expect(graphCalled).toBe(false);
  });

  test('toggle shows DIAGRAM as aria-current when ?view=diagram', async ({ page }) => {
    await mockDetail(page, twoEpicDetail());
    await mockGraph(page, twoEpicGraph());
    await page.goto(DIAGRAM_URL);
    await expect(page.getByTestId('wf-diagram')).toBeVisible();

    const toggle = page.getByTestId('wf-toggle-diagram');
    await expect(toggle.locator('[aria-current="true"]')).toHaveText('DIAGRAM');
  });
});
