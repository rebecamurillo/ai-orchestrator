/**
 * `HelperDrawer.tsx` (story 1-3) — static rendering coverage for the I/O matrix rows
 * that do not require click interaction:
 *
 * - Row 1 (partial): "prompt · result" tab shows dispatch_prompt, retry_prompt, result blocks
 * - Row 2 (partial): "reach agent" tab shows resume_command block, TERMINAL_SESSION_LINE, note
 * - Row 3 (partial): "reach agent" tab button absent inside the drawer when resume_command null
 *
 * Rows 4–6 (close, same-button toggle, tab switch) require click events and are covered by
 * `tests/e2e/step-detail.spec.ts`.  Row 7 (shell-step → no attempt buttons in StepDetail)
 * and the full reach-agent button absence on the attempt row are also e2e concerns since
 * StepDetail uses async hooks and API calls that `renderToStaticMarkup` cannot drive.
 *
 * Pattern: `createElement` + `renderToStaticMarkup`, same as `run-stop-body-answer.test.ts`.
 * `vitest.config.ts` runs in `environment: 'node'`; no DOM-mounting library is used.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HelperDrawer, { type HelperDrawerAttempt } from '../../src/components/run/HelperDrawer';
import { TERMINAL_SESSION_LINE } from '../../src/lib/run/terminal';

const DISPATCH_PROMPT = 'Read the spec and implement story 1-3.';
const RETRY_PROMPT = 'Fix the test failures before proceeding.';
const RESULT = '## Auto Run Result\n\nall tests green';
const RESUME_CMD = 'docker compose exec backend-api sh -c claude-resume-s42';
const LIFETIME = '2026-10-16T10:00:00Z';

function attempt(over: Partial<HelperDrawerAttempt> = {}): HelperDrawerAttempt {
  return {
    dispatch_prompt: DISPATCH_PROMPT,
    retry_prompt: null,
    result: RESULT,
    resume_command: RESUME_CMD,
    session_lifetime_ends_at: LIFETIME,
    ...over,
  };
}

function render(props: Parameters<typeof HelperDrawer>[0]): string {
  return renderToStaticMarkup(createElement(HelperDrawer, props));
}

describe('HelperDrawer — prompt-result tab (row 1)', () => {
  it('renders dispatch_prompt in the prompt-result tab', () => {
    const html = render({ attempt: attempt(), initialContent: 'prompt-result', onClose: () => {} });
    expect(html).toContain(DISPATCH_PROMPT);
  });

  it('renders result block in the prompt-result tab when result is non-null', () => {
    const html = render({ attempt: attempt(), initialContent: 'prompt-result', onClose: () => {} });
    expect(html).toContain(RESULT);
  });

  it('renders retry_prompt block when retry_prompt is non-null', () => {
    const html = render({
      attempt: attempt({ retry_prompt: RETRY_PROMPT }),
      initialContent: 'prompt-result',
      onClose: () => {},
    });
    expect(html).toContain(RETRY_PROMPT);
  });

  it('omits retry_prompt block when retry_prompt is null', () => {
    const html = render({
      attempt: attempt({ retry_prompt: null }),
      initialContent: 'prompt-result',
      onClose: () => {},
    });
    expect(html).not.toContain('retry prompt');
  });
});

describe('HelperDrawer — reach-agent tab (row 2)', () => {
  it('renders the resume_command in the reach-agent tab', () => {
    const html = render({
      attempt: attempt(),
      initialContent: 'reach-agent',
      onClose: () => {},
    });
    expect(html).toContain(RESUME_CMD);
  });

  it('renders TERMINAL_SESSION_LINE in the reach-agent tab', () => {
    const html = render({
      attempt: attempt(),
      initialContent: 'reach-agent',
      onClose: () => {},
    });
    expect(html).toContain(TERMINAL_SESSION_LINE);
  });

  it('renders the past-session note in the reach-agent tab', () => {
    const html = render({
      attempt: attempt(),
      initialContent: 'reach-agent',
      onClose: () => {},
    });
    expect(html).toContain('only the current stop');
  });

  it('renders the session lifetime line when session_lifetime_ends_at is non-null', () => {
    const html = render({
      attempt: attempt(),
      initialContent: 'reach-agent',
      onClose: () => {},
    });
    expect(html).toContain('session lifetime ends');
  });
});

describe('HelperDrawer — reach-agent tab button absent when resume_command null (row 3 partial)', () => {
  it('omits the reach-agent tab button when resume_command is null', () => {
    const html = render({
      attempt: attempt({ resume_command: null }),
      initialContent: 'prompt-result',
      onClose: () => {},
    });
    expect(html).not.toContain('reach agent');
  });

  it('renders the reach-agent tab button when resume_command is non-null', () => {
    const html = render({
      attempt: attempt(),
      initialContent: 'prompt-result',
      onClose: () => {},
    });
    expect(html).toContain('reach agent');
  });
});
