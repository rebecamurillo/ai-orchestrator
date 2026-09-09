/**
 * The Run detail island (4.15, SPEC CAP-15, FR-23): one poll of `GET /runs/{id}/detail`,
 * `Header`/`Banner`/`StopBody`/`StepsTable`/`StoriesStrip`/`CostBlock`/`GateRecord`
 * composed from it, the Cancel confirm, and the effects a signal button has (`retry`,
 * `continue`, and the three that carry a payload: 6.1's `answer` and 6.6's `budget_raise`
 * and Accept (`continue` with the files the park recorded) — `cancel` is its own
 * always-present control). A screen reads one
 * endpoint and aggregates nothing (AD-8): every status shown here is `run.status`/`alert.
 * park_kind`/`admitted_signals`, verbatim off the response, never derived by this island.
 *
 * Reuses 4.13/4.14's shared polling loop (`$poll`/`configurePolling`) rather than opening a
 * second interval — `Board.tsx`'s own module doc states why that store exists at all.
 * `requestSeqRef` is the same staleness guard `Board.tsx`/`NewWorkflow.tsx` already use: a
 * slow poll response must never overwrite a newer one.
 *
 * A signal click always re-fetches on success (the binding rule: "each posts ... and
 * re-fetches") rather than patching local state — `signal_run`/`apply_step_result` are the
 * only writers of Run/Step state (AD-8), so this island never predicts what the write did.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import type { components } from '../api/schema';
import FailedFetch from '../components/FailedFetch';
import ArtifactsPanel from '../components/run/ArtifactsPanel';
import Banner from '../components/run/Banner';
import CancelModal from '../components/run/CancelModal';
import CostBlock from '../components/run/CostBlock';
import GateRecord from '../components/run/GateRecord';
import Header from '../components/run/Header';
import StepsTable from '../components/run/StepsTable';
import StopBody from '../components/run/StopBody';
import StoriesStrip from '../components/run/StoriesStrip';
import { acceptBody } from '../lib/run/accept';
import { answerBody } from '../lib/run/answer';
import { budgetRaiseBody } from '../lib/run/budget';
import { isFile } from '../lib/run/artifacts';
import { isSpecCheckpoint, plannedFilePath } from '../lib/run/checkpoint';
import { detailRequestPath, runToken, stopKind, type RunDetailOut } from '../lib/run/detail';
import { signalBody, signalsRequestPath, type SignalIn, type SignalKind } from '../lib/run/signals';
import { $poll, configurePolling, stopPolling } from '../stores/poll';
import '../styles/run-detail.css';

type ProblemDetail = components['schemas']['ProblemDetail'];
type RunFileOut = components['schemas']['RunFileOut'];

interface Props {
  runId: string;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

export default function RunDetail({ runId }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [detail, setDetail] = useState<RunDetailOut | null>(null);
  const [cancelOpen, setCancelOpen] = useState(false);
  const [posting, setPosting] = useState<SignalKind | null>(null);
  const [signalError, setSignalError] = useState<ProblemDetail | null>(null);
  const [plannedFile, setPlannedFile] = useState<RunFileOut | null>(null);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);

  async function fetchDetail(): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const { data, error, response } = await api.GET('/runs/{run_id}/detail', {
        params: { path: { run_id: runId } },
      });
      if (seq !== requestSeqRef.current) return;
      if (error || !data) {
        stopPolling();
        setPhase({ kind: 'error', status: response.status });
        return;
      }
      setDetail(data);
      setPhase({ kind: 'ready' });
      configurePolling(data.run.status === 'running');
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchDetail();
    return () => stopPolling();
    // fires once on mount; every later fetch is driven by the `$poll` effect below
  }, [runId]);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchDetail();
  }, [pollTick]);

  // The planned story file a spec checkpoint shows inline (6.2, `GET /runs/{id}/files`) —
  // a second read beside the polled detail, the same way `Header`'s own `now` prop is a
  // second fact this island supplies rather than one aggregated into the detail response
  // (AD-8: `run_detail` never reads a Workspace, so this can only ever be a second call).
  useEffect(() => {
    if (!detail) return;
    const token = runToken(detail.run, detail.alert);
    const path = isSpecCheckpoint(detail, stopKind(detail, token)) ? plannedFilePath(detail) : null;
    if (!path) {
      setPlannedFile(null);
      return;
    }
    let cancelled = false;
    void (async () => {
      const { data } = await api.GET('/runs/{run_id}/files', {
        params: { path: { run_id: runId }, query: { path } },
      });
      // `path` was given and `diff` was not, so this is always `RunFileOut` — 6.3 widened
      // the response type for the no-`path` tree branch and 6.6 for the diff mode, and
      // `isFile` is the one place the three are told apart.
      if (!cancelled) setPlannedFile(data && isFile(data) ? data : null);
    })();
    return () => {
      cancelled = true;
    };
  }, [detail, runId]);

  async function sendSignal(kind: SignalKind, body?: SignalIn): Promise<void> {
    setPosting(kind);
    setSignalError(null);
    try {
      const { error } = await api.POST('/runs/{run_id}/signals', {
        params: { path: { run_id: runId } },
        body: body ?? signalBody(kind),
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
        detail: `POST ${signalsRequestPath(runId)} → network error`,
      });
    } finally {
      setPosting(null);
    }
  }

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={detailRequestPath(runId)}
        status={phase.status}
        onRetry={() => void fetchDetail()}
      />
    );
  }
  if (!detail) return null;

  const token = runToken(detail.run, detail.alert);

  return (
    <div data-testid="wf-detail">
      <Header detail={detail} token={token} now={Date.now()} />
      <Banner detail={detail} token={token} />
      <div className="wf-body">
        <div className="wf-left">
          <StopBody
            detail={detail}
            token={token}
            onSignal={(kind) => void sendSignal(kind)}
            onCancelClick={() => setCancelOpen(true)}
            posting={posting}
            error={signalError}
            onAnswer={(text) => void sendSignal('answer', answerBody(text))}
            onRaiseBudget={(amount) => void sendSignal('budget_raise', budgetRaiseBody(amount))}
            onAccept={(paths) => void sendSignal('continue', acceptBody(paths))}
            runId={runId}
            plannedFile={plannedFile}
          />
          <div>
            <h2 className="wf-section-head">STEPS</h2>
            <StepsTable detail={detail} />
          </div>
        </div>
        <div className="wf-right">
          <StoriesStrip stories={detail.stories} />
          <CostBlock detail={detail} />
          <GateRecord detail={detail} token={token} />
          <ArtifactsPanel runId={runId} run={detail.run} folder={detail.header.meta.folder} />
        </div>
      </div>
      {cancelOpen ? (
        <CancelModal
          branch={detail.run.branch}
          posting={posting === 'cancel'}
          onConfirm={() => void sendSignal('cancel')}
          onDismiss={() => setCancelOpen(false)}
        />
      ) : null}
    </div>
  );
}
