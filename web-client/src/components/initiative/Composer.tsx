/**
 * The message box of the current conversation step. It posts the owner's words and nothing
 * else: no control here closes a step. It is never disabled by a running turn (a post on a
 * `conversation` stop is queued, never refused); only the POST in flight blocks a second send.
 */
import { useState, type KeyboardEvent } from 'react';

import { api } from '../../api/client';
import { isSendKey } from '../../lib/initiative/conversation';
import { messageBody } from '../../lib/run/session';
import { forceTick } from '../../stores/poll';

interface Props {
  runId: string;
  hint: string;
}

export default function Composer({ runId, hint }: Props) {
  const [text, setText] = useState('');
  const [posting, setPosting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function send(): Promise<void> {
    if (posting || text.trim() === '') return;
    setPosting(true);
    try {
      const { error: problem } = await api.POST('/runs/{run_id}/session/messages', {
        params: { path: { run_id: runId } },
        body: messageBody(text),
      });
      if (problem) {
        const p = problem as { detail?: string; title?: string };
        setError(p.detail ?? p.title ?? 'The message was not sent.');
        return;
      }
      setText('');
      setError(null);
      forceTick();
    } catch {
      setError('The message was not sent.');
    } finally {
      setPosting(false);
    }
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>): void {
    if (!isSendKey(e)) return;
    e.preventDefault();
    void send();
  }

  return (
    <div className="ini-composer">
      <label htmlFor="ini-message">message</label>
      <textarea
        id="ini-message"
        data-testid="ini-message"
        rows={4}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKeyDown}
      />
      {error ? <p role="alert">{error}</p> : null}
      <button
        type="button"
        className="primary"
        data-testid="ini-send"
        disabled={posting}
        onClick={() => void send()}
      >
        Send
      </button>
      <p className="ini-hint">{hint}</p>
    </div>
  );
}
