/**
 * The Initiative detail island (S7): one poll of `GET /initiatives/{slug}`, the members
 * grouped by repository, each epic paired with its merge Run (`src/lib/initiative/
 * view.ts::repoGroups`), the go-live Run last, and the 404 readout.
 *
 * Reuses `stores/poll.ts`'s shared loop rather than a second interval — `RunDetail.tsx`'s
 * own precedent, `requestSeqRef`/`mountedTickRef` copied the same way: a poll response only
 * ever applies while it is still the most recent request in flight.
 *
 * **404 is not a failed fetch.** `FailedFetch` states "backend-api could not be reached"; a
 * 404 here states a true fact about this instance — no initiative was ever dispatched under
 * this slug — so it gets its own readout (`NO INITIATIVE UNDER {slug}`, `EmptyState.astro`'s
 * own visual language, S7's own required text) rather than `FailedFetch`'s retry-a-network-
 * call framing.
 *
 * **Cancel initiative (S8).** Beside the slug headline, visible/enabled only while
 * `hasCancellableMember` finds a member still queued, running or `needs_you` — a settled
 * initiative has nothing left for `POST /initiatives/{slug}/signals {kind: cancel}` to do.
 * `CancelInitiativeModal` confirms; on success this re-fetches (`RunDetail.tsx`'s own rule:
 * a signal always re-fetches rather than patching local state, AD-8's two writers again).
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import type { components } from '../api/schema';
import FailedFetch from '../components/FailedFetch';
import CancelInitiativeModal from '../components/initiative/CancelInitiativeModal';
import MemberRow from '../components/initiative/MemberRow';
import RepoSection from '../components/initiative/RepoSection';
import {
  cancelInitiativeBody,
  detailRequestPath,
  golivemembers,
  hasActiveMember,
  hasCancellableMember,
  notFoundHeadline,
  repoGroups,
  signalsRequestPath,
  type InitiativeOut,
} from '../lib/initiative/view';
import { $poll, configurePolling, stopPolling } from '../stores/poll';
import '../styles/initiative-detail.css';

type ProblemDetail = components['schemas']['ProblemDetail'];

interface Props {
  slug: string;
}

type Phase =
  | { kind: 'loading' }
  | { kind: 'ready' }
  | { kind: 'not-found' }
  | { kind: 'error'; status: number | null };

export default function InitiativeDetail({ slug }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [view, setView] = useState<InitiativeOut | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [posting, setPosting] = useState(false);
  const [signalError, setSignalError] = useState<ProblemDetail | null>(null);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchDetail(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const { data, error, response } = await api.GET('/initiatives/{slug}', {
        params: { path: { slug } },
      });
      if (seq !== requestSeqRef.current) return;
      if (error || !data) {
        stopPolling();
        setPhase(
          response.status === 404
            ? { kind: 'not-found' }
            : { kind: 'error', status: response.status },
        );
        return;
      }
      setView(data);
      setPhase({ kind: 'ready' });
      configurePolling(hasActiveMember(data));
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchDetail();
    return () => stopPolling();
    // fires once on mount (and on a navigation to a different slug); every later fetch is
    // driven by the `$poll` effect below
  }, [slug]);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchDetail();
  }, [pollTick]);

  async function cancelInitiative(): Promise<void> {
    setPosting(true);
    setSignalError(null);
    try {
      const { error } = await api.POST('/initiatives/{slug}/signals', {
        params: { path: { slug } },
        body: cancelInitiativeBody(),
      });
      if (error) {
        setSignalError(error);
        return;
      }
      setCancelOpen(false);
      await fetchDetail();
    } catch {
      setSignalError({
        status: 0,
        title: 'the request failed',
        type: 'about:blank',
        detail: `POST ${signalsRequestPath(slug)} → network error`,
      });
    } finally {
      setPosting(false);
    }
  }

  if (phase.kind === 'loading') return null;

  if (phase.kind === 'not-found') {
    return (
      <section className="newin-detail-empty" data-testid="newin-not-found">
        <p className="newin-detail-empty-headline">{notFoundHeadline(slug)}</p>
      </section>
    );
  }

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={detailRequestPath(slug)}
        status={phase.status}
        onRetry={() => void fetchDetail()}
      />
    );
  }

  if (!view) return null;

  const groups = repoGroups(view);
  const golive = golivemembers(view);
  const cancellable = hasCancellableMember(view);

  return (
    <div className="newin-detail" data-testid="newin-detail">
      <div className="newin-detail-head">
        <h1 className="newin-detail-headline">{view.slug}</h1>
        <button
          type="button"
          className="newin-signal newin-cancel"
          data-testid="newin-cancel-trigger"
          disabled={!cancellable}
          onClick={() => setCancelOpen(true)}
        >
          Cancel initiative
        </button>
      </div>
      {signalError ? (
        <p className="newin-signal-error" data-testid="newin-signal-error">
          {signalError.detail ?? signalError.title}
        </p>
      ) : null}
      {groups.map((group) => (
        <RepoSection key={group.repositoryId} group={group} members={view.members} />
      ))}
      {golive.length > 0 ? (
        <div className="newin-detail-golive" data-testid="newin-detail-golive">
          <p className="newin-detail-repo-head">go-live</p>
          {golive.map((member) => (
            <MemberRow key={member.run_id} member={member} members={view.members} />
          ))}
        </div>
      ) : null}
      {cancelOpen ? (
        <CancelInitiativeModal
          slug={view.slug}
          posting={posting}
          onConfirm={() => void cancelInitiative()}
          onDismiss={() => setCancelOpen(false)}
        />
      ) : null}
    </div>
  );
}
