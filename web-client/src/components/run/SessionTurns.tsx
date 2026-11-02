/**
 * The senior session's conversation (story 2-4, CAP-7): each turn's message and reply in
 * order. Text renders as text. A finished turn that left no reply file says so and links its
 * attempt's log, which is then the only account of what the senior did (story 2-5).
 */
import {
  LOG_LINK_LABEL,
  NO_REPLY_LINE,
  logHref,
  turnFailedLine,
  turnRunningLine,
  turnState,
  type SessionTurn,
} from '../../lib/run/session';

interface Props {
  runId: string;
  turns: readonly SessionTurn[];
}

export default function SessionTurns({ runId, turns }: Props) {
  if (turns.length === 0) return null;
  return (
    <ol className="wf-session-turns" data-testid="wf-session-turns">
      {turns.map((t) => {
        const state = turnState(t);
        const log = (
          <a className="wf-new-run-link" href={logHref(runId, t.attempt_id)}>
            {LOG_LINK_LABEL}
          </a>
        );
        return (
          <li
            key={t.attempt_id}
            className="wf-session-turn"
            data-testid={`wf-session-turn-${t.turn}`}
          >
            <p className="wf-session-meta">TURN {t.turn}</p>
            <p className="wf-session-message">{t.message}</p>
            {state === 'running' ? (
              <p className="wf-session-note" role="status" data-testid="wf-session-running">
                {turnRunningLine(t.turn)}
              </p>
            ) : null}
            {t.reply !== '' ? <p className="wf-session-reply">{t.reply}</p> : null}
            {state === 'no_reply' ? (
              <p className="wf-session-note">
                {NO_REPLY_LINE} · {log}
              </p>
            ) : null}
            {state === 'failed' ? (
              <p className="wf-signal-error">
                {turnFailedLine(t.exit_code)} · {log}
              </p>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}
