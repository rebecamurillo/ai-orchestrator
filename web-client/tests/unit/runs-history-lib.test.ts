/**
 * The pure reads behind the HISTORY section (7.5, SPEC CAP-5, FR-25 history, UX-DR14):
 * the ten column heads, each cell's text, the row link, the query and the request path, the
 * promotion of currently-executing rows, and the `$poll` cadence question.
 *
 * `lib/**` is gated at 90 % lines (`vitest.config.ts`), so every branch of every helper here
 * is exercised — including the ones that answer the em dash, which is what a non-agent
 * attempt's whole right-hand side reads as.
 */
import { describe, expect, it } from 'vitest';

import {
  costText,
  durationText,
  EMPTY_CELL,
  harnessText,
  HISTORY_COLUMNS,
  HISTORY_STATUS_TOKENS,
  historyQuery,
  historyRequestPath,
  isCurrent,
  promoted,
  rowHref,
  startedText,
  workflowText,
  type HistoryRowOut,
} from '../../src/lib/runs/history';

const RUN_ID = '11111111-1111-1111-1111-111111111111';

function row(overrides: Partial<HistoryRowOut> = {}): HistoryRowOut {
  return {
    attempt_id: '22222222-2222-2222-2222-222222222222',
    run_id: RUN_ID,
    seq: 7,
    started_at: '2026-09-09T08:04:05Z',
    ended_at: '2026-09-09T08:06:35Z',
    seconds: 150.4,
    project_name: 'acme',
    run_label: 'story v3 · feat/epic-7',
    path: 'epics[0].stories[3].build',
    kind: 'agent',
    harness: 'codex',
    model: 'gpt-5-codex',
    session_id: 'sess-1',
    status: 'done',
    token: 'DON',
    tokens_in: 100,
    tokens_out: 20,
    cost_usd: '0.250000',
    cost_provisional: false,
    trace_url: 'https://langfuse.test/t/1',
    log_tail_url: `/api/v1/runs/${RUN_ID}/detail`,
    ...overrides,
  };
}

describe('the columns', () => {
  it('are UX-DR14’s ten, in its order, with time named twice', () => {
    expect([...HISTORY_COLUMNS]).toEqual([
      'time',
      'project',
      'workflow',
      'path',
      'kind',
      'harness',
      'status',
      'time',
      'cost',
      'trace',
    ]);
  });

  it('offers exactly the bar’s five filterable status tokens', () => {
    expect([...HISTORY_STATUS_TOKENS]).toEqual(['QUE', 'RUN', 'BLK', 'ERR', 'DON']);
  });
});

describe('the cells', () => {
  it('reads the clock off the UTC payload without a timezone of its own', () => {
    expect(startedText(row())).toBe('08:04:05');
  });

  it('states the duration in whole seconds', () => {
    expect(durationText(row())).toBe('150s');
  });

  it('states an em dash while the attempt is still running', () => {
    expect(durationText(row({ seconds: null, ended_at: null }))).toBe(EMPTY_CELL);
  });

  it('prints the harness and the model it ran', () => {
    expect(harnessText(row())).toBe('codex · gpt-5-codex');
  });

  it('prints the harness alone when no model was recorded', () => {
    expect(harnessText(row({ model: null }))).toBe('codex');
  });

  it('prints an em dash on a non-agent row', () => {
    expect(harnessText(row({ harness: null, model: null, kind: 'git.commit' }))).toBe(EMPTY_CELL);
  });

  it('prints the cost as the decimal string the endpoint sent', () => {
    expect(costText(row())).toBe('$0.250000');
  });

  it('says provisional while the figure is the harness’s own estimate', () => {
    expect(costText(row({ cost_provisional: true }))).toBe('$0.250000 provisional');
  });

  it('prints a locally served attempt’s zero as a cost, not as an absence', () => {
    expect(costText(row({ cost_usd: '0.000000', harness: 'local' }))).toBe('$0.000000');
  });

  it('prints an em dash where no cost was recorded at all', () => {
    expect(costText(row({ cost_usd: null }))).toBe(EMPTY_CELL);
  });

  it('prints the workflow label verbatim', () => {
    expect(workflowText(row())).toBe('story v3 · feat/epic-7');
  });
});

describe('the row link', () => {
  it('is the Run detail, at the fragment naming this row’s seq', () => {
    expect(rowHref(row())).toBe(`/workflows/${RUN_ID}#step-7`);
  });
});

describe('the request', () => {
  it('omits a missing project and the ALL token', () => {
    expect(historyQuery(null, 'ALL', null)).toEqual({});
    expect(historyRequestPath(null, 'ALL')).toBe('/api/steps');
  });

  it('carries the project, the status token and the cursor when there are ones', () => {
    expect(historyQuery('p-1', 'BLK', 'cur')).toEqual({
      project_id: 'p-1',
      status: 'BLK',
      cursor: 'cur',
    });
  });

  it('names the request a failed fetch was, filters and all', () => {
    expect(historyRequestPath('p-1', 'BLK')).toBe('/api/steps?project_id=p-1&status=BLK');
  });

  it('escapes a value rather than pasting it into the path', () => {
    expect(historyRequestPath('a b', null)).toBe('/api/steps?project_id=a%20b');
  });
});

describe('the promotion', () => {
  it('reads the current flag off the status the endpoint sent', () => {
    expect(isCurrent(row({ status: 'running' }))).toBe(true);
    expect(isCurrent(row())).toBe(false);
  });

  it('promotes the executing rows above the rest and keeps every other order', () => {
    const a = row({ attempt_id: 'a' });
    const b = row({ attempt_id: 'b', status: 'running' });
    const c = row({ attempt_id: 'c' });

    expect(promoted([a, b, c]).map((each) => each.attempt_id)).toEqual(['b', 'a', 'c']);
  });
});
