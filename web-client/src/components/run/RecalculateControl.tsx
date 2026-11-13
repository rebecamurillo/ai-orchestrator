import type { components } from '../../api/schema';
import {
  calcLine,
  isEnded,
  RECALCULATE_LABEL,
  recalcConfirmLine,
} from '../../lib/run/metrics-glance';
import { KEEP_LABEL } from '../../lib/run/skip';
import ConfirmAction from './ConfirmAction';

type ProblemDetail = components['schemas']['ProblemDetail'];
type CalculationOut = components['schemas']['CalculationOut'];
type ResultVersionOut = components['schemas']['ResultVersionOut'];

interface Props {
  status: string;
  versions: ResultVersionOut[];
  calc: CalculationOut | null;
  calcError: ProblemDetail | null;
  onConfirm: () => void;
}

/** Recalculate an ended Run's metrics; the running calculation replaces the button. */
export default function RecalculateControl({
  status,
  versions,
  calc,
  calcError,
  onConfirm,
}: Props) {
  if (!isEnded(status)) return null;
  const line = calcLine(calc);
  const running = calc !== null && calc.state !== 'failed';
  return (
    <span className="wf-recalculate">
      {line ? (
        <span className="wf-calc-line" data-testid="wf-calc-line">
          {line}
        </span>
      ) : null}
      {calc?.state === 'failed' ? (
        <div className="wf-command">
          <pre className="wf-command-code" data-testid="wf-calc-output">
            {calc.output}
          </pre>
        </div>
      ) : null}
      {running ? null : (
        <ConfirmAction
          kind="recalculate"
          label={RECALCULATE_LABEL}
          line={recalcConfirmLine(versions)}
          confirmLabel={RECALCULATE_LABEL}
          keepLabel={KEEP_LABEL}
          disabled={false}
          onConfirm={onConfirm}
        />
      )}
      {calcError ? (
        <span className="wf-signal-error">{calcError.detail ?? calcError.title}</span>
      ) : null}
    </span>
  );
}
