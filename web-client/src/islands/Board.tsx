/**
 * The Board island (4.14, SPEC CAP-14, FR-22, FR-24): fetches `GET /runs?view=board`, writes
 * `$board`, drives `$poll`'s cadence off `counts.running`, and renders the five columns, the
 * two empty states, and the full-surface `FailedFetch` swap. `index.astro` mounts this
 * `client:load` only once at least one Project exists — the zero-project case stays the
 * existing static `EmptyState` (see that page's own module doc).
 *
 * **Staleness guard.** `requestSeqRef` is `NewWorkflow.tsx`'s own pattern: a poll response
 * only applies while it is still the most recent request in flight, so a slow poll N can
 * never overwrite poll N+1's result — the property the brief requires of the polling store.
 *
 * **Why `AppRail`/`FooterReadout` are patched here instead of subscribing themselves.** Both
 * are `.astro` and are rendered by `AstroContainer.create()` with zero framework renderers
 * registered in two frozen unit test files (`components.test.ts`, `shell.test.ts`); nesting a
 * `client:load` component inside either would throw there. `syncFooter`/`syncRail` below
 * patch the already-rendered elements directly instead — `syncFooter` only ever replaces
 * `textContent` (no new element, nothing to style), and `syncRail`'s two possibly-new
 * elements reuse `AppRail.astro`'s own `.count`/`.needs-you` classes rather than an inline
 * `style` (`tests/unit/stylesheets.test.ts`'s frozen "styles nothing with a style attribute"
 * — `web-client/AGENTS.md`'s "no inline styles"). Astro's scoped-style compiler stamps every
 * element *that component's own template* renders with one shared `data-astro-cid-*`
 * attribute and scopes that component's `<style>` selectors to it; `copyScopeAttr` copies
 * that attribute from a sibling `AppRail.astro` already rendered onto the element this
 * island creates, so the same compiled rule reaches it with no CSS of this island's own.
 * This only ever runs in the browser (`board.spec.ts` is what proves it); `syncFooter`/
 * `syncRail` are not unit-tested, matching this codebase's own rule that DOM wiring belongs
 * in the island, not `src/lib/**` (coverage-gated at 90% lines, with no DOM to test against
 * under `environment: 'node'`).
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import type { components } from '../api/schema';
import { api } from '../api/client';
import BoardColumn from '../components/BoardColumn';
import FailedFetch from '../components/FailedFetch';
import {
  boardRequestPath,
  clockText,
  footerReadoutText,
  oldestWaitSeconds,
  surfaceReadoutText,
  totalCards,
} from '../lib/board/format';
import { $board, setBoard } from '../stores/board';
import { $poll, configurePolling, forceTick, stopPolling } from '../stores/poll';
import '../styles/board.css';

type BoardOut = components['schemas']['BoardOut'];

interface Props {
  initialProjectId: string | null;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

/** Copies `AppRail.astro`'s Astro-generated `data-astro-cid-*` scoping attribute from an
 * already-rendered sibling onto an element this island creates, so that component's own
 * compiled `<style>` (already loaded on the page) reaches it too — see this module's own doc
 * on why nothing here uses an inline `style`. */
function copyScopeAttr(from: Element, to: Element): void {
  for (const attr of Array.from(from.attributes)) {
    if (attr.name.startsWith('data-astro-cid-')) to.setAttribute(attr.name, attr.value);
  }
}

function syncFooter(board: BoardOut): void {
  const el = document.querySelector('[data-testid="footer-readout"]');
  if (!el) return;
  el.textContent = footerReadoutText(
    {
      running: board.counts.running,
      queued: board.counts.queued,
      needsYou: board.counts.needs_you,
    },
    clockText(board.generated_at),
  );
}

function syncRail(board: BoardOut): void {
  const link = document.querySelector('[data-testid="nav-workflows"]');
  if (!link) return;

  const total = totalCards(board);
  let countEl = link.querySelector<HTMLElement>('.count');
  if (total > 0) {
    if (!countEl) {
      countEl = document.createElement('span');
      countEl.className = 'count';
      copyScopeAttr(link, countEl);
      link.appendChild(countEl);
    }
    countEl.textContent = String(total);
  } else {
    countEl?.remove();
  }

  const li = link.closest('li');
  if (!li) return;
  const needsYou = board.counts.needs_you;
  let badge = li.querySelector<HTMLElement>('[data-testid="nav-needs-you"]');
  if (needsYou > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.setAttribute('data-testid', 'nav-needs-you');
      badge.setAttribute('data-signal', 'needs-you');
      badge.className = 'needs-you';
      copyScopeAttr(link, badge);
      li.appendChild(badge);
    }
    badge.textContent = `${needsYou} need you`;
  } else {
    badge?.remove();
  }
}

export default function Board({ initialProjectId }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const board = useStore($board);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchBoard(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const { data, error, response } = await api.GET('/runs', {
        params: {
          query: { view: 'board', ...(initialProjectId ? { project_id: initialProjectId } : {}) },
        },
      });
      if (seq !== requestSeqRef.current) return;
      // `GET /runs` is a union response (`Page<RunSummaryOut> | BoardOut`, one route serving
      // both the plain list and `?view=board`); `columns` only exists on the Board shape,
      // and this call always asks for it — the narrowing is a defensive runtime check, not
      // a real ambiguity.
      if (error || !data || !('columns' in data)) {
        stopPolling();
        setPhase({ kind: 'error', status: response.status });
        return;
      }
      setBoard(data);
      setPhase({ kind: 'ready' });
      configurePolling(data.counts.running > 0);
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchBoard();
    return () => stopPolling();
    // fires once on mount; every later fetch is driven by the `$poll` effect below
  }, []);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchBoard();
  }, [pollTick]);

  useEffect(() => {
    if (!board) return;
    syncFooter(board);
    syncRail(board);
  }, [board]);

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={boardRequestPath(initialProjectId)}
        status={phase.status}
        onRetry={forceTick}
      />
    );
  }

  const total = board ? totalCards(board) : 0;

  if (phase.kind === 'ready' && total === 0) {
    return (
      <section className="board-empty" data-testid="board-empty">
        <p className="board-empty-headline">NOTHING RUNNING</p>
        <ul className="board-empty-lines">
          <li>No run is currently active.</li>
          <li>Nothing is queued.</li>
        </ul>
        <p className="board-empty-action">
          <a href="/workflows/new">new workflow</a>
        </p>
      </section>
    );
  }

  const needsYou = board?.counts.needs_you ?? 0;
  const allCards = board
    ? [
        ...board.columns.queued,
        ...board.columns.running,
        ...board.columns.needs_you,
        ...board.columns.done,
        ...board.columns.failed,
      ]
    : [];

  return (
    <div className="board" data-testid="board">
      <p className="board-readout" data-testid="board-readout">
        {surfaceReadoutText(total, needsYou, oldestWaitSeconds(allCards))}
      </p>
      <button
        type="button"
        className="board-refresh"
        data-testid="board-refresh"
        onClick={forceTick}
      >
        refresh
      </button>
      <div className="board-columns">
        <BoardColumn status="queued" label="Queued" cards={board?.columns.queued ?? []} />
        <BoardColumn status="running" label="Running" cards={board?.columns.running ?? []} />
        <BoardColumn status="needs_you" label="Needs you" cards={board?.columns.needs_you ?? []} />
        <BoardColumn status="done" label="Done" cards={board?.columns.done ?? []} cap={20} />
        <BoardColumn status="failed" label="Failed" cards={board?.columns.failed ?? []} cap={20} />
      </div>
    </div>
  );
}
