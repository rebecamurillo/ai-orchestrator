/**
 * The Runs screen's HISTORY island (7.5, SPEC CAP-5, FR-25 history, UX-DR14, `client:load`):
 * one poll of `GET /steps`, the dense table, the *more* control that appends the next page,
 * the empty reading, and the full-surface `FailedFetch` swap.
 *
 * **It polls the first page only** (the brief's own implementation note). A poll replaces the
 * first page and drops whatever *more* had appended: the pages below it were read against a
 * cursor from a history that has since grown, and re-stitching them would print rows twice.
 * Losing them is honest and visible — the *more* control is still there to read them again —
 * where a silent duplicate would not be.
 *
 * **It subscribes to the shared `$poll` loop but never re-times it.** `configurePolling` owns
 * one interval for the whole page (`stores/poll.ts`), and this is the first screen to carry
 * two islands that read it: whichever called it last would decide the cadence for both, so a
 * history reporting "nothing executing" would slow the queue beside it down from 5 s to 30 s
 * — and the queue's own frozen poll-tick scenario asserts exactly that 5 s. The queue is the
 * right authority anyway: an executing attempt belongs to an executing Run, and `GET /queue`
 * already reports that Run as `running`, so there is no cadence this section could ask for
 * that the section above it has not already asked for. The consequence is that a failed
 * queue poll (`RunsQueue.tsx` calls `stopPolling`) stops this section refreshing too, until
 * that section's own Retry restarts the loop.
 *
 * `requestSeqRef`/`mountedTickRef` are `Board.tsx`'s staleness guard, copied verbatim: a poll
 * response only ever applies while it is still the most recent *first-page* request in
 * flight. A *more* click does not touch that guard — it is not a poll, and a poll landing
 * mid-append is exactly the case the paragraph above discards.
 *
 * **Its own test-ids, never the queue's.** `runs-empty` and `fetch-failed` each already match
 * exactly one element on this page (`tests/e2e/shell.spec.ts`, `tests/e2e/runs-queue.spec.ts`,
 * both frozen, assert on them under Playwright's strict mode), so this section's empty
 * reading is `runs-history-empty` and its failed read is `runs-history-failed`. Two elements
 * with one of those ids would break a frozen test that has nothing to do with this story.
 *
 * The filters arrive as props from the page rather than being read from `location` here: the
 * bar is server-rendered and a filter click is a full navigation (`runs/index.astro`), so the
 * page already knows them and this island never parses a URL.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import FailedFetch from '../components/FailedFetch';
import HistoryTable from '../components/runs/HistoryTable';
import {
  END_TEXT,
  HISTORY_EMPTY_HEADLINE,
  HISTORY_EMPTY_LINE,
  HISTORY_SECTION_HEAD,
  historyQuery,
  historyRequestPath,
  MORE_LABEL,
  type HistoryRowOut,
} from '../lib/runs/history';
import { $poll } from '../stores/poll';
import '../styles/runs.css';

interface Props {
  projectId: string | null;
  status: string | null;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

export default function RunsHistory({ projectId, status }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [rows, setRows] = useState<HistoryRowOut[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [ended, setEnded] = useState(false);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchFirstPage(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const { data, error, response } = await api.GET('/steps', {
        params: { query: historyQuery(projectId, status, null) },
      });
      if (seq !== requestSeqRef.current) return;
      if (error || !data) {
        setPhase({ kind: 'error', status: response.status });
        return;
      }
      setRows(data.items);
      setCursor(data.next_cursor ?? null);
      setEnded(data.next_cursor == null);
      setPhase({ kind: 'ready' });
    } catch {
      if (seq !== requestSeqRef.current) return;
      setPhase({ kind: 'error', status: null });
    }
  }

  async function fetchMore(): Promise<void> {
    if (cursor === null) return;
    setLoadingMore(true);
    try {
      const { data, error } = await api.GET('/steps', {
        params: { query: historyQuery(projectId, status, cursor) },
      });
      if (error || !data) return;
      setRows((current) => [...current, ...data.items]);
      setCursor(data.next_cursor ?? null);
      setEnded(data.next_cursor == null);
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    void fetchFirstPage();
    // fires once on mount; every later read is a `$poll` tick or a `more` click
  }, []);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchFirstPage();
  }, [pollTick]);

  // nothing to show until the first read resolves — `RunsQueue.tsx`'s own hydration gate
  if (phase.kind === 'loading') return null;

  return (
    <section className="runs-history" data-testid="runs-history">
      <h2 className="runs-section-head">{HISTORY_SECTION_HEAD}</h2>
      {phase.kind === 'error' ? (
        <div data-testid="runs-history-failed">
          <FailedFetch
            method="GET"
            path={historyRequestPath(projectId, status)}
            status={phase.status}
            onRetry={() => void fetchFirstPage()}
          />
        </div>
      ) : rows.length === 0 ? (
        <div className="runs-empty" data-testid="runs-history-empty">
          <p className="runs-empty-headline">{HISTORY_EMPTY_HEADLINE}</p>
          <p className="runs-empty-line">{HISTORY_EMPTY_LINE}</p>
        </div>
      ) : (
        <>
          <HistoryTable rows={rows} />
          <div className="runs-history-more">
            {ended ? (
              <p className="runs-history-end">{END_TEXT}</p>
            ) : (
              <button
                type="button"
                data-testid="runs-history-more"
                disabled={loadingMore}
                onClick={() => void fetchMore()}
              >
                {MORE_LABEL}
              </button>
            )}
          </div>
        </>
      )}
    </section>
  );
}
