/**
 * The terminal resume command block (6.7, FR-21, UX-DR5, UX-DR9) — `DESIGN.md`'s
 * `{components.command-block}`: the darkest element in the product, because it is the one
 * thing on screen that is not the app but a quotation from the operator's own shell.
 *
 * **The command is rendered as text and never as markup.** It arrives whole from
 * `run.terminal.command`, goes into a `<pre>` as a React child, and is never split, rebuilt
 * or interpolated here. No `dangerouslySetInnerHTML`, in this file or anywhere in this app.
 *
 * **Copy is best-effort, and the session mark is not.** `navigator.clipboard` is unavailable
 * over plain HTTP and can be refused by permission, so the write is guarded — but the click
 * still posts `terminal_start` and still reads `COPIED`, because the Operator's intent was to
 * take the session over and the block's text is selectable either way. Marking the session on
 * a copy that silently failed is the safe error: the actions come back with one *Release*.
 *
 * The block never soft-wraps (`white-space: pre`, `overflow-x: auto` in `run-detail.css`): a
 * wrapped command is a broken paste, which is the one failure this element exists to prevent.
 */
import { useEffect, useRef, useState } from 'react';

import {
  COMMAND_EYEBROW,
  COPIED_LABEL,
  COPIED_MS,
  COPY_LABEL,
  RELEASE_LABEL,
  TERMINAL_SESSION_LINE,
  sessionLifetimeLine,
  type TerminalOut,
} from '../../lib/run/terminal';

interface Props {
  terminal: TerminalOut;
  /** Posts `terminal_start` — the click that marks the session (AD-13). */
  onCopy: () => void;
  /** Posts `terminal_release`. */
  onRelease: () => void;
  /** Whether `admitted_signals` carries `terminal_release` — the button comes from the
   * server's own list, never from `in_progress` alone. */
  canRelease: boolean;
  /** True while any signal on this screen is in flight. */
  disabled: boolean;
}

export default function CommandBlock({ terminal, onCopy, onRelease, canRelease, disabled }: Props) {
  const [copied, setCopied] = useState(false);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => clearTimer(timerRef), []);

  async function copy(): Promise<void> {
    try {
      await navigator.clipboard?.writeText(terminal.command);
    } catch {
      // a clipboard the browser refuses is not a reason to leave the session unmarked
    }
    setCopied(true);
    clearTimer(timerRef);
    timerRef.current = setTimeout(() => setCopied(false), COPIED_MS);
    onCopy();
  }

  const lifetime = sessionLifetimeLine(terminal.session_lifetime_ends_at);

  return (
    <section className="wf-command" data-testid="wf-terminal">
      <div className="wf-command-bar">
        <span className="wf-command-eyebrow">{COMMAND_EYEBROW}</span>
        <button
          type="button"
          className="wf-command-copy"
          data-testid="wf-terminal-copy"
          disabled={disabled}
          onClick={() => void copy()}
        >
          {copied ? COPIED_LABEL : COPY_LABEL}
        </button>
      </div>
      <pre className="wf-command-code" data-testid="wf-terminal-command">
        {terminal.command}
      </pre>
      {lifetime ? (
        <p className="wf-command-lifetime" data-testid="wf-terminal-lifetime">
          {lifetime}
        </p>
      ) : null}
      {terminal.in_progress ? (
        <div className="wf-command-session" data-testid="wf-terminal-session">
          <p className="wf-command-session-line" role="status">
            {TERMINAL_SESSION_LINE}
          </p>
          {canRelease ? (
            <button
              type="button"
              className="wf-signal"
              data-testid="wf-terminal-release"
              disabled={disabled}
              onClick={onRelease}
            >
              {RELEASE_LABEL}
            </button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function clearTimer(ref: { current: ReturnType<typeof setTimeout> | null }): void {
  if (ref.current !== null) {
    clearTimeout(ref.current);
    ref.current = null;
  }
}
