import HintControl from '../metrics/HintControl';
import { FIGURES_DIFFER } from '../../lib/run/metrics-glance';

interface Props {
  line: string;
  gate: string;
  /** The catalogue's one-line reason; absent when the catalogue has no entry. */
  reason: string | null;
}

/** Shown when the Run's gateway and harness totals differ at cent precision (EXPERIENCE §4). */
export default function FiguresDifferCard({ line, gate, reason }: Props) {
  return (
    <div className="wf-figures-differ" role="note" data-testid="wf-figures-differ">
      <p className="wf-figures-differ-eyebrow">
        {FIGURES_DIFFER} <HintControl metricId="cost.figure_gap" />
      </p>
      <p>{line}</p>
      <p className="wf-figures-differ-reason">{reason ? `${gate} · ${reason}` : gate}</p>
    </div>
  );
}
