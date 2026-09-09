/**
 * `CommandBlock.tsx` (6.7, FR-21, UX-DR5) — the terminal resume block's first render.
 *
 * `vitest.config.ts` runs in `environment: 'node'` with no DOM-mounting library, so what is
 * asserted here is the markup as it is served: the eyebrow, the Copy control, the command in
 * a `<pre>`, the lifetime line, and the session footer's two halves. The click — the
 * clipboard write, `COPIED`, and the posted `terminal_start` — is
 * `tests/e2e/run-detail-terminal.spec.ts`'s job in a real browser, the same split
 * `run-budget-raise-box.test.ts` documents for `BudgetRaiseBox`.
 *
 * **Two of the assertions below are security assertions**, and are the browser half of AD-5:
 * the command reaches the page as a React text child rather than as markup (no
 * `dangerouslySetInnerHTML` anywhere in this app), and a command carrying a shell reference
 * renders that reference and never expands it — the value belongs to the container.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import CommandBlock from '../../src/components/run/CommandBlock';
import type { TerminalOut } from '../../src/lib/run/terminal';

const COMMAND =
  'docker compose exec -e ORCH_RUN_ID=01a0 -e ORCH_ATTEMPT_ID=01a1 backend-api sh -c ' +
  '\'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"; cd /work/wt/x && claude --resume s1\'';
const ENDS_AT = '2026-10-07T09:00:00Z';

function terminal(over: Partial<TerminalOut> = {}): TerminalOut {
  return {
    command: COMMAND,
    session_lifetime_ends_at: ENDS_AT,
    in_progress: false,
    ...over,
  } as TerminalOut;
}

function render(over: Partial<Parameters<typeof CommandBlock>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(CommandBlock, {
      terminal: terminal(),
      onCopy: () => {},
      onRelease: () => {},
      canRelease: true,
      disabled: false,
      ...over,
    }),
  );
}

describe('CommandBlock', () => {
  it('names the section the way the experience spec does', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-terminal"');
    expect(html).toContain('OR CONTINUE IN THE SESSION');
  });

  it('offers a Copy control that reads COPY before it is clicked', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-terminal-copy"');
    expect(html).toContain('>COPY<');
    expect(html).not.toContain('>COPIED<');
  });

  it('puts the command in a pre, so nothing about it is soft-wrapped', () => {
    const html = render();

    expect(html).toContain('<pre class="wf-command-code" data-testid="wf-terminal-command">');
    expect(html).toContain('claude --resume s1');
  });

  it('renders the command as text and never as markup', () => {
    // the browser half of AD-5: a command that reached the DOM as HTML would be a second
    // place a value could enter, and an escape hatch for anything the server put in it
    const html = render({
      terminal: terminal({ command: '<script>alert(1)</script> && claude --resume s1' }),
    });

    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('shows a shell reference as a reference, never as a value', () => {
    const html = render();

    expect(html).toContain('ANTHROPIC_AUTH_TOKEN=&quot;$LITELLM_API_KEY&quot;');
  });

  it('names the date the session stops being resumable', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-terminal-lifetime"');
    expect(html).toContain(`session lifetime ends ${ENDS_AT}`);
  });

  it('shows no lifetime line for a harness that states none', () => {
    const html = render({ terminal: terminal({ session_lifetime_ends_at: null }) });

    expect(html).not.toContain('data-testid="wf-terminal-lifetime"');
    expect(html).not.toContain('session lifetime ends');
  });

  it('offers no Release and no session line until a session is in progress', () => {
    const html = render();

    expect(html).not.toContain('data-testid="wf-terminal-release"');
    expect(html).not.toContain('terminal session in progress');
  });

  it('states which actions are disabled and until when while a session is open', () => {
    const html = render({ terminal: terminal({ in_progress: true }) });

    expect(html).toContain('data-testid="wf-terminal-session"');
    expect(html).toContain(
      'terminal session in progress · Answer, Continue, Skip and Retry disabled until Release',
    );
    expect(html).toContain('the run resumes by itself when the story file is done');
  });

  it('offers Release while a session is open and the server admits it', () => {
    const html = render({ terminal: terminal({ in_progress: true }) });

    expect(html).toContain('data-testid="wf-terminal-release"');
    expect(html).toContain('>Release<');
  });

  it('states the session but offers no Release the server would not apply', () => {
    // the control comes from `admitted_signals`, never from `in_progress` alone — a button
    // the endpoint answers 409 to is a button that should not be on screen
    const html = render({ terminal: terminal({ in_progress: true }), canRelease: false });

    expect(html).toContain('terminal session in progress');
    expect(html).not.toContain('data-testid="wf-terminal-release"');
  });

  it('refuses every control while another signal is in flight', () => {
    const html = render({ terminal: terminal({ in_progress: true }), disabled: true });

    expect(html.match(/disabled=""/g)?.length).toBe(2);
  });
});
