/**
 * The embedded run diagram, v3 (2026-09-24): a ranked-column hierarchy on React Flow.
 *
 * Rewritten from the 8.1 spec, which drove a `?view=diagram` page that no longer exists and
 * a fixture whose group ids (`epic-1/story-4-1`) no backend ever produced. Every id here is
 * the bracket-index shape `application/graph.py` actually emits, which is the whole point of
 * the rework: the hierarchy is read off those prefixes, and a fixture that does not carry
 * them proves nothing about the product.
 *
 * Graph and detail both come from `tests/fixtures/`, typed against `components['schemas']`
 * and shared with the unit suite. This file kept untyped copies of both for one iteration;
 * the graph had already drifted from the unit suite's, and the detail's `stories` carried a
 * `story_path` that `StoryCellOut` has never had.
 *
 * **The clock is installed before every navigation.** The footer states an age against the
 * Run's `created_at`, so a wall-clock assertion drifts by a day every day and breaks outright
 * on a machine whose clock is before the fixture's date. `run-activity.spec.ts` set the
 * precedent.
 */

import { expect, test, type Page, type Route } from '@playwright/test';

import { frameLessGraph, frameLessSteps, twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';
import {
  runDetail,
  RUN_ID,
  STARTED_AT,
  withSteps,
  type DetailOverrides,
} from '../fixtures/run-detail';
import type { components } from '../../src/api/schema';

type RunGraphOut = components['schemas']['RunGraphOut'];
type StepRowOut = components['schemas']['StepRowOut'];

const BASE_URL = `/workflows/${RUN_ID}`;
/** 42 minutes into the Run, fixed — so the footer's age is a constant, not a countdown. */
const NOW = new Date(Date.parse(STARTED_AT) + 42 * 60_000);
/** `$poll` ticks every 5 s while a Run is running (`stores/poll.ts`). */
const POLL_MS = 5_000;

// ---------------------------------------------------------------------------
// Route helpers
// ---------------------------------------------------------------------------

async function mockDetail(page: Page, body: () => ReturnType<typeof runDetail>): Promise<void> {
  // `**` admits the `?opened=true` of the first fetch (story 8-3).
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body()) }),
  );
}

