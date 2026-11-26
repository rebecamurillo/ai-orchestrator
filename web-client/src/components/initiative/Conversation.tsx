/**
 * The conversation column of the selected step: its turns across rounds, the mechanism lines
 * the API's values call for, and, on the current step parked on `conversation`, the composer.
 * Nothing here closes a step; only the owner's words in the box do.
 */
import { useState } from 'react';

import { forcedLine } from '../../lib/initiative/actions';
import { freshBranchLine } from '../../lib/initiative/reopen';
import {
  agentAttribution,
  answeringLine,
  blockedLine,
  closedLine,
  closingHint,
  conversationHead,
  isReadOnly,
  listedTurns,
  notClosedLine,
  operatorAttribution,
  queuedLines,
  readOnlyTurns,
  roundLine,
  showsComposer,
  yourTurnLine,
} from '../../lib/initiative/conversation';
import type { DetailStep, DetailWorkflow, InitiativeDetail } from '../../lib/initiative/page';
import {
  failedTurnLine,
  gateAgent,
  isMergeConflict,
  mergeYourTurnLine,
  ownersLine,
} from '../../lib/initiative/stops';
import { logHref } from '../../lib/run/session';
import Composer from './Composer';
import DefectsBlock from './DefectsBlock';

interface Props {
  detail: InitiativeDetail;
  workflow: DetailWorkflow;
  step: DetailStep;
  isCurrent: boolean;
  onSelectStep(id: string): void;
}

function Line({
  text,
  signal,
  children,
}: {
  text: string;
  signal?: 'needs-you' | 'failed';
  children?: React.ReactNode;
}) {
  return (
    <p className="ini-sysline" role="status" data-signal={signal}>
      {text}
      {children}
    </p>
  );
}

export default function Conversation({ detail, workflow, step, isCurrent, onSelectStep }: Props) {
  const [showAll, setShowAll] = useState(false);
  const turns = step.turns ?? [];
  const listed = listedTurns(turns);
  const readOnly = isReadOnly(step);
  const shown = readOnly ? readOnlyTurns(listed, showAll) : listed;
  const index = workflow.steps.findIndex((s) => s.id === step.id);
  const closed = closedLine(step, workflow.steps[index + 1] ?? null, detail.slug);
  const running = turns.find((t) => t.status === 'running');
  const yourTurn = mergeYourTurnLine(step, isCurrent) ?? yourTurnLine(detail, step, isCurrent);
  const failedTurn = failedTurnLine(step);
  const owners = ownersLine(detail, step, isCurrent);
  const mergeComposer = isCurrent && isMergeConflict(step) && detail.status !== 'cancelled';
  const notClosed = notClosedLine(step, isCurrent);
  const blocked = blockedLine(detail, step, isCurrent);
  const fresh = freshBranchLine(step, detail.slug);
  const forced = forcedLine(workflow.steps[index - 1] ?? null, step, detail.slug);

  return (
    <>
      <h3 className="ini-section-head" data-testid="ini-conversation-head">
        <span>{conversationHead(step)}</span>
        <span>{roundLine(step, detail)}</span>
      </h3>
      {forced ? <Line text={forced} /> : null}
      {fresh ? <Line text={fresh} /> : null}
      <ol className="ini-turns">
        {shown.map((t) => (
          <li className="ini-turn" key={t.attempt_id} data-testid={`ini-turn-${t.n}`}>
            {t.author === 'operator' ? (
              <p className="ini-turn-eyebrow">{operatorAttribution(t)}</p>
            ) : null}
            {t.author === 'gate' ? (
              <DefectsBlock turn={t} step={step} gateAgent={gateAgent(workflow, step)} />
            ) : (
              <p className="ini-turn-operator">{t.message}</p>
            )}
            {t.reply !== '' ? (
              <>
                {t.author === 'operator' ? (
                  <p className="ini-turn-eyebrow">{agentAttribution(t, step)}</p>
                ) : null}
                <p className="ini-turn-agent">{t.reply}</p>
              </>
            ) : null}
          </li>
        ))}
      </ol>
      {readOnly && listed.length > 3 && !showAll ? (
        <button type="button" onClick={() => setShowAll(true)}>
          show all {listed.length} turns
        </button>
      ) : null}
      {running ? <Line text={answeringLine(running)} /> : null}
      {queuedLines(turns).map((q) => (
        <Line key={q.turn.attempt_id} text={q.text} />
      ))}
      {failedTurn ? (
        <Line text={failedTurn.text} signal="failed">
          <a href={logHref(failedTurn.runId, failedTurn.attemptId)}>log</a>
        </Line>
      ) : null}
      {yourTurn ? <Line text={yourTurn} /> : null}
      {owners ? <Line text={owners} /> : null}
      {closed ? (
        <Line text={closed.text + (closed.next ? ` · ${closed.next} started → ` : '')}>
          {closed.next ? (
            <button type="button" onClick={() => onSelectStep(closed.next as string)}>
              open {closed.next}
            </button>
          ) : null}
        </Line>
      ) : null}
      {notClosed ? <Line text={notClosed} signal="needs-you" /> : null}
      {blocked ? <Line text={blocked} signal="needs-you" /> : null}
      {(showsComposer(detail, step, isCurrent) || mergeComposer) && step.run_id ? (
        <Composer key={step.id} runId={step.run_id} hint={mergeComposer ? '' : closingHint(step)} />
      ) : null}
    </>
  );
}
