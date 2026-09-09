/**
 * The protected-path stop's own body (6.6, FR-31, AD-17, UX-DR10): the files an attempt
 * touched that AD-17 froze, each with its mark and a link to its unified diff, the line that
 * says what accepting them does, and the button that posts exactly that list.
 *
 * Stateless — there is nothing to type. The list is not a set of checkboxes on purpose: the
 * server refuses any list that is not exactly the hits (`use_cases/signals.py::
 * ACCEPT_MISMATCH`), because a partial accept would leave a flagged file unaccepted and park
 * the resumed check on it again. What the Operator chooses is *whether*, not *which*; the
 * per-file control they need is the diff link, which is a read.
 *
 * The diff opens in a new tab rather than inline: it is git's own text, it can be long, and
 * the Run detail is a screen that polls. No `dangerouslySetInnerHTML` anywhere.
 */
import {
  ACCEPT_LABEL,
  acceptLine,
  diffHref,
  hitMark,
  type ProtectedHit,
} from '../../lib/run/accept';

interface Props {
  runId: string;
  hits: ProtectedHit[];
  storyId: string;
  onAccept: (paths: string[]) => void;
  posting: boolean;
}

export default function AcceptBox({ runId, hits, storyId, onAccept, posting }: Props) {
  return (
    <div className="wf-accept-box">
      <ul className="wf-accept-files" data-testid="wf-accept-files">
        {hits.map((hit) => (
          <li key={hit.path} data-testid={`wf-accept-file-${hit.path}`}>
            <span className="wf-accept-mark">{hitMark(hit.kind)}</span>
            <a
              className="wf-accept-diff"
              data-testid={`wf-accept-diff-${hit.path}`}
              href={diffHref(runId, hit.path)}
              target="_blank"
              rel="noreferrer"
            >
              {hit.path}
            </a>
          </li>
        ))}
      </ul>
      <p className="wf-accept-line" data-testid="wf-accept-line">
        {acceptLine(storyId)}
      </p>
      <button
        type="button"
        className="wf-signal wf-accept-submit"
        data-testid="wf-accept"
        disabled={posting}
        onClick={() => onAccept(hits.map((hit) => hit.path))}
      >
        {ACCEPT_LABEL}
      </button>
    </div>
  );
}
