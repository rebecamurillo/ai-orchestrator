import { LIST_PRICE_WORDS, NOT_AVAILABLE_WORD } from '../../lib/metrics/format';
import type { OriginTarget } from '../../stores/metric-ui';
import '../../styles/metrics.css';
import HintControl from './HintControl';
import MissingWord from './MissingWord';
import ValueCell from './ValueCell';

interface Props {
  gateway: OriginTarget | null;
  harness: OriginTarget | null;
  subscription: boolean;
  gatewayMetricId: string;
  harnessMetricId: string;
}

/** The two cost figures side by side, gateway first (EXPERIENCE §5.5). */
export default function FigurePair({
  gateway,
  harness,
  subscription,
  gatewayMetricId,
  harnessMetricId,
}: Props) {
  return (
    <div className="metric-figure-pair">
      <div className="metric-figure-head">
        GATEWAY <HintControl metricId={gatewayMetricId} />
      </div>
      <div className="metric-figure-head">
        HARNESS <HintControl metricId={harnessMetricId} />
      </div>
      {subscription && <p className="metric-figure-note">{LIST_PRICE_WORDS}</p>}
      {gateway ? <ValueCell target={gateway} /> : <MissingWord word={NOT_AVAILABLE_WORD} />}
      {harness ? <ValueCell target={harness} /> : <MissingWord word={NOT_AVAILABLE_WORD} />}
    </div>
  );
}
