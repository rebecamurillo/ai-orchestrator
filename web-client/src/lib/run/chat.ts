/**
 * The stop's chat thread as the Run page states it (story 3-3, AD-25): where the thread was
 * posted and how far it got. A failed post is never retried, and the sentence says so; the
 * platform's own error is shown beside it, verbatim, whatever the state.
 */
import type { components } from '../../api/schema';

export type ChatThreadOut = components['schemas']['ChatThreadOut'];

export function chatThreadText(thread: ChatThreadOut): string {
  switch (thread.state) {
    case 'posting':
      return `posting the thread to ${thread.provider}`;
    case 'open':
      return `thread posted to ${thread.provider}`;
    case 'failed':
      return 'thread post failed; not retried';
    case 'closed':
      return 'thread closed';
  }
}
