/**
 * The stop's chat thread under the Alert banner (story 3-3): one neutral line, never a
 * signal colour (NFR-6), with the platform's error printed verbatim as text when there is one.
 */
import { chatThreadText, type ChatThreadOut } from '../../lib/run/chat';

interface Props {
  thread: ChatThreadOut;
}

export default function ChatThreadLine({ thread }: Props) {
  return (
    <p className="wf-chat-thread" data-testid="wf-chat-thread" data-state={thread.state}>
      <span>chat · {chatThreadText(thread)}</span>
      {thread.error ? (
        <span className="wf-chat-thread-error" data-testid="wf-chat-thread-error">
          {thread.error}
        </span>
      ) : null}
    </p>
  );
}
