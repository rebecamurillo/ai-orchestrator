/**
 * `AttemptsTable.tsx` (story 5, 2026-09-25): static rendering coverage for the attempts table.
 *
 * 8 tests covering:
 * (1) seven column headers rendered: #, status, harness, model, duration, cost, exit
 * (2) status token span has data-signal from tokenSignal
 * (3) selected row <tr> carries data-selected="true"
 * (4) unselected row carries data-selected="false"
 * (5) step-prompt-{n} button present when command:null, step-reach absent when resume_command:null
 * (6) step-reach-{n} button present when command:null and resume_command set
 * (7) step-prompt-{n} absent when command is non-null (shell step)
 * (8) em-dash rendered for null harness, model, duration, cost, and exit_code
 *
 * Pattern: createElement + renderToStaticMarkup, same as helper-drawer-render.test.ts.
 * vitest.config.ts runs in environment:'node'; no DOM-mounting library is used.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import AttemptsTable, { type AttemptDetail } from '../../src/components/run/AttemptsTable';

function attempt(over: Partial<AttemptDetail> = {}): AttemptDetail {
  return {
    id: 'a1',
    n: 1,
    status: 'done',
    token: 'DON',
    started_at: null,
    ended_at: null,
    seconds: null,
    harness: null,
    model: null,
    session_id: null,
    exit_code: null,
    cost_usd: null,
    cost_provisional: false,
    tokens_in: null,
    tokens_out: null,
    dispatch_prompt: null,
    retry_prompt: null,
    result: null,
    command: null,
    resume_command: null,
    session_lifetime_ends_at: null,
    ...over,
  };
}

function render(attempts: AttemptDetail[], selectedN: number | null = null): string {
  return renderToStaticMarkup(
    createElement(AttemptsTable, {
      attempts,
      selectedN,
      onSelect: () => {},
      onDrawer: () => {},
    }),
  );
}

describe('AttemptsTable — column headers (test 1)', () => {
  it('renders seven column headers: #, status, harness, model, duration, cost, exit', () => {
    const html = render([attempt()]);
    for (const header of ['#', 'status', 'harness', 'model', 'duration', 'cost', 'exit']) {
      expect(html).toContain(`>${header}<`);
    }
  });
});

describe('AttemptsTable — status token signal (test 2)', () => {
  it('status token span has data-signal="run" from tokenSignal for token RUN', () => {
    const html = render([attempt({ token: 'RUN', status: 'running' })]);
    expect(html).toContain('class="wf-step-token"');
    expect(html).toContain('data-signal="run"');
    expect(html).toContain('>RUN<');
  });
});

describe('AttemptsTable — row selection (tests 3 and 4)', () => {
  it('selected row <tr> carries data-selected="true" when attempt.n === selectedN', () => {
    const html = render([attempt({ n: 1 })], 1);
    expect(html).toContain('data-selected="true"');
  });

  it('unselected row carries data-selected="false" when attempt.n !== selectedN', () => {
    const html = render([attempt({ n: 2 }), attempt({ n: 1, id: 'a2' })], 1);
    expect(html).toContain('data-selected="false"');
  });
});

describe('AttemptsTable — actions column (tests 5, 6, 7)', () => {
  it('renders step-prompt-{n} but not step-reach-{n} when command is null and resume_command is null (test 5)', () => {
    const html = render([attempt({ n: 3, command: null, resume_command: null })]);
    expect(html).toContain('data-testid="step-prompt-3"');
    expect(html).not.toContain('data-testid="step-reach-3"');
  });

  it('renders both step-prompt-{n} and step-reach-{n} when command:null and resume_command set (test 6)', () => {
    const html = render([
      attempt({ n: 4, command: null, resume_command: 'cd /x && opencode run --session s' }),
    ]);
    expect(html).toContain('data-testid="step-prompt-4"');
    expect(html).toContain('data-testid="step-reach-4"');
  });

  it('omits step-prompt-{n} button when command is non-null (shell step, test 7)', () => {
    const html = render([attempt({ n: 5, command: 'make lint' })]);
    expect(html).not.toContain('data-testid="step-prompt-5"');
  });
});

describe('AttemptsTable — nullable cells (test 8)', () => {
  it('renders em-dash for null harness, model, duration, cost, and exit_code', () => {
    const html = render([
      attempt({ harness: null, model: null, seconds: null, cost_usd: null, exit_code: null }),
    ]);
    expect(html.match(/—/g)?.length).toBeGreaterThanOrEqual(5);
  });
});
