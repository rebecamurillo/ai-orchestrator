/**
 * The Answer box (6.1, FR-18, UX-DR10, UX-DR17): where it appears, and what it says.
 *
 * `vitest.config.ts` runs in `environment: 'node'` with no DOM-mounting library (see
 * `run-detail-island.test.ts`'s own note), so what is asserted here is the rendered markup
 * and the pure functions behind it: the hint verbatim with the file the resumed attempt will
 * actually archive, the button disabled while nothing has been typed, and the two stops that
 * must *not* offer the box. Typing, clicking and the 409 are the browser's own facts and are
 * asserted in `tests/e2e/run-detail-answer.spec.ts`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import AnswerBox from '../../src/components/run/AnswerBox';
import StopBody from '../../src/components/run/StopBody';
import {
  ANSWER_HINT_WITHOUT_STORY,
  ANSWER_LABEL,
  SESSION_ANSWER_HINT,
  answerBody,
  answerHint,
  answerTarget,
  offersAnswer,
} from '../../src/lib/run/answer';
import type { RunDetailOut } from '../../src/lib/run/detail';

const STORY_ID = '4-1';
const BUILD = 'epics[0].stories[0].build';

/** The line UX-DR17 pins, written out in full so a reworded one fails here. */
const HINT =
  'Blocked story file archived to stories/.answers/4-1-attempt-1.md with your answer; ' +
  'story 4-1 re-planned with the answer as context. ' +
  'If the gap is in SPEC.md, edit SPEC.md on the branch instead.';

function base(): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'needs_you',
      admitted_signals: [],
      branch: 'epics/1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '0',
      template: 'epic',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'specs/gates',
        template: 'epic',
        version: 1,
        harness: 'claude',
        started_at: null,
        worktree_path: null,
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '0',
      budget_usd: '15',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [],
    admitted_signals: [],
    summary: null,
  };
}

function blocked(overrides: Partial<RunDetailOut> = {}): RunDetailOut {
  return {
    ...base(),
    alert: {
      token: 'BLK',
      reason: '## Auto Run Result\n\nWhich channel should this post to?',
      park_kind: 'blocked',
      attribution: { harness: 'claude', model: 'claude-opus-4', ended_at: null },
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
        latest: {
          n: 1,
          started_at: null,
          ended_at: null,
          seconds: null,
          harness: 'claude',
          model: 'claude-opus-4',
          exit_code: 0,
          cost_usd: null,
          log_tail: [],
        },
      },
    ],
    stories: [
      { epic_index: 1, story_id: '4-0', state: 'done', cost_usd: '1.00' },
      { epic_index: 1, story_id: STORY_ID, state: 'current', cost_usd: '2.00' },
    ],
    admitted_signals: ['answer', 'skip_story', 'skip_epic', 'cancel'],
    ...overrides,
  };
}

function render(detail: RunDetailOut, token: Parameters<typeof StopBody>[0]['token']): string {
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail,
      token,
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: null,
      onAnswer: () => {},
    }),
  );
}

describe('the Answer box on a blocked stop', () => {
  it('renders the textarea, the hint and the primary button under the question', () => {
    const html = render(blocked(), 'BLK');

    expect(html).toContain('data-testid="wf-question"');
    expect(html).toContain('data-testid="wf-answer"');
    expect(html).toContain('data-testid="wf-signal-answer"');
    expect(html).toContain(ANSWER_LABEL);
    expect(html.indexOf('wf-question')).toBeLessThan(html.indexOf('wf-answer'));
  });

  it('states the file the resumed attempt will archive, verbatim (UX-DR17, NFR-8)', () => {
    const html = render(blocked(), 'BLK');

    expect(html).toContain(HINT);
  });

  it('names the attempt that blocked, not the one about to run', () => {
    const detail = blocked();
    detail.steps[0].latest = { ...detail.steps[0].latest!, n: 3 };

    expect(answerHint(answerTarget(detail))).toContain('4-1-attempt-3.md');
  });

  it('disables the button until something has been typed', () => {
    const html = render(blocked(), 'BLK');

    expect(html).toMatch(/data-testid="wf-signal-answer"[^>]*disabled/);
  });

  it('disables it while any signal is in flight', () => {
    const html = renderToStaticMarkup(
      createElement(AnswerBox, {
        target: { storyId: STORY_ID, attempt: 1 },
        onAnswer: () => {},
        posting: true,
        error: null,
      }),
    );

    expect(html).toMatch(/data-testid="wf-signal-answer"[^>]*disabled/);
  });

  it('prints a refusal beside the button rather than replacing the box', () => {
    const html = renderToStaticMarkup(
      createElement(AnswerBox, {
        target: { storyId: STORY_ID, attempt: 1 },
        onAnswer: () => {},
        posting: false,
        error: {
          status: 409,
          title: 'conflict',
          type: 'about:blank',
          detail: 'signal answer invalid for status running / park null',
        },
      }),
    );

    expect(html).toContain('data-testid="wf-answer-error"');
    expect(html).toContain('signal answer invalid for status running');
    expect(html).toContain('data-testid="wf-answer"');
  });

  it('keeps its own skip and cancel buttons beside it', () => {
    const html = render(blocked(), 'BLK');

    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-signal-skip_epic"');
    expect(html).toContain('data-testid="wf-cancel"');
  });
});

