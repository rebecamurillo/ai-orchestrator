/**
 * The Runs screen's QUEUE island (4.16, SPEC CAP-16, FR-25, UX-DR14, `client:load`): one
 * poll of `GET /queue`, reused off `stores/poll.ts`'s shared loop rather than a second
 * interval (that store's own module doc — `Board.tsx`/`RunDetail.tsx`'s precedent), the
 * section head with the endpoint's own `max_active_runs`, the dense table, the empty
 * reading, and the full-surface `FailedFetch` swap.
 *
 * `requestSeqRef`/`mountedTickRef` are `Board.tsx`'s own staleness guard, copied verbatim: a
 * poll response only ever applies while it is still the most recent request in flight.
 *
 * No footer/rail sync. `Board.tsx` patches `footer-readout`/`nav-workflows` because those
 * figures are its own board-wide counts; `RunDetail.tsx`/`NewWorkflow.tsx` never touch
 * either, because their own screens answer a narrower question. This island reads one
 * endpoint and aggregates nothing (AD-8) — the queue's own figures are not the footer's.
 *
 * **The empty reading doubles as `/runs`'s frozen bare-page empty state.** `tests/e2e/
 * shell.spec.ts` (frozen, pre-dates this story) visits bare `/runs` against the shared stub
 * — which answers `GET /api/v1/queue` unconditionally empty, `stub-backend.mjs`'s own "`GET
 * /api/v1/projects` answers an empty list unconditionally" precedent, extended the same way
 * for this endpoint — and asserts a `data-testid="runs-empty"` element containing "NO RUNS":
 * the exact copy the page's own placeholder carried before this story wired a real fetch.
 * An SSR-side gate cannot substitute for it: an SSR read is never intercepted by Playwright's
 * `page.route()` (only a browser-side fetch is — `board.spec.ts`'s own module doc), so this
 * story's own `runs-queue.spec.ts` — which mocks `GET /queue` with real content — would see
 * an SSR gate permanently stuck on the real, empty stub instead. Rather than add a second,
 * SSR-only empty page, the same "queue has zero items" branch this story's own AC2 asks for
 * ("the section reads `nothing queued`") carries that `data-testid` and headline too —
 * `Board.tsx` sets the precedent, reusing `data-testid="board-empty"` for both its outer
 * zero-Project state and its own inner zero-card reading.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import FailedFetch from '../components/FailedFetch';
import QueueTable from '../components/runs/QueueTable';
import {
  hasRunningRow,
  queueRequestPath,
  queueSectionHeadText,
  type QueueItemOut,
} from '../lib/runs/queue';
import { $poll, configurePolling, stopPolling } from '../stores/poll';
import '../styles/board.css';
import '../styles/runs.css';

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

export default function RunsQueue() {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [items, setItems] = useState<QueueItemOut[]>([]);
  const [maxActiveRuns, setMaxActiveRuns] = useState(0);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchQueue(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const { data, error, response } = await api.GET('/queue');
      if (seq !== requestSeqRef.current) return;
      if (error || !data) {
        stopPolling();
        setPhase({ kind: 'error', status: response.status });
        return;
      }
      setItems(data.items);
      setMaxActiveRuns(data.max_active_runs);
      setPhase({ kind: 'ready' });
      configurePolling(hasRunningRow(data.items));
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchQueue();
    return () => stopPolling();
    // fires once on mount; every later fetch is driven by the `$poll` effect below
  }, []);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchQueue();
  }, [pollTick]);

  // nothing to show until the first fetch resolves — `RunDetail.tsx`'s own precedent, and
  // this story's own operating rule: "a `client:load` island needs a hydration gate"
  if (phase.kind === 'loading') return null;

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={queueRequestPath()}
        status={phase.status}
        onRetry={() => void fetchQueue()}
      />
    );
  }

  return (
    <section className="runs-queue" data-testid="runs-queue">
      <h2 className="runs-section-head">{queueSectionHeadText(maxActiveRuns)}</h2>
      {items.length === 0 ? (
        <div className="runs-empty" data-testid="runs-empty">
          <p className="runs-empty-headline">NO RUNS</p>
          <p className="runs-empty-line">nothing queued.</p>
        </div>
      ) : (
        <QueueTable items={items} />
      )}
    </section>
  );
}
