/**
 * Continue and Reject at checkpoints (6.2, FR-19, UX-DR10): the spec-checkpoint body (the
 * planned story file inline, the eyebrow, the Reject box) and the done-checkpoint body (the
 * summary line), split out of the frozen `run-stop-body.test.ts` `StopBody · checkpoint`
 * case the same way 6.1 split `-answer` out of it — that case stays exactly as it was
 * (no `alert.row_kind`, generic banner + Continue only) and is not touched here.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RejectBox from '../../src/components/run/RejectBox';
import StopBody from '../../src/components/run/StopBody';
import StoryFileBlock from '../../src/components/run/StoryFileBlock';
import {
  checkpointSummaryLine,
  REJECT_TOGGLE_LABEL,
  rejectHint,
} from '../../src/lib/run/checkpoint';
import type { RunDetailOut } from '../../src/lib/run/detail';

const STORY_ID = '2';
const BUILD = 'stories[0].build';

function base(): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'needs_you',
      admitted_signals: [],
      branch: 'epics/gates',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-09T09:00:00Z',
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

function specCheckpoint(overrides: Partial<RunDetailOut> = {}): RunDetailOut {
  return {
    ...base(),
    alert: {
      token: 'CHK',
      reason: 'spec checkpoint',
      park_kind: 'checkpoint',
      row_kind: 'agent',
      attribution: { harness: 'claude', model: 'claude-opus-4', ended_at: '2026-09-09T09:05:00Z' },
    },
    steps: [
      {
        seq: 1,
        path: BUILD,
        label: 'build',
        kind: 'agent',
        gate: 'liveness',
        status: 'checkpoint',
        token: 'CHK',
        reason: null,
        attempts: 1,
        latest: null,
      },
    ],
    stories: [{ epic_index: 1, story_id: STORY_ID, state: 'current', cost_usd: '0.01' }],
    admitted_signals: ['answer', 'continue', 'skip_story', 'skip_epic', 'cancel'],
    ...overrides,
  };
}

function doneCheckpoint(overrides: Partial<RunDetailOut> = {}): RunDetailOut {
  return {
    ...base(),
    alert: {
      token: 'CHK',
      reason: 'story checkpoint',
      park_kind: 'checkpoint',
      row_kind: 'checkpoint',
      checkpoint_story: {
        story_id: STORY_ID,
        title: 'Record the plan',
        attempts: 1,
        cost_usd: '0.01',
        verify: 'done',
      },
    },
    admitted_signals: ['continue', 'skip_story', 'skip_epic', 'cancel'],
    ...overrides,
  };
}

function render(detail: RunDetailOut, props: Partial<Parameters<typeof StopBody>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail,
      token: 'CHK',
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: null,
      onAnswer: () => {},
      ...props,
    }),
  );
}

describe('the spec-checkpoint body', () => {
  it('renders the planned file inline with its eyebrow, once the island has fetched it', () => {
    const html = render(specCheckpoint(), {
      plannedFile: {
        path: 'specs/gates/stories/2-plan.md',
        content: '# Story 2\n',
        size: 10,
        mtime: 0,
      },
    });

    expect(html).toContain('data-testid="wf-planned-file"');
    expect(html).toContain('data-testid="wf-planned-file-eyebrow"');
    expect(html).toContain('planned by claude · claude-opus-4 · 2026-09-09T09:05:00Z');
    expect(html).toContain('Story 2');
  });

  it('shows nothing for the planned file until the island has fetched it', () => {
    const html = render(specCheckpoint());

    expect(html).not.toContain('data-testid="wf-planned-file"');
  });

  it('offers Continue as a primary signal button, matching admitted_signals', () => {
    const html = render(specCheckpoint());

    expect(html).toContain('data-testid="wf-signal-continue"');
    expect(html).toContain('>Continue<');
  });

  it('starts collapsed behind the toggle — the textarea is a click away, not on load', () => {
    const html = render(specCheckpoint());

    expect(html).toContain(REJECT_TOGGLE_LABEL);
    expect(html).not.toContain('data-testid="wf-reject"');
    expect(html).not.toContain('<textarea');

    // `RejectBox` alone, with no click simulated (`renderToStaticMarkup` cannot): its own
    // `useState(false)` still starts closed — clicking to reveal it is proven in the
    // browser (`tests/e2e/run-detail-checkpoint.spec.ts`), the same split
    // `run-stop-body-answer.test.ts` draws for typing and submitting.
    const closed = renderToStaticMarkup(
      createElement(RejectBox, {
        target: { storyId: STORY_ID, attempt: 1 },
        onReject: () => {},
        posting: false,
        error: null,
      }),
    );
    expect(closed).toContain(REJECT_TOGGLE_LABEL);
    expect(closed).not.toContain('data-testid="wf-reject"');
  });

  it('states the reason-archive mechanism and the re-plan, verbatim (NFR-8)', () => {
    expect(rejectHint({ storyId: STORY_ID, attempt: 1 })).toBe(
      `planned story archived to stories/.answers/${STORY_ID}-attempt-1.md with your reason; ` +
        `story ${STORY_ID} re-planned`,
    );
  });

  it('is absent from Reject when the Run does not admit answer', () => {
    const html = render(specCheckpoint({ admitted_signals: ['continue', 'cancel'] }));

    expect(html).not.toContain(REJECT_TOGGLE_LABEL);
  });

  it('keeps Skip story, Skip epic and Cancel run beside it', () => {
    const html = render(specCheckpoint());

    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-signal-skip_epic"');
    expect(html).toContain('data-testid="wf-cancel"');
  });
});

describe('the done-checkpoint body', () => {
  it('shows the summary line, verbatim', () => {
    const html = render(doneCheckpoint());

    expect(html).toContain('data-testid="wf-checkpoint-summary"');
    expect(html).toContain('story 2 · Record the plan · 1 attempts · $0.01 · verify done');
  });

  it('computes the same line the library function does', () => {
    const detail = doneCheckpoint();
    const html = render(detail);

    expect(html).toContain(checkpointSummaryLine(detail.alert!.checkpoint_story!));
  });

  it('offers Continue as primary, and no Reject box at all', () => {
    const html = render(doneCheckpoint());

    expect(html).toContain('data-testid="wf-signal-continue"');
    expect(html).not.toContain(REJECT_TOGGLE_LABEL);
    expect(html).not.toContain('data-testid="wf-planned-file"');
  });

  it('keeps Skip story, Skip epic and Cancel run beside it', () => {
    const html = render(doneCheckpoint());

    expect(html).toContain('data-testid="wf-signal-skip_story"');
    expect(html).toContain('data-testid="wf-signal-skip_epic"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('renders no summary line when the response predates the field', () => {
    const detail = doneCheckpoint();
    detail.alert!.checkpoint_story = null;

    const html = render(detail);

    expect(html).not.toContain('data-testid="wf-checkpoint-summary"');
  });
});

describe('StoryFileBlock', () => {
  it('renders the eyebrow and every block the parser gives it', () => {
    const html = renderToStaticMarkup(
      createElement(StoryFileBlock, {
        eyebrow: 'planned by claude · claude-opus-4 · 2026-09-09T09:05:00Z',
        content: '# Story 2\n\n- one\n- two\n\n```\ncode\n```\n\nA plain paragraph.',
      }),
    );

    expect(html).toContain('data-testid="wf-planned-file"');
    expect(html).toContain('data-testid="wf-planned-file-eyebrow"');
    expect(html).toContain('planned by claude · claude-opus-4 · 2026-09-09T09:05:00Z');
    expect(html).toContain('<h1>Story 2</h1>');
    expect(html).toContain('<li>one</li>');
    expect(html).toContain('<li>two</li>');
    expect(html).toContain('<pre><code>code</code></pre>');
    expect(html).toContain('<p>A plain paragraph.</p>');
  });

  it('never renders raw HTML — no dangerouslySetInnerHTML, ever', () => {
    const html = renderToStaticMarkup(
      createElement(StoryFileBlock, {
        eyebrow: '—',
        content: '<script>alert(1)</script>',
      }),
    );

    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });
});
