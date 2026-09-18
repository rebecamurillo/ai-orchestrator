/**
 * The Run detail island (4.15, SPEC CAP-15, FR-23): one poll of `GET /runs/{id}/detail`,
 * `Header`/`Banner`/`StopBody`/`StepsTable`/`StoriesStrip`/`CostBlock`/`GateRecord`
 * composed from it, the Cancel confirm, and the effects a signal button has (`retry`,
 * `continue`, and the three that carry a payload: 6.1's `answer` and 6.6's `budget_raise`
 * and Accept (`continue` with the files the park recorded); 6.7's `terminal_start` and
 * `terminal_release` come off the command block — `cancel` is its own
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
 *
 * **`#step-{seq}` (7.5).** A Runs history row links here with a fragment naming one Steps
 * row (`lib/runs/history.ts::rowHref`). The browser cannot honour it: this island renders
 * nothing until its first fetch resolves, so the row does not exist while the browser is
 * still looking for it. The effect below scrolls to it once the first detail has rendered
 * and promotes it for `PROMOTED_MS` (`lib/run/anchor.ts`). It reads `location.hash` once,
 * on arrival — a later poll must not yank the page back to the anchor while the Operator is
 * reading somewhere else.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import type { components } from '../api/schema';
import FailedFetch from '../components/FailedFetch';
import ArtifactsPanel from '../components/run/ArtifactsPanel';
import Banner from '../components/run/Banner';
import CancelModal from '../components/run/CancelModal';
import CommandBlock from '../components/run/CommandBlock';
import CostBlock from '../components/run/CostBlock';
import DiagramSection from '../components/run/DiagramSection';
import GateRecord from '../components/run/GateRecord';
import Header from '../components/run/Header';
import StepsTable from '../components/run/StepsTable';
import StopBody from '../components/run/StopBody';
import StoriesStrip from '../components/run/StoriesStrip';
import { acceptBody } from '../lib/run/accept';
import { answerBody } from '../lib/run/answer';
import { budgetRaiseBody } from '../lib/run/budget';
import { isFile } from '../lib/run/artifacts';
import { anchoredSeq, PROMOTED_MS, stepAnchorId } from '../lib/run/anchor';
import { isSpecCheckpoint, plannedFilePath } from '../lib/run/checkpoint';
import { detailRequestPath, runToken, stopKind, type RunDetailOut } from '../lib/run/detail';
import { signalBody, signalsRequestPath, type SignalIn, type SignalKind } from '../lib/run/signals';
import { terminalBlock, TERMINAL_RELEASE, TERMINAL_START } from '../lib/run/terminal';
import { $poll, configurePolling, stopPolling } from '../stores/poll';
import { startTracking, stopTracking } from '../stores/activity';
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
  const [anchored, setAnchored] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<'gate' | 'steps' | 'session'>('gate');
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);
  /** One-shot guard: sets the active tab once on the first detail load. */
  const tabDefaultSetRef = useRef(false);
  // 8-3: on the first navigation fetch, append `?opened=true` so `open_run` records the
  // visit server-side before `build_detail` runs — the response's `last_opened_at` then
  // reflects the just-updated timestamp, and the files fetch sees the freshly committed
  // `last_opened_before` for changed-marks computation.
  const openedRef = useRef(false);

  async function fetchDetail(): Promise<void> {
    const seq = ++requestSeqRef.current;
    const opened = !openedRef.current;
    if (opened) openedRef.current = true;
    try {
      const { data, error, response } = await api.GET('/runs/{run_id}/detail', {
        params: { path: { run_id: runId }, query: opened ? { opened: true } : undefined },
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
    openedRef.current = false; // reset so ?opened=true fires again on navigation to a new Run
    void fetchDetail();
    return () => stopPolling();
    // fires once on mount; every later fetch is driven by the `$poll` effect below
  }, [runId]);

  // Activity tracking (8.2): count focused seconds while the Operator has this view open.
  useEffect(() => {
    startTracking(runId);
    return () => stopTracking();
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

  // The `#step-{seq}` arrival (7.5). `arrived` guards the one-shot: the effect depends on
  // `detail` because the row it scrolls to only exists once the first one has rendered, and
  // without the guard every poll would re-scroll the page.
  //
  // It opens STEPS as well as promoting the row, because since story 1-4 the table is one tab
  // of three and `activeTab` starts on GATE: the row this arrival exists to show is not
  // mounted, so the `getElementById` below found nothing and a HISTORY row's `#step-{seq}`
  // link landed on the gate record with no sign of the step it named (FR-25's own link rule).
  // The scroll is a second effect for the same reason — the row exists only after the tab
  // this one opens has rendered.
  const arrivedRef = useRef(false);
  useEffect(() => {
    if (!detail || arrivedRef.current) return;
    arrivedRef.current = true;
    const seq = anchoredSeq(window.location.hash);
    if (seq === null) return;
    setAnchored(seq);
    setActiveTab('steps');
    const clear = window.setTimeout(() => setAnchored(null), PROMOTED_MS);
    return () => window.clearTimeout(clear);
  }, [detail]);

  useEffect(() => {
    if (anchored === null || activeTab !== 'steps') return;
    document.getElementById(stepAnchorId(anchored))?.scrollIntoView({ block: 'center' });
  }, [anchored, activeTab]);

  // SESSION tab default (story 1-4): set once on the first detail load when terminal is present.
  // The `tabDefaultSetRef` guard prevents subsequent polls from resetting the operator's choice.
  // A `#step-{seq}` arrival wins over it: the Operator followed a link to one row, and this
  // effect runs after the one above, so without the guard it would take the tab straight back.
  useEffect(() => {
    if (!detail) return;
    if (tabDefaultSetRef.current) return;
    tabDefaultSetRef.current = true;
    if (anchoredSeq(window.location.hash) !== null) return;
    if (terminalBlock(detail) !== null) {
      setActiveTab('session');
    }
  }, [detail]);

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
  const terminal = terminalBlock(detail);

  return (
    <div data-testid="wf-detail">
      <Header detail={detail} token={token} now={Date.now()} view={undefined} />
      <Banner detail={detail} token={token} />
      <div className="wf-top-zone">
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
      </div>
      <div className="wf-diagram-row">
        <div className="wf-diagram-main">
          <DiagramSection runId={runId} detail={detail} />
        </div>
        <div className="wf-summary-col">
          <StoriesStrip stories={detail.stories} />
          <CostBlock detail={detail} />
          <ArtifactsPanel runId={runId} run={detail.run} folder={detail.header.meta.folder} />
        </div>
      </div>
      <div className="wf-tabs">
        <div className="wf-tab-btns">
          <button
            type="button"
            className="wf-tab-btn"
            aria-pressed={activeTab === 'gate'}
            onClick={() => setActiveTab('gate')}
          >
            GATE
          </button>
          <button
            type="button"
            className="wf-tab-btn"
            aria-pressed={activeTab === 'steps'}
            onClick={() => setActiveTab('steps')}
          >
            STEPS
          </button>
          {terminal !== null ? (
            <button
              type="button"
              className="wf-tab-btn"
              aria-pressed={activeTab === 'session'}
              onClick={() => setActiveTab('session')}
            >
              SESSION
            </button>
          ) : null}
        </div>
        <div className="wf-tab-panel">
          {activeTab === 'gate' ? <GateRecord detail={detail} token={token} /> : null}
          {activeTab === 'steps' ? (
            <StepsTable detail={detail} anchoredSeq={anchored} runId={runId} />
          ) : null}
          {activeTab === 'session' && terminal !== null ? (
            <CommandBlock
              terminal={terminal}
              onCopy={() => void sendSignal(TERMINAL_START)}
              onRelease={() => void sendSignal(TERMINAL_RELEASE)}
              canRelease={(detail.admitted_signals as readonly string[]).includes(TERMINAL_RELEASE)}
              disabled={posting !== null}
            />
          ) : null}
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