async function mockGraph(page: Page, body: () => RunGraphOut): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/graph`, (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body()) }),
  );
}

/** The artboard's Run, and the steps the detail poll returns for it. */
function twoEpic(overrides: Record<string, Partial<StepRowOut>> = {}) {
  return { graph: twoEpicGraph(), steps: withSteps(twoEpicSteps(), overrides) };
}

function frameLess(overrides: Record<string, Partial<StepRowOut>> = {}) {
  return { graph: frameLessGraph(), steps: withSteps(frameLessSteps(), overrides) };
}

async function mockRun(
  page: Page,
  fixture: { graph: RunGraphOut; steps: StepRowOut[] },
  detailOverrides: DetailOverrides = {},
): Promise<void> {
  await mockDetail(page, () => runDetail(fixture.steps, detailOverrides));
  await mockGraph(page, () => fixture.graph);
}

async function openDiagram(page: Page, url: string = BASE_URL): Promise<void> {
  await page.clock.install({ time: NOW });
  await page.goto(url);
  await expect(page.getByTestId('wf-diagram')).toBeVisible();
  await expect(page.getByTestId('wf-diagram-node-root')).toBeVisible();
  await settle(page);
}

/**
 * Wait for the initial `fitView` to finish moving things.
 *
 * React Flow applies the fit after mount, so a box read the moment a card appears is a box
 * mid-transition — and a later assertion that the layout *returned* to it then compares two
 * viewports.
 */
async function settle(page: Page): Promise<void> {
  const root = page.getByTestId('wf-diagram-node-root');
  let last = '';
  await expect
    .poll(async () => {
      const box = await root.boundingBox();
      expect(box, 'the root card has a box to settle on').not.toBeNull();
      const here = `${Math.round(box!.x)},${Math.round(box!.y)}`;
      const stable = here === last;
      last = here;
      return stable;
    })
    .toBe(true);
}

/**
 * One card's placed position, in canvas coordinates.
 *
 * Read off the node's own transform rather than its bounding box: React Flow auto-pans the
 * canvas while a node is dragged near the pane edge, so a screen box compares two viewports
 * and says a card moved when only the camera did.
 */
async function placedAt(page: Page, id: string): Promise<{ x: number; y: number }> {
  const transform = await page
    .locator(`.react-flow__node[data-id="${id}"]`)
    .evaluate((element) => (element as HTMLElement).style.transform);
  const found = /translate\(([-\d.]+)px,\s*([-\d.]+)px\)/.exec(transform);
  expect(found, `node ${id} carries a translate transform`).not.toBeNull();
  return { x: Math.round(Number(found![1])), y: Math.round(Number(found![2])) };
}

/** Every pair of cards that share screen space — the tree is a layout, not a pile. */
async function overlappingCards(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const boxes = [...document.querySelectorAll('.react-flow__node')].map((element) => ({
      id: (element as HTMLElement).dataset.id ?? '',
      box: element.getBoundingClientRect(),
    }));
    const clashes: string[] = [];
    for (let i = 0; i < boxes.length; i += 1) {
      for (let j = i + 1; j < boxes.length; j += 1) {
        const a = boxes[i]!;
        const b = boxes[j]!;
        const over =
          a.box.left < b.box.right &&
          b.box.left < a.box.right &&
          a.box.top < b.box.bottom &&
          b.box.top < a.box.bottom;
        if (over) clashes.push(`${a.id} / ${b.id}`);
      }
    }
    return clashes;
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe('/workflows/[id] — the run diagram (v3)', () => {
  test('draws four rank columns under the four heads, joining no two sibling stories', async ({
    page,
  }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    for (const rank of ['0', '1', '2', '3']) {
      await expect(
        page.locator(`[data-testid="wf-diagram"] .wf-node[data-rank="${rank}"]`).first(),
      ).toBeVisible();
    }
    // the heads describe the columns actually drawn, every one of them
    await expect(page.locator('.wf-flow-head-node')).toHaveText([
      'RUN',
      'EPICS',
      'STORIES + EPIC AGENTS',
      'AGENTS',
    ]);
    expect(await overlappingCards(page)).toEqual([]);

    await expect(page.locator('[data-id="epics[1]->epics[1].stories[0]"]')).toHaveCount(1);
    await expect(page.locator('[data-id="epics[1].stories[0]->epics[1].stories[1]"]')).toHaveCount(
      0,
    );
    await expect(page.locator('[data-id="epics[1].stories[1]->epics[1].stories[0]"]')).toHaveCount(
      0,
    );
  });

  test('renders a story’s deterministic rows as a guardrail strip and as no node', async ({
    page,
  }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    const strip = page.getByTestId('wf-diagram-guardrail-epics.1.stories.0');
    await expect(strip).toBeVisible();
    for (const stepId of ['sync', 'verify', 'commit-guard']) {
      await expect(
        page.getByTestId(`wf-diagram-guardrail-epics.1.stories.0-${stepId}`),
      ).toBeVisible();
      await expect(page.getByTestId(`wf-diagram-node-epics.1.stories.0.${stepId}`)).toHaveCount(0);
    }
    // the strip is information: it carries no control of its own, and it says its states in
    // words rather than in a dot alone
    await expect(strip.locator('button')).toHaveCount(0);
    // the separator is markup and each dot has its word beside it, so the strip reads as
    // words rather than as `syncverifycommit-guard`
    // each dot is a glyph as well as a hue, and each entry says its state in words
    await expect(strip).toHaveText('■sync done · □verify queued · □commit-guard queued');
  });

  test('shows a row that belongs to no frame on the root card', async ({ page }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    // `plan` sits outside every `epics[i]`; the root built a strip for it and drew none
    await expect(page.getByTestId('wf-diagram-guardrail-root-plan')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-node-plan')).toHaveCount(0);
  });

  test('draws one retry chip per failed attempt, each looping back on a dashed edge', async ({
    page,
  }) => {
    await mockRun(page, twoEpic({ 'epics[1].stories[0].build': { attempts: 3 } }));
    await openDiagram(page);

    await expect(page.getByTestId('wf-diagram-retry-epics.1.stories.0.build-1')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-retry-epics.1.stories.0.build-2')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-retry-epics.1.stories.0.build-3')).toHaveCount(0);

    const retryEdges = page.locator('[data-testid="wf-diagram"] g.wf-flow-edge-retry');
    await expect(retryEdges).toHaveCount(2);
    await expect(retryEdges.first().locator('path.react-flow__edge-path')).toHaveCSS(
      'stroke-dasharray',
      '3px, 3px',
    );
  });

  test('draws no failure chip for a checkpoint park — the designed stop is not a failure', async ({
    page,
  }) => {
    await mockRun(
      page,
      twoEpic({
        'epics[1].stories[0].build': { attempts: 2, status: 'checkpoint', token: 'CHK' },
      }),
    );
    await openDiagram(page);

    // two attempts, the newest of them parked at a checkpoint: one failed, not two
    await expect(page.getByTestId('wf-diagram-retry-epics.1.stories.0.build-1')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-retry-epics.1.stories.0.build-2')).toHaveCount(0);
  });

  test('navigates from the CTA alone — the card body is a drag handle', async ({ page }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    const card = page.getByTestId('wf-diagram-node-epics.1.stories.0.build');
    await card.locator('.wf-node-title').click();
    await expect(page).toHaveURL(new RegExp(`${RUN_ID}$`));

    // a real link: the URL is on the element, so cmd-click and copy-link work too
    const cta = page.getByTestId('wf-diagram-open-epics.1.stories.0.build');
    await expect(cta).toHaveAttribute('href', `${BASE_URL}/steps/epics.1.stories.0.build`);
    await cta.click();
    await expect(page).toHaveURL(`${BASE_URL}/steps/epics.1.stories.0.build`);
  });

  test('gives the blue border to the current step alone, and the RUN word to its ancestors', async ({
    page,
  }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    const running = page.locator('[data-testid="wf-diagram"] .wf-node[data-status="running"]');
    await expect(running).toHaveCount(1);
    await expect(running).toHaveAttribute('data-testid', 'wf-diagram-node-epics.1.stories.0.build');

    for (const id of ['wf-diagram-node-root', 'wf-diagram-node-epics.1']) {
      const ancestor = page.getByTestId(id);
      await expect(ancestor).toHaveAttribute('data-status', 'inflight');
      await expect(ancestor.locator('.wf-node-token')).toHaveText('RUN');
    }
  });

  test('keeps a stopped step red and says the word beside it', async ({ page }) => {
    const fixture = twoEpic({
      'epics[1].stories[0].build': { attempts: 2, status: 'error', token: 'ERR' },
    });
    fixture.graph = twoEpicGraph({ status: 'error', token: 'ERR' });
    await mockRun(page, fixture, {
      run: { status: 'needs_you' },
      alert: { token: 'BLK', reason: 'harness exit 1', park_kind: 'blocked' },
    });
    await openDiagram(page);

    const card = page.getByTestId('wf-diagram-node-epics.1.stories.0.build');
    await expect(card).toHaveAttribute('data-status', 'error');
    await expect(card.locator('.wf-node-token')).toHaveText('ERR');
    // a row is `error`; the Run above it is `blocked` — the footer reads the Run's word
    await expect(card).toHaveAccessibleName('build · error · current step');
    await expect(page.getByTestId('wf-diagram-footer')).toContainText('· blocked ');
    // both attempts failed here: `error` is the one status whose newest attempt did
    await expect(page.getByTestId('wf-diagram-retry-epics.1.stories.0.build-2')).toBeVisible();
  });

  test('expands and collapses an epic in place, one level per click', async ({ page }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.0')).toHaveCount(0);

    const caret = page.getByTestId('wf-diagram-toggle-epics.0');
    await expect(caret).toHaveAttribute('aria-expanded', 'false');
    await caret.click();

    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.0')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-toggle-epics.0')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.0.build')).toHaveCount(0);

    // the tree the operator opened is a different tree, and it is re-laid out as one:
    // keeping the pre-expansion positions dropped the revealed children on the placed cards
    expect(await overlappingCards(page)).toEqual([]);

    await page.getByTestId('wf-diagram-toggle-epics.0').click();
    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.0')).toHaveCount(0);
    expect(await overlappingCards(page)).toEqual([]);
  });

  test('keeps a dragged card put on a poll, and returns it on reset layout', async ({ page }) => {
    // the step stops rather than finishes, so it stays `current` and the tree the reload
    // computes still opens the same path — what changes is the word on the card
    let settled = false;
    const running = twoEpicGraph();
    const stopped = twoEpicGraph({ status: 'blocked', token: 'BLK' });
    await mockDetail(page, () => runDetail(withSteps(twoEpicSteps())));
    await mockGraph(page, () => (settled ? stopped : running));
    await openDiagram(page);

    // the React Flow node is keyed by the bracket id; the test id is its dot-index form
    const id = 'epics[1].stories[0].build';
    const card = page.getByTestId('wf-diagram-node-epics.1.stories.0.build');
    const computed = await placedAt(page, id);
    const box = (await card.boundingBox())!;
    await page.mouse.move(box.x + box.width / 2, box.y + 10);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width / 2 + 90, box.y + 70, { steps: 8 });
    await page.mouse.up();

    const dragged = await placedAt(page, id);
    expect(dragged.x).toBeGreaterThan(computed.x);
    expect(dragged.y).toBeGreaterThan(computed.y);

    settled = true;
    // the diagram re-fetches on the shared poll tick
    await page.clock.runFor(POLL_MS + 500);
    await expect(card.locator('.wf-node-token')).toHaveText('BLK');

    // the status swapped in place: the card is exactly where the operator left it
    expect(await placedAt(page, id)).toEqual(dragged);

    // `reset layout` restores the computed tree without a reload
    await page.getByTestId('wf-diagram-reset').click();
    await expect.poll(async () => await placedAt(page, id)).toEqual(computed);

    // and nothing was persisted: a reload computes the same tree again
    await page.reload();
    await expect(page.getByTestId('wf-diagram-node-root')).toBeVisible();
    expect(await placedAt(page, id)).toEqual(computed);
  });

  test('fits the tree to the canvas, and states the zoom it fitted at', async ({ page }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    const zoom = page.getByTestId('wf-diagram-zoom');
    // the readout follows the canvas rather than its own initial `100%`: the whole tree is
    // wider than the column it sits in, so a fitted diagram is never at 100 %
    await expect(zoom).not.toHaveText('100%');

    await page.getByTestId('wf-diagram-fit').click();
    const fitted = (await zoom.textContent())!;
    expect(fitted).toMatch(/^\d+%$/);

    // zoom in, then `fit` puts the whole tree back and the readout follows it
    await page.mouse.move(600, 400);
    await page.keyboard.down('Control');
    await page.mouse.wheel(0, -400);
    await page.keyboard.up('Control');
    await expect.poll(async () => await zoom.textContent()).not.toBe(fitted);

    await page.getByTestId('wf-diagram-fit').click();
    await expect.poll(async () => await zoom.textContent()).toBe(fitted);
  });

  test('serves the run detail for ?view=diagram, with no redirect and no toggle', async ({
    page,
  }) => {
    await mockRun(page, twoEpic());

    const response = await page.goto(`${BASE_URL}?view=diagram`);

    expect(response?.status()).toBe(200);
    expect(response?.request().redirectedFrom()).toBeNull();
    await expect(page).toHaveURL(`${BASE_URL}?view=diagram`);
    await expect(page.getByTestId('wf-header')).toBeVisible();
    await expect(page.getByTestId('wf-toggle-diagram')).toHaveCount(0);
    await expect(page.getByTestId('wf-diagram')).toBeVisible();
  });

  test('says `no steps planned` and draws no canvas for an empty plan', async ({ page }) => {
    await mockDetail(page, () => runDetail([], { stories: [] }));
    await mockGraph(page, () => ({ nodes: [], edges: [], groups: [] }));

    await page.clock.install({ time: NOW });
    await page.goto(BASE_URL);

    await expect(page.getByText('no steps planned')).toBeVisible();
    await expect(page.getByTestId('wf-diagram')).toHaveCount(0);
  });

  test('states the whole footer readout, and keeps the controls around the canvas', async ({
    page,
  }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    await expect(page.getByTestId('wf-diagram-fit')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-reset')).toBeVisible();
    // `step {seq} of {n} · {label} · {run word} {age} · {k}/{n} stories`
    await expect(page.getByTestId('wf-diagram-footer')).toHaveText(
      'step 22 of 35 · epic 2 · story 2-1 · build · running 42m · 2/4 stories',
    );
    // the attribution React Flow asks for stays visible
    await expect(page.locator('.react-flow__attribution')).toBeVisible();
  });

  test('names the canvas and every card on it, in words', async ({ page }) => {
    await mockRun(page, twoEpic());
    await openDiagram(page);

    // the canvas says what it holds; `stepsDone` counts the `done` rows of the plan
    await expect(page.getByTestId('wf-diagram')).toHaveAttribute(
      'aria-label',
      'run epics/4 · 20/35 steps',
    );

    // every card is a tab stop carrying its own name — the current step and the ancestors
    // that hold it both read `RUN`, so the name says which is which
    await expect(page.getByTestId('wf-diagram-node-root')).toHaveAttribute('tabindex', '0');
    await expect(page.getByTestId('wf-diagram-node-root')).toHaveAccessibleName(
      'initiative · running · holds the current step',
    );
    await expect(page.getByTestId('wf-diagram-node-epics.1.stories.0.build')).toHaveAccessibleName(
      'build · running · current step',
    );
    await expect(page.getByTestId('wf-diagram-node-epics.0')).toHaveAccessibleName('epic 1 · done');
  });

  test('carries exactly one amber element while the Run needs you', async ({ page }) => {
    // 8.1 asserted this of the SVG surface; the v3 surface makes the same promise —
    // one reason the operator is needed, findable by colour from the root down
    await mockRun(
      page,
      twoEpic({ 'epics[1].stories[0].build': { status: 'blocked', token: 'BLK' } }),
      {
        run: { status: 'needs_you' },
        alert: { token: 'BLK', reason: 'blocked', park_kind: 'blocked' },
      },
    );
    await mockGraph(page, () => twoEpicGraph({ status: 'blocked', token: 'BLK' }));
    await openDiagram(page);

    const amber = page.locator(
      '[data-testid="wf-diagram"] .wf-node[data-status="blocked"],' +
        ' [data-testid="wf-diagram"] .wf-node[data-status="checkpoint"]',
    );
    await expect(amber).toHaveCount(1);
    await expect(amber).toHaveAttribute('data-testid', 'wf-diagram-node-epics.1.stories.0.build');
    // and the ancestors that hold it keep the neutral hairline, not a second amber box
    await expect(page.getByTestId('wf-diagram-node-epics.1')).toHaveAttribute(
      'data-status',
      'inflight',
    );
  });

  test('cancelled run: no group carries a token, and the root reads CAN', async ({ page }) => {
    // 8.1's case (d), re-asserted against the v3 cards: `SPEC CAP-12` sends `status: null`
    // on every group of a cancelled Run, and a group with no status states none
    const graph = twoEpicGraph();
    const cancelled: RunGraphOut = {
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === 'root'
          ? { ...node, status: 'cancelled', token: 'CAN' }
          : { ...node, current: false },
      ),
      groups: graph.groups.map((group) => ({ ...group, status: null })),
    };
    await mockDetail(page, () =>
      runDetail(withSteps(twoEpicSteps()), {
        run: { status: 'cancelled', admitted_signals: [] },
        admitted_signals: [],
      }),
    );
    await mockGraph(page, () => cancelled);
    await openDiagram(page);

    await expect(page.getByTestId('wf-diagram-node-root').locator('.wf-node-token')).toHaveText(
      'CAN',
    );
    for (const id of ['epics.0', 'epics.1', 'epics.2']) {
      await expect(page.getByTestId(`wf-diagram-node-${id}`)).toHaveAttribute(
        'data-status',
        'none',
      );
      await expect(page.getByTestId(`wf-diagram-node-${id}`).locator('.wf-node-token')).toHaveCount(
        0,
      );
    }
  });

  test('keeps the newest failed attempts, and the exit code they carry', async ({ page }) => {
    await mockRun(
      page,
      twoEpic({
        'epics[1].stories[0].build': {
          attempts: 9,
          status: 'error',
          token: 'ERR',
          latest: {
            n: 9,
            harness: 'claude',
            model: 'sonnet',
            seconds: 12,
            exit_code: 1,
            cost_usd: null,
            ended_at: null,
            started_at: null,
            log_tail: [],
          },
        },
      }),
    );
    await openDiagram(page);

    const path = 'epics.1.stories.0.build';
    // nine failures, four chips: the newest four, so the one code on the wire survives
    await expect(page.getByTestId(`wf-diagram-retry-${path}-6`)).toBeVisible();
    await expect(page.getByTestId(`wf-diagram-retry-${path}-9`)).toContainText('exit 1');
    await expect(page.getByTestId(`wf-diagram-retry-${path}-1`)).toHaveCount(0);
    // and the five before them are a chip of their own, above the stack
    await expect(page.getByTestId(`wf-diagram-retry-${path}-more`)).toContainText('+5');
    expect(await overlappingCards(page)).toEqual([]);
  });

  test('re-opens the path to the current step when the Run moves into it', async ({ page }) => {
    // a Run opened while `queued` has no current step at all, so the first response cannot
    // seed the tree; once-only seeding meant it never opened itself when one started
    const queued = twoEpicGraph();
    let started = false;
    await mockDetail(page, () => runDetail(withSteps(twoEpicSteps())));
    await mockGraph(page, () =>
      started
        ? twoEpicGraph()
        : {
            ...queued,
            nodes: queued.nodes.map((node) => ({ ...node, current: false })),
          },
    );
    await openDiagram(page);

    // nothing is current, so nothing is open: the epics are all collapsed
    await expect(page.getByTestId('wf-diagram-node-epics.1.stories.0')).toHaveCount(0);

    // the operator opens one by hand while they wait
    await page.getByTestId('wf-diagram-toggle-epics.0').click();
    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.0')).toBeVisible();

    started = true;
    await page.clock.runFor(POLL_MS + 500);

    // the path to the step that started is open, with no click …
    await expect(page.getByTestId('wf-diagram-node-epics.1.stories.0.build')).toBeVisible();
    // … and what the operator opened is still open: the seed merges, it does not replace
    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.0')).toBeVisible();
  });

  test('swaps statuses on a poll without closing what is open', async ({ page }) => {
    let settled = false;
    await mockDetail(page, () => runDetail(withSteps(twoEpicSteps())));
    await mockGraph(page, () =>
      settled ? twoEpicGraph({ status: 'blocked', token: 'BLK' }) : twoEpicGraph(),
    );
    await openDiagram(page);

    await page.getByTestId('wf-diagram-toggle-epics.0').click();
    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.1')).toBeVisible();

    settled = true;
    await page.clock.runFor(POLL_MS + 500);

    const card = page.getByTestId('wf-diagram-node-epics.1.stories.0.build');
    await expect(card.locator('.wf-node-token')).toHaveText('BLK');
    // the expansion is state of this section, and a re-fetch is not a reason to drop it
    await expect(page.getByTestId('wf-diagram-node-epics.0.stories.1')).toBeVisible();
    await expect(page.getByTestId('wf-diagram-toggle-epics.0')).toHaveAttribute(
      'aria-expanded',
      'true',
    );
  });

  test('sends no React Flow from the server', async ({ request }) => {
    // `DiagramSection` is a child of the `RunDetail` island, so `client:only` cannot reach
    // it and Astro renders it server-side. React Flow would measure a DOM that is not there.
    const html = await (await request.get(BASE_URL)).text();

    expect(html).toContain('<astro-island');
    expect(html).not.toContain('react-flow');
    expect(html).not.toContain('wf-diagram-node-root');
    expect(html).not.toContain('wf-flow-head-node');
  });

  test('stands the skeleton in until the graph lands, and says what it is waiting for', async ({
    page,
  }) => {
    // the mount guard's visible half: no canvas until the browser has run an effect and the
    // graph has answered
    let release = () => {};
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    await mockDetail(page, () => runDetail(withSteps(twoEpicSteps())));
    await page.route(`**/api/runs/${RUN_ID}/graph`, async (route: Route) => {
      await held;
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(twoEpicGraph()),
      });
    });

    await page.clock.install({ time: NOW });
    await page.goto(BASE_URL);

    const skeleton = page.locator('.wf-diagram-skeleton');
    await expect(skeleton).toBeVisible();
    await expect(skeleton).toHaveAttribute('role', 'status');
    await expect(skeleton).toHaveAttribute('aria-busy', 'true');
    await expect(skeleton).toHaveText('loading the run diagram');
    await expect(page.getByTestId('wf-diagram')).toHaveCount(0);

    release();
    await expect(page.getByTestId('wf-diagram')).toBeVisible();
    await expect(skeleton).toHaveCount(0);
  });
});

test.describe('/workflows/[id] — a Run with no epics[i] or stories[j] frame', () => {
  // `story@1`, `task@1` and `repo-init@1` plan bare top-level rows, and DiagramSection
  // mounts for every Run: a fixed four-rank model drew `build` under the `EPICS` head and
  // hid `sync`, `verify` and `commit-guard` entirely (operator amendment, 2026-09-24).
  test('draws two columns headed RUN and AGENTS, and no empty one between them', async ({
    page,
  }) => {
    await mockRun(page, frameLess());
    await openDiagram(page);

    await expect(page.locator('.wf-flow-head-node')).toHaveText(['RUN', 'AGENTS']);
    await expect(page.getByTestId('wf-diagram-node-build')).toHaveAttribute('data-rank', '1');
    await expect(page.locator('[data-id="root->build"]')).toHaveCount(1);
    expect(await overlappingCards(page)).toEqual([]);
  });

  test('puts its deterministic rows on the root card rather than nowhere', async ({ page }) => {
    await mockRun(page, frameLess());
    await openDiagram(page);

    const strip = page.getByTestId('wf-diagram-guardrail-root');
    await expect(strip).toBeVisible();
    for (const stepId of ['sync', 'verify', 'commit-guard']) {
      await expect(page.getByTestId(`wf-diagram-guardrail-root-${stepId}`)).toBeVisible();
      await expect(page.getByTestId(`wf-diagram-node-${stepId}`)).toHaveCount(0);
    }
  });

  test('states the plan size on the root rather than two absences', async ({ page }) => {
    await mockRun(page, frameLess());
    await openDiagram(page);

    await expect(page.getByTestId('wf-diagram-node-root')).toContainText('4 steps');
    await expect(page.getByTestId('wf-diagram-node-root')).not.toContainText('0 epics');
  });
});
