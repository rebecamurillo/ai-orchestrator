/**
 * The Initiatives board island (story 10.1): fetches `GET /initiatives`, renders one column
 * per workflow the response names, then DONE. Placement, status, step line and progress all
 * come from the response — see `lib/initiatives/format.ts`.
 *
 * `requestSeqRef` and the `$poll` mounted-tick skip are `Board.tsx`'s own staleness guard.
 * The rail's Initiatives count and need-you line are patched into the already-rendered
 * `AppRail.astro` the way `Board.tsx`'s `syncRail` patches Workflows: `AppRail` cannot host a
 * framework island, and `copyScopeAttr` lets its compiled scoped styles reach the new
 * elements without an inline `style`.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import type { components } from '../api/schema';
import { api } from '../api/client';
import FailedFetch from '../components/FailedFetch';
import InitiativeColumn from '../components/initiatives/InitiativeColumn';
import {
  cancelledHiddenText,
  hasRunning,
  initiativesRequestPath,
  placeItems,
  readoutText,
  type InitiativeFilter,
} from '../lib/initiatives/format';
import { $poll, configurePolling, forceTick, stopPolling } from '../stores/poll';
import '../styles/initiatives.css';

type ListOut = components['schemas']['InitiativeListOut'];

interface Props {
  initialProjectId: string | null;
  initialFilter: InitiativeFilter;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

const FILTERS: { value: InitiativeFilter; label: string }[] = [
  { value: 'ongoing', label: 'ONGOING' },
  { value: 'needs_you', label: 'NEEDS YOU' },
  { value: 'all', label: 'ALL' },
];

function copyScopeAttr(from: Element, to: Element): void {
  for (const attr of Array.from(from.attributes)) {
    if (attr.name.startsWith('data-astro-cid-')) to.setAttribute(attr.name, attr.value);
  }
}

function syncRail(list: ListOut): void {
  const link = document.querySelector('[data-testid="nav-initiatives"]');
  if (!link) return;

  const total = list.counts.ongoing;
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
  const needYou = list.counts.need_you;
  let badge = li.querySelector<HTMLElement>('[data-testid="nav-initiatives-needs-you"]');
  if (needYou > 0) {
    if (!badge) {
      badge = document.createElement('span');
      badge.setAttribute('data-testid', 'nav-initiatives-needs-you');
      badge.setAttribute('data-signal', 'needs-you');
      badge.className = 'needs-you';
      copyScopeAttr(link, badge);
      li.appendChild(badge);
    }
    badge.textContent = `${needYou} need you`;
  } else {
    badge?.remove();
  }
}

export default function Initiatives({ initialProjectId, initialFilter }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [filter, setFilter] = useState<InitiativeFilter>(initialFilter);
  const [data, setData] = useState<ListOut | null>(null);
  const [showCancelled, setShowCancelled] = useState(false);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);
  const filterRef = useRef(filter);
  filterRef.current = filter;

  async function fetchList(f: InitiativeFilter): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const {
        data: out,
        error,
        response,
      } = await api.GET('/initiatives', {
        params: {
          query: { filter: f, ...(initialProjectId ? { project_id: initialProjectId } : {}) },
        },
      });
      if (seq !== requestSeqRef.current) return;
      if (error || !out) {
        stopPolling();
        setPhase({ kind: 'error', status: response.status });
        return;
      }
      setData(out);
      setPhase({ kind: 'ready' });
      configurePolling(hasRunning(out.items));
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  function chooseFilter(f: InitiativeFilter): void {
    const params = new URLSearchParams(window.location.search);
    params.set('filter', f);
    history.replaceState(null, '', `?${params.toString()}`);
    setFilter(f);
    void fetchList(f);
  }

  useEffect(() => {
    void fetchList(filterRef.current);
    return () => stopPolling();
    // fires once on mount; later fetches come from the segments and the `$poll` effect
  }, []);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchList(filterRef.current);
  }, [pollTick]);

  useEffect(() => {
    if (data) syncRail(data);
  }, [data]);

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={initiativesRequestPath(filter, initialProjectId)}
        status={phase.status}
        onRetry={forceTick}
      />
    );
  }
  if (!data) return null;

  const nowMs = Date.now();
  const placed = placeItems(data.columns, data.items);
  const doneItems = showCancelled ? [...placed.done, ...placed.cancelled] : placed.done;

  return (
    <div className="ini" data-testid="initiatives">
      <div className="ini-bar">
        <div className="ini-filter" data-testid="initiatives-filter">
          {FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              aria-current={filter === f.value ? 'true' : undefined}
              onClick={() => chooseFilter(f.value)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <p className="ini-readout" data-testid="initiatives-readout">
          {readoutText(data.counts, nowMs)}
        </p>
      </div>
      {data.items.length === 0 ? (
        <section className="ini-empty" data-testid="initiatives-empty">
          <p className="ini-empty-headline">NO INITIATIVES</p>
          <p>An initiative starts from a project: a name and a first message.</p>
          <p>
            <a href="/initiatives/new">New initiative</a>
          </p>
        </section>
      ) : (
        <div className="ini-board" data-testid="initiatives-board">
          {data.columns.map((c) => (
            <InitiativeColumn
              key={c.workflow}
              testId={`initiatives-col-${c.workflow}`}
              name={c.workflow}
              type={c.type}
              items={placed.byColumn.get(c.workflow) ?? []}
              nowMs={nowMs}
            />
          ))}
          <InitiativeColumn
            testId="initiatives-col-done"
            name="DONE · LAST 30 DAYS"
            items={doneItems}
            nowMs={nowMs}
            footer={
              placed.cancelled.length > 0 && !showCancelled ? (
                <button
                  type="button"
                  className="ini-cancelled"
                  onClick={() => setShowCancelled(true)}
                >
                  {cancelledHiddenText(placed.cancelled.length)}
                </button>
              ) : null
            }
          />
        </div>
      )}
    </div>
  );
}
