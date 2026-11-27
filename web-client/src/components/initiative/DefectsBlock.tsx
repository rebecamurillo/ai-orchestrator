/** A gate turn: the defects the gate found, as the question-block pattern. Text only, never HTML. */
import { defectsEyebrow, gateAttribution } from '../../lib/initiative/stops';
import type { Turn } from '../../lib/initiative/conversation';
import type { DetailStep } from '../../lib/initiative/page';

interface Props {
  turn: Turn;
  step: DetailStep;
  gateAgent: string | null;
}

export default function DefectsBlock({ turn, step, gateAgent }: Props) {
  return (
    <>
      <p className="ini-turn-eyebrow">{gateAttribution(turn, gateAgent)}</p>
      <div className="ini-defects">
        <p className="ini-defects-eyebrow">{defectsEyebrow(turn, step)}</p>
        <p className="ini-defects-text">{turn.message}</p>
      </div>
    </>
  );
}
