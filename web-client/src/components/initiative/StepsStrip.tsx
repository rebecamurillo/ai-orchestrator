/** The steps of the selected interactive workflow, in order; a cell selects its step. */
import { tokenSignal } from '../../lib/board/format';
import { stepAnnounce, stepEyebrow, type DetailWorkflow } from '../../lib/initiative/page';

interface Props {
  workflow: DetailWorkflow;
  currentStepId: string | null;
  selectedStepId: string | null;
  onSelect: (stepId: string) => void;
  forceStepId: string | null;
  onForce: (stepId: string) => void;
}

export default function StepsStrip({
  workflow,
  currentStepId,
  selectedStepId,
  onSelect,
  forceStepId,
  onForce,
}: Props) {
  return (
    <section className="ini-strip" data-testid="ini-steps">
      <p className="ini-section-head">
        <span>STEPS OF {workflow.workflow.toUpperCase()}</span>
        <span>{workflow.steps.length} steps</span>
      </p>
      <ol className="ini-strip-list">
        {workflow.steps.map((s, i) => {
          const current = s.id === currentStepId;
          return (
            <li key={s.id} className="ini-scell-item">
              <button
                type="button"
                className="ini-scell"
                data-testid={`ini-step-${s.id}`}
                aria-label={stepAnnounce(i + 1, s)}
                aria-current={current ? 'step' : undefined}
                data-selected={selectedStepId === s.id ? 'true' : undefined}
                data-left-rule={s.token === 'BLK' ? 'needs-you' : undefined}
                onClick={() => onSelect(s.id)}
              >
                <span className="ini-scell-eyebrow">
                  {stepEyebrow(workflow.position, i + 1, s.kind)}
                  {current ? <span className="ini-now"> NOW</span> : null}
                </span>
                <span className="ini-scell-name">{s.token === 'SKP' ? <s>{s.id}</s> : s.id}</span>
                {s.agent ? <span className="ini-scell-agent">{s.agent}</span> : null}
                <span className="ini-card-token" data-signal={tokenSignal(s.token)}>
                  <span className="ini-card-chip" />
                  {s.token}
                </span>
                <span
                  className="ini-scell-line"
                  data-signal={s.token === 'BLK' ? 'needs-you' : undefined}
                  data-to-come={s.token === 'QUE' ? 'true' : undefined}
                >
                  {s.line}
                </span>
              </button>
              {s.id === forceStepId ? (
                <button
                  type="button"
                  className="ini-scell-action"
                  data-testid={`ini-force-${s.id}`}
                  onClick={() => onForce(s.id)}
                >
                  Start now
                </button>
              ) : null}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
