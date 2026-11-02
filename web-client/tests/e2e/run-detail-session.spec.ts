import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The Operator's senior session on the Run page (story 2-4, CAP-7): the offer, the start
 * form, the conversation, the lock, the close and the anchor review.
 *
 * `GET /api/runs/{id}/detail`, `GET /api/runs/{id}/session`, `POST /api/runs/{id}/signals`,
 * `POST /api/runs/{id}/session/messages` and the two harness reads are mocked with
 * `page.route()`, the way the other Run detail specs mock the detail: there is no engine here
 * to park a Run or run a turn, and every assertion is about what the screen does with a given
 * response. The mock keeps one small state object so a signal changes what the next poll
 * reads, as the server would.
 */

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939d9';
const URL = `/workflows/${RUN_ID}`;
const BUILD = 'epics[0].stories[0].build';

const STOP_ADMITTED = ['answer', 'skip_story', 'skip_epic', 'cancel'];
const LOCKED_ADMITTED = ['cancel', 'session_end'];

interface Turn {
  attempt_id: string;
  turn: number;
  status: string;
  message: string;
  reply: string;
  started_at: string | null;
  ended_at: string | null;
  exit_code: number | null;
  cost_usd: string | null;
}

interface Server {
  active: boolean;
  available: boolean;
  turnRunning: boolean;
  turns: Turn[];
  edits: { kind: string; path: string }[];
  /** Every signal body posted, in order. */
  signals: Record<string, unknown>[];
  messages: Record<string, unknown>[];
  startRefusal: { status: number; detail: string } | null;
  messageRefusal: { status: number; detail: string } | null;
  probe: { ok: boolean; models: string[]; version: string; failing_reason: string | null };
  /** The number of the stop the Run is at; a stale signal moves it, as another tab would. */
  parkSeq: number;
  scopes: string[];
}

function newServer(over: Partial<Server> = {}): Server {
  return {
    active: false,
    available: true,
    turnRunning: false,
    turns: [],
    edits: [],
    signals: [],
    messages: [],
    parkSeq: 4,
    scopes: ['story', 'epic', 'run'],
    startRefusal: null,
    messageRefusal: null,
    probe: {
      ok: true,
      models: ['claude-opus-4', 'claude-sonnet-4'],
      version: '2.1',
      failing_reason: null,
    },
    ...over,
  };
}

function run(server: Server): Record<string, unknown> {
  return {
    id: RUN_ID,
    status: 'needs_you',
    branch: 'epics/1',
    budget_usd: '40.00',
    compare_urls: [],
    created_at: '2026-11-02T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: null,
    project: '11111111-1111-1111-1111-111111111111',
    repository: '22222222-2222-2222-2222-222222222222',
    spend_usd: '12.30',
    template: 'epic',
    terminal_session: false,
    version: 1,
    worktree_path: '/work/orchestrator',
    worktrees: [],
    accepted_paths: [],
    park_seq: server.parkSeq,
    ...(server.active ? { senior_session: true } : {}),
  };
}

