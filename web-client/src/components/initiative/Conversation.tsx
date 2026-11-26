/**
 * The conversation column of the selected step: its turns across rounds, the mechanism lines
 * the API's values call for, and, on the current step parked on `conversation`, the composer.
 * Nothing here closes a step; only the owner's words in the box do.
 */
import { useState } from 'react';

import { forcedLine } from '../../lib/initiative/actions';
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
import Composer from './Composer';

interface Props {
  detail: InitiativeDetail;
  workflow: DetailWorkflow;
  step: DetailStep;
  isCurrent: boolean;
  onSelectStep(id: string): void;
}

function Line({
  text,
  amber = false,
  children,
}: {
  text: string;
  amber?: boolean;
  children?: React.ReactNode;
}) {
  return (
    <p className="ini-sysline" role="status" data-signal={amber ? 'needs-you' : undefined}>
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
  const yourTurn = yourTurnLine(detail, step, isCurrent);
  const notClosed = notClosedLine(step, isCurrent);
  const blocked = blockedLine(detail, step, isCurrent);
  const forced = forcedLine(workflow.steps[index - 1] ?? null, step, detail.slug);

  return (
    <>
      <h3 className="ini-section-head" data-testid="ini-conversation-head">
        <span>{conversationHead(step)}</span>
        <span>{roundLine(step, detail)}</span>
      </h3>
      {forced ? <Line text={forced} /> : null}
      <ol className="ini-turns">
        {shown.map((t) => (
          <li className="ini-turn" key={t.attempt_id} data-testid={`ini-turn-${t.n}`}>
            {t.author === 'operator' ? (
              <p className="ini-turn-eyebrow">{operatorAttribution(t)}</p>
            ) : null}
            <p className="ini-turn-operator">{t.message}</p>
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
      {yourTurn ? <Line text={yourTurn} /> : null}
      {closed ? (
        <Line text={closed.text + (closed.next ? ` · ${closed.next} started → ` : '')}>
          {closed.next ? (
            <button type="button" onClick={() => onSelectStep(closed.next as string)}>
              open {closed.next}
            </button>
          ) : null}
        </Line>
      ) : null}
      {notClosed ? <Line text={notClosed} amber /> : null}
      {blocked ? <Line text={blocked} amber /> : null}
      {showsComposer(detail, step, isCurrent) && step.run_id ? (
        <Composer key={step.id} runId={step.run_id} hint={closingHint(step)} />
      ) : null}
    </>
  );
}
