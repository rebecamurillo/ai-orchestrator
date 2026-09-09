/**
 * `src/lib/run/terminal.ts` (6.7, FR-21, UX-DR5, UX-DR9) — the terminal block's pure half.
 *
 * Two things are asserted at length beyond the derivations themselves:
 *
 * 1. **The three frozen filters are untouched.** `stopSignals`, `blockedSignals` and
 *    `checkpointSignals` each have a test that predates this story; `terminalSignals` is a
 *    sibling, and the assertions below show it appending rather than any of them widening.
 * 2. **The command is passed through, never rebuilt.** The screen renders exactly the string
 *    the server proved carries no secret value, so a helper that reassembled it in the
 *    browser would be a second place a credential could enter. `terminalBlock` returns the
 *    server's object whole, and nothing in this module writes a command.
 */
import { describe, expect, it } from 'vitest';

import {
  blockedSignals,
  stopSignals,
  type RunDetailOut,
  type SignalKind,
} from '../../src/lib/run/detail';
import { checkpointSignals } from '../../src/lib/run/checkpoint';
import {
  COMMAND_EYEBROW,
  COPIED_LABEL,
  COPIED_MS,
  COPY_LABEL,
  RELEASE_LABEL,
  TERMINAL_RELEASE,
  TERMINAL_SESSION_LINE,
  TERMINAL_START,
  offersRelease,
  sessionLifetimeLine,
  terminalBlock,
  terminalSignals,
} from '../../src/lib/run/terminal';

const COMMAND =
  'docker compose exec -e ORCH_RUN_ID=01a0 -e ORCH_ATTEMPT_ID=01a1 -e ORCH_STORY_ID=4-1 ' +
  '-e ORCH_HARNESS=claude -e ORCH_PROJECT=acme -e ORCH_TAGS=run:01a0 ' +
  `-e ORCH_LANGFUSE_TAGS='["run:01a0"]' -e TRACEPARENT=00-abc-def-01 backend-api sh -c ` +
  '\'export ANTHROPIC_AUTH_TOKEN="$LITELLM_API_KEY"; cd /work/wt/x && claude --resume s1\'';

const ENDS_AT = '2026-10-07T09:00:00Z';

function detail(over: Record<string, unknown> = {}): RunDetailOut {
  return {
    run: {
      status: 'needs_you',
      terminal_session: false,
      admitted_signals: ['answer', 'cancel'],
      ...over,
    },
  } as unknown as RunDetailOut;
}

function withTerminal(over: Record<string, unknown> = {}): RunDetailOut {
  return detail({
    terminal: {
      command: COMMAND,
      session_lifetime_ends_at: ENDS_AT,
      in_progress: false,
      ...over,
    },
  });
}

describe('terminalBlock', () => {
  it('hands back the server’s own block, command included, byte for byte', () => {
    const block = terminalBlock(withTerminal());

    expect(block).not.toBeNull();
    expect(block?.command).toBe(COMMAND);
  });

  it('is null for a Run the escape hatch does not apply to', () => {
    expect(terminalBlock(detail({ terminal: null }))).toBeNull();
  });

  it('is null for a response written before this field existed', () => {
    // `terminal` is `_drop_default`-guarded on the wire, so a fixture that predates it is a
    // Run with no terminal rather than a crash (AD-3)
    expect(terminalBlock(detail())).toBeNull();
  });
});

describe('sessionLifetimeLine', () => {
  it('names the date the session stops being resumable', () => {
    expect(sessionLifetimeLine(ENDS_AT)).toBe(`session lifetime ends ${ENDS_AT}`);
  });

  it('says nothing at all for a harness that states no lifetime', () => {
    expect(sessionLifetimeLine(null)).toBe('');
    expect(sessionLifetimeLine(undefined)).toBe('');
  });
});

describe('offersRelease', () => {
  it('follows the server’s own list, not the block’s in_progress', () => {
    expect(offersRelease(['cancel', 'terminal_release'])).toBe(true);
    expect(offersRelease(['answer', 'cancel'])).toBe(false);
  });

  it('offers nothing at all for a Run that admits nothing', () => {
    expect(offersRelease([])).toBe(false);
  });
});

describe('terminalSignals', () => {
  it('offers Release exactly when the server admits it', () => {
    expect(terminalSignals(['cancel', 'terminal_release'])).toEqual(['terminal_release']);
    expect(terminalSignals(['answer', 'skip_story', 'cancel'])).toEqual([]);
  });

  it('never invents a control the server did not admit', () => {
    // buttons come from `admitted_signals`; a hardcoded Release would offer an action the
    // endpoint answers 409 to
    expect(terminalSignals([])).toEqual([]);
  });

  it('is a sibling of the three frozen filters, not a widening of any of them', () => {
    const admitted: SignalKind[] = ['cancel', 'terminal_release'];

    expect(stopSignals(admitted)).toEqual([]);
    expect(blockedSignals(admitted)).toEqual([]);
    expect(checkpointSignals(admitted)).toEqual([]);
    expect(terminalSignals(admitted)).toEqual(['terminal_release']);
  });
});

describe('the copy the block renders', () => {
  it('names the section the way UX-DR5 does', () => {
    expect(COMMAND_EYEBROW).toBe('OR CONTINUE IN THE SESSION');
  });

  it('states the session line verbatim, naming every action it disables and the way out', () => {
    expect(TERMINAL_SESSION_LINE).toBe(
      'terminal session in progress · Answer, Continue, Skip and Retry disabled until ' +
        'Release — the run resumes by itself when the story file is done and the tree is clean',
    );
  });

  it('confirms a copy in place for about 1.2 s', () => {
    expect(COPY_LABEL).toBe('COPY');
    expect(COPIED_LABEL).toBe('COPIED');
    expect(COPIED_MS).toBe(1200);
  });

  it('labels the control that ends the session', () => {
    expect(RELEASE_LABEL).toBe('Release');
  });

  it('posts the two kinds AD-13 names', () => {
    expect(TERMINAL_START).toBe('terminal_start');
    expect(TERMINAL_RELEASE).toBe('terminal_release');
  });
});