function detail(server: Server): Record<string, unknown> {
  const admitted = server.active ? LOCKED_ADMITTED : STOP_ADMITTED;
  return {
    header: {
      meta: {
        project: 'Mixed Signals',
        repository: 'orchestrator',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: '2026-11-02T09:00:05Z',
        worktree_path: '/work/orchestrator',
      },
    },
    alert: {
      token: 'BLK',
      reason: '## Auto Run Result\n\nWhich channel should the notification post to?',
      park_kind: 'blocked',
      attribution: { harness: 'claude', model: 'claude-opus-4', ended_at: '2026-11-02T09:12:00Z' },
    },
    steps: [
      {
        seq: 1,
        path: BUILD,
        label: 'build',
        kind: 'agent',
        gate: 'liveness',
        status: 'blocked',
        token: 'BLK',
        reason: null,
        attempts: 1,
        latest: null,
      },
    ],
    stories: [{ epic_index: 1, story_id: '2-4', state: 'current', cost_usd: '3.20' }],
    cost: {
      spent_usd: '12.30',
      budget_usd: '40.00',
      tokens_in: 15000,
      tokens_out: 4200,
      wall_clock_seconds: 930,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: admitted,
    summary: null,
    run: { ...run(server), admitted_signals: admitted },
  };
}

function sessionRead(server: Server): Record<string, unknown> {
  return {
    active: server.active,
    available: server.available && !server.active,
    scopes: server.scopes,
    scope: server.active ? 'story' : null,
    harness: server.active ? 'claude' : null,
    model: server.active ? 'claude-opus-4' : null,
    anchor_edits: server.active ? server.edits : [],
    turn_running: server.turnRunning,
    turns: server.turns,
  };
}

function problem(status: number, detailText: string): Record<string, unknown> {
  return { type: 'about:blank', title: 'refused', status, detail: detailText };
}

function json(route: Route, status: number, body: unknown): Promise<void> {
  return route.fulfill({
    status,
    contentType: status >= 400 ? 'application/problem+json' : 'application/json',
    body: JSON.stringify(body),
  });
}

async function serve(page: Page, server: Server): Promise<void> {
  await page.route(`**/api/runs/${RUN_ID}/detail**`, (route) => json(route, 200, detail(server)));
  await page.route(`**/api/runs/${RUN_ID}/session`, (route) =>
    json(route, 200, sessionRead(server)),
  );
  await page.route('**/api/harnesses', (route) =>
    json(route, 200, {
      items: [
        {
          name: 'claude',
          enabled: true,
          version_pin: '2.1',
          failing_check: null,
          last_readiness_at: null,
        },
        {
          name: 'codex',
          enabled: false,
          version_pin: '0.4',
          failing_check: 'login',
          last_readiness_at: null,
        },
      ],
      next_cursor: null,
    }),
  );
  await page.route('**/api/harnesses/*/probe', (route) => json(route, 200, server.probe));
  await page.route(`**/api/runs/${RUN_ID}/session/messages`, (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    server.messages.push(body);
    if (server.messageRefusal) {
      return json(
        route,
        server.messageRefusal.status,
        problem(server.messageRefusal.status, server.messageRefusal.detail),
      );
    }
    const turn: Turn = {
      attempt_id: `att-${server.turns.length + 1}`,
      turn: server.turns.length + 1,
      status: 'queued',
      message: String(body.text),
      reply: '',
      started_at: '2026-11-02T10:00:00Z',
      ended_at: null,
      exit_code: null,
      cost_usd: null,
    };
    server.turns.push(turn);
    server.turnRunning = true;
    return json(route, 202, turn);
  });
  await page.route(`**/api/runs/${RUN_ID}/signals`, (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    server.signals.push(body);
    if (body.kind === 'cancel') {
      // the Run has moved to a new stop since this page read it
      server.parkSeq += 1;
      server.scopes = ['run'];
      return json(route, 409, problem(409, `stale stop: the Run is at stop ${server.parkSeq}`));
    }
    if (body.kind === 'session_start') {
      if (server.startRefusal) {
        return json(
          route,
          server.startRefusal.status,
          problem(server.startRefusal.status, server.startRefusal.detail),
        );
      }
      server.active = true;
    } else if (body.kind === 'session_end') {
      const confirmed = ((body.payload as Record<string, unknown> | undefined)?.confirmed_paths ??
        []) as string[];
      const missing = server.edits.filter((edit) => !confirmed.includes(edit.path));
      if (missing.length > 0) {
        return json(
          route,
          409,
          problem(
            409,
            `anchor edits neither confirmed nor reverted: ${missing.map((m) => m.path).join(', ')}`,
          ),
        );
      }
      server.active = false;
    }
    return json(route, 202, { status: 'needs_you' });
  });
}

async function open(page: Page, server: Server): Promise<void> {
  await serve(page, server);
  await page.goto(URL);
  await expect(page.getByTestId('wf-header')).toBeVisible();
}

function finishedTurn(over: Partial<Turn> = {}): Turn {
  return {
    attempt_id: 'att-1',
    turn: 1,
    status: 'done',
    message: 'why does the test fail?',
    reply: 'it asserts the old mapping',
    started_at: '2026-11-02T10:00:00Z',
    ended_at: '2026-11-02T10:01:00Z',
    exit_code: 0,
    cost_usd: '0.40',
    ...over,
  };
}

test.describe('the senior session offer and start', () => {
  test('offers the session at a stop and starts it with the chosen scope, harness and model', async ({
    page,
  }) => {
    const server = newServer();
    await open(page, server);

    await expect(page.getByTestId('wf-answer')).toBeVisible();
    await page.getByTestId('wf-session-offer').click();

    await expect(page.getByTestId('wf-session-scope')).toHaveValue('story');
    await expect(page.getByTestId('wf-session-start')).toBeDisabled();
    // only the enabled harness is offered
    await expect(page.getByTestId('wf-session-harness').locator('option')).toHaveText([
      '—',
      'claude',
    ]);

    await page.getByTestId('wf-session-scope').selectOption('epic');
    await page.getByTestId('wf-session-harness').selectOption('claude');
    const model = page.getByTestId('wf-session-model');
    await expect(model.locator('option')).toHaveText([
      'harness default',
      'claude-opus-4',
      'claude-sonnet-4',
    ]);
    await model.selectOption('claude-sonnet-4');
    await page.getByTestId('wf-session-start').click();

    await expect(page.getByTestId('wf-session')).toBeVisible();
    expect(server.signals).toEqual([
      {
        kind: 'session_start',
        payload: { scope: 'epic', harness: 'claude', model: 'claude-sonnet-4' },
      },
    ]);
  });

  test('offers nothing where the server says no session can start', async ({ page }) => {
    await open(page, newServer({ available: false }));

    await expect(page.getByTestId('wf-answer')).toBeVisible();
    await expect(page.getByTestId('wf-session-offer')).toHaveCount(0);
  });

  test('keeps Start off and prints the reason when the harness probe fails', async ({ page }) => {
    const server = newServer({
      probe: { ok: false, models: [], version: '', failing_reason: 'claude is not logged in' },
    });
    await open(page, server);

    await page.getByTestId('wf-session-offer').click();
    await page.getByTestId('wf-session-harness').selectOption('claude');

    await expect(page.getByTestId('wf-session-probe-error')).toHaveText('claude is not logged in');
    await expect(page.getByTestId('wf-session-start')).toBeDisabled();
    await expect(page.getByTestId('wf-session-model')).toHaveCount(0);
  });

  test('shows a refused start verbatim and keeps the form', async ({ page }) => {
    const server = newServer({
      startRefusal: { status: 422, detail: 'skill senior-session is not installed' },
    });
    await open(page, server);

    await page.getByTestId('wf-session-offer').click();
    await page.getByTestId('wf-session-harness').selectOption('claude');
    await page.getByTestId('wf-session-start').click();

    await expect(page.getByTestId('wf-signal-error').first()).toHaveText(
      'skill senior-session is not installed',
    );
    await expect(page.getByTestId('wf-session-form')).toBeVisible();
  });
});

test.describe('an open session', () => {
  test('hides the stop’s controls, keeps Cancel, and shows the conversation', async ({ page }) => {
    await open(page, newServer({ active: true, turns: [finishedTurn()] }));

    await expect(page.getByTestId('wf-session-lock')).toContainText('senior session open');
    await expect(page.getByTestId('wf-cancel')).toBeVisible();
    await expect(page.getByTestId('wf-answer')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-answer')).toHaveCount(0);
    await expect(page.getByTestId('wf-signal-skip_story')).toHaveCount(0);
    await expect(page.getByTestId('wf-session-turn-1')).toContainText('why does the test fail?');
    await expect(page.getByTestId('wf-session-turn-1')).toContainText('it asserts the old mapping');
    await expect(page.getByTestId('wf-session-offer')).toHaveCount(0);
  });

  test('disables the box while a turn runs and re-enables it when the poll sees it end', async ({
    page,
  }) => {
    const server = newServer({
      active: true,
      turnRunning: true,
      turns: [finishedTurn({ status: 'running', reply: '', ended_at: null, exit_code: null })],
    });
    await open(page, server);

    await expect(page.getByTestId('wf-session-message')).toBeDisabled();
    await expect(page.getByTestId('wf-session-send')).toBeDisabled();
    await expect(page.getByTestId('wf-session-running')).toContainText('turn 1 is running');

    server.turnRunning = false;
    server.turns = [finishedTurn()];

    await expect(page.getByTestId('wf-session-message')).toBeEnabled({ timeout: 15_000 });
    await expect(page.getByTestId('wf-session-running')).toHaveCount(0);
  });

  test('sends a message, clears the draft and disables the box for the queued turn', async ({
    page,
  }) => {
    const server = newServer({ active: true });
    await open(page, server);

    await page.getByTestId('wf-session-message').fill('  look at the failing test  ');
    await page.getByTestId('wf-session-send').click();

    await expect(page.getByTestId('wf-session-turn-1')).toContainText('look at the failing test');
    await expect(page.getByTestId('wf-session-message')).toHaveValue('');
    await expect(page.getByTestId('wf-session-message')).toBeDisabled();
    expect(server.messages).toEqual([{ text: 'look at the failing test' }]);
  });

  test('shows a refused message verbatim and keeps the draft', async ({ page }) => {
    const server = newServer({
      active: true,
      messageRefusal: { status: 409, detail: 'no remaining budget' },
    });
    await open(page, server);

    await page.getByTestId('wf-session-message').fill('go on');
    await page.getByTestId('wf-session-send').click();

    await expect(page.getByTestId('wf-signal-error')).toHaveText('no remaining budget');
    await expect(page.getByTestId('wf-session-message')).toHaveValue('go on');
  });

  test('says no reply file and links the log when a finished turn left none', async ({ page }) => {
    await open(page, newServer({ active: true, turns: [finishedTurn({ reply: '' })] }));

    const turn = page.getByTestId('wf-session-turn-1');
    await expect(turn).toContainText('no reply file');
    await expect(turn.getByRole('link', { name: 'log' })).toHaveAttribute(
      'href',
      `/api/runs/${RUN_ID}/attempts/att-1/log`,
    );
  });
});

test.describe('closing the session', () => {
  test('closes with no anchor edit and the stop’s controls return', async ({ page }) => {
    const server = newServer({ active: true, turns: [finishedTurn()] });
    await open(page, server);

    await page.getByTestId('wf-session-close').click();

    await expect(page.getByTestId('wf-answer')).toBeVisible();
    await expect(page.getByTestId('wf-session-offer')).toBeVisible();
    await expect(page.getByTestId('wf-session')).toHaveCount(0);
    expect(server.signals).toEqual([{ kind: 'session_end' }]);
  });

  test('lists each unconfirmed anchor edit, and closes with the confirmed paths', async ({
    page,
  }) => {
    const server = newServer({
      active: true,
      turns: [finishedTurn()],
      edits: [
        { kind: 'modified', path: 'stories.yaml' },
        { kind: 'added', path: 'repos/m/AGENTS.md' },
      ],
    });
    await open(page, server);

    await page.getByTestId('wf-session-close').click();

    await expect(page.getByTestId('wf-signal-error')).toHaveText(
      'anchor edits neither confirmed nor reverted: stories.yaml, repos/m/AGENTS.md',
    );
    await expect(page.getByTestId('wf-session-anchors')).toContainText('stories.yaml');
    await expect(page.getByTestId('wf-session-anchors')).toContainText('repos/m/AGENTS.md');
    await expect(page.getByTestId('wf-session-close-confirmed')).toBeDisabled();

    await page.getByTestId('wf-session-confirm-stories.yaml').click();
    await expect(page.getByTestId('wf-session-close-confirmed')).toBeDisabled();
    await page.getByTestId('wf-session-confirm-repos/m/AGENTS.md').click();
    await page.getByTestId('wf-session-close-confirmed').click();

    await expect(page.getByTestId('wf-answer')).toBeVisible();
    expect(server.signals.at(-1)).toEqual({
      kind: 'session_end',
      payload: { confirmed_paths: ['stories.yaml', 'repos/m/AGENTS.md'] },
    });
  });

  test('a revert is a message to the senior, and the file leaves the list when it is restored', async ({
    page,
  }) => {
    const server = newServer({
      active: true,
      turns: [finishedTurn()],
      edits: [{ kind: 'modified', path: 'stories.yaml' }],
    });
    await open(page, server);

    await page.getByTestId('wf-session-close').click();
    await page.getByTestId('wf-session-confirm-stories.yaml').click();
    await page.getByTestId('wf-session-revert-stories.yaml').click();

    await expect(page.getByTestId('wf-session-turn-2')).toContainText('Revert stories.yaml');
    expect(server.messages).toEqual([
      {
        text: 'Revert stories.yaml to its state before this session, then say when it is restored.',
      },
    ]);
    // the revert turn runs: confirm and revert wait for it
    await expect(page.getByTestId('wf-session-revert-stories.yaml')).toBeDisabled();

    server.turnRunning = false;
    server.turns[1] = {
      ...server.turns[1]!,
      status: 'done',
      reply: 'restored',
      ended_at: '2026-11-02T10:05:00Z',
    };
    server.edits = [];

    await expect(page.getByTestId('wf-session-anchors')).toContainText('no anchor edit remains', {
      timeout: 15_000,
    });
    await page.getByTestId('wf-session-close-confirmed').click();
    await expect(page.getByTestId('wf-answer')).toBeVisible();
    expect(server.signals.at(-1)).toEqual({ kind: 'session_end' });
  });

  test('keeps Cancel run available throughout', async ({ page }) => {
    await open(
      page,
      newServer({
        active: true,
        turnRunning: true,
        turns: [finishedTurn({ ended_at: null, status: 'running' })],
      }),
    );

    await expect(page.getByTestId('wf-cancel')).toBeEnabled();
    await expect(page.getByTestId('wf-session-close')).toBeDisabled();
  });
});

test.describe('a new stop', () => {
  async function moveToNewStop(page: Page): Promise<void> {
    await page.getByTestId('wf-cancel').click();
    await page.getByTestId('wf-cancel-confirm-yes').click();
    await expect(page.getByTestId('wf-signal-error').first()).toContainText('stale stop');
    await page.getByTestId('wf-cancel-confirm-no').click();
  }

  test('starts the form clean: no kept scope, harness or probe from the last stop', async ({
    page,
  }) => {
    const server = newServer();
    await open(page, server);

    await page.getByTestId('wf-session-offer').click();
    await page.getByTestId('wf-session-scope').selectOption('epic');
    await page.getByTestId('wf-session-harness').selectOption('claude');
    await expect(page.getByTestId('wf-session-model')).toBeVisible();

    await moveToNewStop(page);

    await expect(page.getByTestId('wf-session-form')).toHaveCount(0);
    await page.getByTestId('wf-session-offer').click();
    // the new stop offers only the Run scope, and nothing carries over from the old form
    await expect(page.getByTestId('wf-session-scope')).toHaveValue('run');
    await expect(page.getByTestId('wf-session-scope').locator('option')).toHaveText(['Run']);
    await expect(page.getByTestId('wf-session-harness')).toHaveValue('');
    await expect(page.getByTestId('wf-session-model')).toHaveCount(0);
  });

  test('does not carry an unsent message into the next stop', async ({ page }) => {
    const server = newServer({ active: true, turns: [finishedTurn()] });
    await open(page, server);

    await page.getByTestId('wf-session-message').fill('half a thought');
    await moveToNewStop(page);

    await expect(page.getByTestId('wf-session-message')).toHaveValue('');
  });
});

test.describe('accessible names and focus', () => {
  test('names each row’s buttons by file and keeps Confirm’s word fixed', async ({ page }) => {
    const server = newServer({
      active: true,
      turns: [finishedTurn()],
      edits: [
        { kind: 'modified', path: 'stories.yaml' },
        { kind: 'added', path: 'SPEC.md' },
      ],
    });
    await open(page, server);

    await page.getByTestId('wf-session-close').click();

    const confirm = page.getByRole('button', { name: 'Confirm stories.yaml' });
    await expect(confirm).toHaveText('Confirm');
    await expect(confirm).toHaveAttribute('aria-pressed', 'false');
    await confirm.click();
    await expect(confirm).toHaveText('Confirm');
    await expect(confirm).toHaveAttribute('aria-pressed', 'true');
    await expect(page.getByRole('button', { name: 'Revert SPEC.md' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirm SPEC.md' })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  test('moves focus to the control that replaces the one that unmounted', async ({ page }) => {
    const server = newServer({ edits: [{ kind: 'modified', path: 'stories.yaml' }] });
    await open(page, server);

    await page.getByTestId('wf-session-offer').click();
    await expect(page.getByTestId('wf-session-scope')).toBeFocused();
    await page.getByTestId('wf-session-dismiss').click();
    await expect(page.getByTestId('wf-session-offer')).toBeFocused();

    await page.getByTestId('wf-session-offer').click();
    await page.getByTestId('wf-session-harness').selectOption('claude');
    await page.getByTestId('wf-session-start').click();
    await expect(page.getByTestId('wf-session-message')).toBeFocused();

    await page.getByTestId('wf-session-close').click();
    await expect(page.getByTestId('wf-session-anchors')).toBeFocused();
    await page.getByRole('button', { name: 'Confirm stories.yaml' }).click();
    await page.getByTestId('wf-session-close-confirmed').click();
    await expect(page.getByTestId('wf-session-offer')).toBeFocused();
  });
});