describe('where the Answer box does not appear', () => {
  it('is absent when the Run does not admit an answer', () => {
    const html = render(blocked({ admitted_signals: ['skip_story', 'cancel'] }), 'BLK');

    expect(html).not.toContain('data-testid="wf-signal-answer"');
    expect(html).not.toContain('<textarea');
  });

  it('is absent on a misconfigured stop, which admits no answer at all', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: { token: 'BLK', reason: 'no story file', park_kind: 'misconfigured' },
      admitted_signals: ['retry', 'skip_story', 'skip_epic', 'cancel'],
    };

    const html = render(detail, 'BLK');

    expect(html).toContain('data-testid="wf-stop-misconfigured"');
    expect(html).not.toContain('<textarea');
  });

  it('is absent at a checkpoint — 6.2 is the story that gives that stop its own controls', () => {
    const detail: RunDetailOut = {
      ...base(),
      alert: { token: 'CHK', reason: 'spec checkpoint', park_kind: 'checkpoint' },
      admitted_signals: ['answer', 'continue', 'cancel'],
    };

    const html = render(detail, 'CHK');

    expect(html).not.toContain('<textarea');
  });
});

describe('what the box knows', () => {
  it('reads the Story off the strip and the attempt off the parked row', () => {
    expect(answerTarget(blocked())).toEqual({ storyId: STORY_ID, attempt: 1 });
  });

  it('falls back to the row attempt count when no attempt has been recorded', () => {
    const detail = blocked();
    detail.steps[0].latest = null;

    expect(answerTarget(detail).attempt).toBe(1);
  });

  it('reads the row the gate record names when the response carries one', () => {
    const detail = blocked({
      gate_record: [
        {
          id: 'g1',
          at: '2026-09-07T09:12:00Z',
          path: BUILD,
          event: 'blocked',
          actor: 'machine',
          text: '## Auto Run Result',
          attempt_n: 2,
        },
      ],
    });
    detail.steps[0].latest = { ...detail.steps[0].latest!, n: 2 };

    expect(answerTarget(detail).attempt).toBe(2);
  });

  it('names attempt 1 when the Run stopped with no rows at all', () => {
    expect(answerTarget(blocked({ steps: [] })).attempt).toBe(1);
  });

  it('states the mechanism without inventing a path when no Story is named', () => {
    const detail = blocked({ stories: [] });

    expect(answerHint(answerTarget(detail))).toBe(ANSWER_HINT_WITHOUT_STORY);
    expect(render(detail, 'BLK')).toContain(ANSWER_HINT_WITHOUT_STORY);
  });

  it('posts the Operator text with mode in payload (story 3-4: mode defaults to restart)', () => {
    expect(answerBody('post it to the channel')).toEqual({
      kind: 'answer',
      payload: { text: 'post it to the channel', mode: 'restart' },
    });
  });

  it('offers the box only for a blocked stop that admits the signal', () => {
    expect(offersAnswer(blocked(), 'blocked')).toBe(true);
    expect(offersAnswer(blocked(), 'checkpoint')).toBe(false);
    expect(offersAnswer(blocked({ admitted_signals: [] }), 'blocked')).toBe(false);
    expect(offersAnswer(blocked(), null)).toBe(false);
  });

  it('includes mode: session in payload when session is passed (story 3-4)', () => {
    expect(answerBody('the text', 'session')).toEqual({
      kind: 'answer',
      payload: { text: 'the text', mode: 'session' },
    });
  });
});

describe('mode selector in AnswerBox (story 3-4)', () => {
  it('renders two radio inputs when replyAvailable is true', () => {
    const html = renderToStaticMarkup(
      createElement(AnswerBox, {
        target: { storyId: STORY_ID, attempt: 1 },
        onAnswer: () => {},
        posting: false,
        error: null,
        replyAvailable: true,
      }),
    );

    expect(html.match(/<input[^>]*type="radio"/g)?.length).toBe(2);
  });

  it('shows the session hint text when replyAvailable is true', () => {
    const html = renderToStaticMarkup(
      createElement(AnswerBox, {
        target: { storyId: STORY_ID, attempt: 1 },
        onAnswer: () => {},
        posting: false,
        error: null,
        replyAvailable: true,
      }),
    );

    expect(html).toContain(SESSION_ANSWER_HINT);
  });

  it('shows no radio inputs and only the restart hint when replyAvailable is false', () => {
    const html = renderToStaticMarkup(
      createElement(AnswerBox, {
        target: { storyId: STORY_ID, attempt: 1 },
        onAnswer: () => {},
        posting: false,
        error: null,
        replyAvailable: false,
      }),
    );

    expect(html).not.toContain('<input');
    expect(html).not.toContain(SESSION_ANSWER_HINT);
  });
});
