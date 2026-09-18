/**
 * Helper drawer (story 1-3): right-side panel for prompt-result and reach-agent content.
 *
 * A side panel, never a modal (FR-34). Positioned fixed to the right edge via CSS so it
 * never disturbs the log viewer or attempt selection behind it.
 *
 * `DrawerContent` and `HelperDrawerAttempt` are exported so `StepDetail.tsx` can type its
 * own state without a direct dependency on the component's internals.
 */
import { useState } from 'react';

import { TERMINAL_SESSION_LINE, sessionLifetimeLine } from '../../lib/run/terminal';

export type DrawerContent = 'prompt-result' | 'reach-agent';

export interface HelperDrawerAttempt {
  dispatch_prompt: string | null;
  retry_prompt: string | null;
  result: string | null;
  resume_command: string | null;
  session_lifetime_ends_at: string | null;
}

interface Props {
  attempt: HelperDrawerAttempt;
  initialContent: DrawerContent;
  onClose: () => void;
}

/** Shown after `TERMINAL_SESSION_LINE` in the reach-agent tab (story 1-3, Design Notes). */
const PAST_SESSION_NOTE =
  'A past session opens for interrogation; only the current stop’s session moves the run.';

export default function HelperDrawer({ attempt, initialContent, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<DrawerContent>(initialContent);

  function copy(text: string): void {
    if (navigator.clipboard) void navigator.clipboard.writeText(text);
  }

  const lifetimeLine = sessionLifetimeLine(attempt.session_lifetime_ends_at);

  return (
    <aside className="step-drawer-panel" data-testid="step-drawer">
      <div className="step-drawer-header">
        <button
          type="button"
          className="step-drawer-tab"
          data-active={activeTab === 'prompt-result'}
          onClick={() => setActiveTab('prompt-result')}
        >
          prompt · result
        </button>
        {attempt.resume_command !== null && (
          <button
            type="button"
            className="step-drawer-tab"
            data-active={activeTab === 'reach-agent'}
            onClick={() => setActiveTab('reach-agent')}
          >
            reach agent
          </button>
        )}
        <button type="button" className="step-drawer-close" onClick={onClose}>
          close
        </button>
      </div>

      <div className="step-drawer-body">
        {activeTab === 'prompt-result' && (
          <div className="step-drawer-prompt-result">
            {attempt.dispatch_prompt !== null && (
              <section className="step-drawer-section">
                <h4 className="step-drawer-section-label">dispatch prompt</h4>
                <pre className="step-drawer-pre">{attempt.dispatch_prompt}</pre>
                <button
                  type="button"
                  className="step-drawer-copy"
                  aria-label="copy dispatch prompt"
                  onClick={() => copy(attempt.dispatch_prompt!)}
                >
                  copy
                </button>
              </section>
            )}
            {attempt.retry_prompt !== null && (
              <section className="step-drawer-section">
                <h4 className="step-drawer-section-label">retry prompt</h4>
                <pre className="step-drawer-pre">{attempt.retry_prompt}</pre>
                <button
                  type="button"
                  className="step-drawer-copy"
                  aria-label="copy retry prompt"
                  onClick={() => copy(attempt.retry_prompt!)}
                >
                  copy
                </button>
              </section>
            )}
            {attempt.result !== null && (
              <section className="step-drawer-section">
                <h4 className="step-drawer-section-label">result</h4>
                <pre className="step-drawer-pre">{attempt.result}</pre>
                <button
                  type="button"
                  className="step-drawer-copy"
                  aria-label="copy result"
                  onClick={() => copy(attempt.result!)}
                >
                  copy
                </button>
              </section>
            )}
          </div>
        )}
        {activeTab === 'reach-agent' && attempt.resume_command !== null && (
          <div className="step-drawer-reach-agent">
            <section className="step-drawer-section">
              <pre className="step-drawer-pre">{attempt.resume_command}</pre>
              <button
                type="button"
                className="step-drawer-copy"
                aria-label="copy resume command"
                onClick={() => copy(attempt.resume_command!)}
              >
                copy
              </button>
            </section>
            {lifetimeLine && <p className="step-drawer-lifetime">{lifetimeLine}</p>}
            <p className="step-drawer-session-line">{TERMINAL_SESSION_LINE}</p>
            <p className="step-drawer-note">{PAST_SESSION_NOTE}</p>
          </div>
        )}
      </div>
    </aside>
  );
}
