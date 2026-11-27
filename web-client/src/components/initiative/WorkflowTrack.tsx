/** The workflows of an initiative, one after another; a cell selects its workflow. */
import { Fragment } from 'react';

import { tokenSignal } from '../../lib/board/format';
import { workflowEyebrow, workflowMicro, type DetailWorkflow } from '../../lib/initiative/page';

interface Props {
  workflows: DetailWorkflow[];
  currentPosition: number;
  showNow: boolean;
  selected: number | null;
  onSelect: (position: number) => void;
}

export default function WorkflowTrack({
  workflows,
  currentPosition,
  showNow,
  selected,
  onSelect,
}: Props) {
  return (
    <section className="ini-track" data-testid="ini-workflows">
      <p className="ini-section-head">
        <span>WORKFLOWS · ONE AFTER ANOTHER</span>
        <span>{workflows.length} workflows</span>
      </p>
      <div className="ini-track-cells">
        {workflows.map((w, i) => (
          <Fragment key={w.workflow}>
            {i > 0 ? (
              <span className="ini-track-sep" aria-hidden="true">
                ▸
              </span>
            ) : null}
            <button
              type="button"
              className="ini-wcell"
              data-testid={`ini-workflow-${w.workflow}`}
              aria-pressed={selected === w.position}
              data-selected={selected === w.position ? 'true' : undefined}
              data-left-rule={w.token === 'BLK' ? 'needs-you' : undefined}
              onClick={() => onSelect(w.position)}
            >
              <span className="ini-wcell-eyebrow">
                {workflowEyebrow(w)}
                {showNow && w.position === currentPosition ? (
                  <span className="ini-now"> NOW</span>
                ) : null}
              </span>
              <span className="ini-wcell-name">{w.workflow}</span>
              <span className="ini-wcell-micro">{workflowMicro(w)}</span>
              {w.token ? (
                <span className="ini-card-token" data-signal={tokenSignal(w.token)}>
                  <span className="ini-card-chip" />
                  {w.token}
                </span>
              ) : null}
              <span
                className="ini-wcell-line"
                data-signal={w.token === 'BLK' ? 'needs-you' : undefined}
              >
                {w.line}
              </span>
            </button>
          </Fragment>
        ))}
      </div>
    </section>
  );
}
