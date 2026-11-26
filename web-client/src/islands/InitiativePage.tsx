/**
 * The Initiative page island (story 11.1): header, workflow track, steps strip and the main
 * column of the selected workflow, all from `GET /initiatives/{id}`. Only the load sends
 * `opened=true`, which records the owner's view. The selection is set once from the first
 * answer; a poll never re-derives it. `requestSeqRef` and the mounted-tick skip are
 * `Initiatives.tsx`'s staleness guard.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import { api } from '../api/client';
import FailedFetch from '../components/FailedFetch';
import AutoWorkflowSummary from '../components/initiative/AutoWorkflowSummary';
import Conversation from '../components/initiative/Conversation';
import FilesByStep from '../components/initiative/FilesByStep';
import InitiativeHeader from '../components/initiative/InitiativeHeader';
import SessionsAndRuns from '../components/initiative/SessionsAndRuns';
import StepsStrip from '../components/initiative/StepsStrip';
import WorkflowTrack from '../components/initiative/WorkflowTrack';
import {
  defaultSelection,
  isInteractive,
  pollFast,
  previousWorkflowName,
  showNow,
  type InitiativeDetail,
  type Selection,
} from '../lib/initiative/page';
import { logHref } from '../lib/run/session';
import { $poll, configurePolling, forceTick, stopPolling } from '../stores/poll';
import '../styles/initiatives.css';
import '../styles/initiative.css';

interface Props {
  initiativeId: string;
  initialWorkflow: number | null;
}

type Phase = { kind: 'loading' } | { kind: 'ready' } | { kind: 'error'; status: number | null };

export default function InitiativePage({ initiativeId, initialWorkflow }: Props) {
  const [phase, setPhase] = useState<Phase>({ kind: 'loading' });
  const [detail, setDetail] = useState<InitiativeDetail | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const pollTick = useStore($poll);
  const requestSeqRef = useRef(0);
  const mountedTickRef = useRef(pollTick);
  // A Retry after a failed load must still record the view, so `opened` rides until one answer lands.
  const loadedRef = useRef(false);

  async function fetchDetail(opened: boolean): Promise<void> {
    const seq = ++requestSeqRef.current;
    try {
      const {
        data: out,
        error,
        response,
      } = await api.GET('/initiatives/{initiative_id}', {
        params: {
          path: { initiative_id: initiativeId },
          ...(opened ? { query: { opened: true } } : {}),
        },
      });
      if (seq !== requestSeqRef.current) return;
      if (error || !out) {
        stopPolling();
        setPhase({ kind: 'error', status: response.status });
        return;
      }
      loadedRef.current = true;
      setDetail(out);
      setSelection((current) => current ?? defaultSelection(out, initialWorkflow));
      setPhase({ kind: 'ready' });
      configurePolling(pollFast(out));
    } catch {
      if (seq !== requestSeqRef.current) return;
      stopPolling();
      setPhase({ kind: 'error', status: null });
    }
  }

  useEffect(() => {
    void fetchDetail(true);
    return () => stopPolling();
    // fires once on mount; later fetches come from the `$poll` effect
  }, []);

  useEffect(() => {
    if (pollTick === mountedTickRef.current) return;
    void fetchDetail(!loadedRef.current);
  }, [pollTick]);

  if (phase.kind === 'error') {
    return (
      <FailedFetch
        method="GET"
        path={`/api/initiatives/${initiativeId}`}
        status={phase.status}
        onRetry={forceTick}
      />
    );
  }
  if (!detail || !selection) return null;

  const workflow = detail.workflows.find((w) => w.position === selection.position);
  const isCurrent = selection.position === detail.current_position;
  const step = workflow?.steps.find((s) => s.id === selection.stepId) ?? null;
  const lastTurn = step && step.kind === 'automatic' ? (step.turns.at(-1) ?? null) : null;

  function selectWorkflow(position: number): void {
    const target = detail?.workflows.find((w) => w.position === position);
    const stepId =
      position === detail?.current_position &&
      target?.steps.some((s) => s.id === detail.current_step)
        ? detail.current_step
        : null;
    setSelection({ position, stepId });
  }

  return (
    <div className="ini-page" data-testid="initiative-page">
      <InitiativeHeader detail={detail} />
      <WorkflowTrack
        workflows={detail.workflows}
        currentPosition={detail.current_position}
        showNow={showNow(detail.status)}
        selected={selection.position}
        onSelect={selectWorkflow}
      />
      {workflow && isInteractive(workflow) ? (
        <StepsStrip
          workflow={workflow}
          currentStepId={isCurrent ? detail.current_step : null}
          selectedStepId={selection.stepId}
          onSelect={(stepId) => setSelection({ position: selection.position, stepId })}
        />
      ) : null}
      <div className="ini-body">
        <main className="ini-main">
          {workflow && !isInteractive(workflow) ? (
            <AutoWorkflowSummary
              workflow={workflow}
              previous={previousWorkflowName(detail.workflows, workflow.position)}
              projectId={detail.project?.id ?? detail.project_id}
            />
          ) : step && step.kind === 'automatic' ? (
            <section className="ini-auto-step" data-testid="ini-auto-step">
              <p>{step.line}</p>
              {lastTurn ? (
                <a data-testid="ini-step-log" href={logHref(lastTurn.run_id, lastTurn.attempt_id)}>
                  log
                </a>
              ) : null}
            </section>
          ) : (
            <section className="ini-conversation" data-testid="ini-conversation">
              {step && step.kind === 'conversation' && workflow ? (
                <Conversation
                  key={step.id}
                  detail={detail}
                  workflow={workflow}
                  step={step}
                  isCurrent={isCurrent && step.id === detail.current_step}
                  onSelectStep={(id) => setSelection({ position: selection.position, stepId: id })}
                />
              ) : null}
            </section>
          )}
        </main>
        <aside className="ini-side">
          <FilesByStep detail={detail} selection={selection} />
          <SessionsAndRuns sessions={detail.sessions ?? []} />
        </aside>
      </div>
    </div>
  );
}
