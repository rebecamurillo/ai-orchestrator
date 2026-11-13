/** Where the time went: machine time solid, waiting on you hatched, on one duration axis. */
import type { ChartRow } from '../../lib/charts/run-charts';
import type { TargetContext } from '../../lib/run/metrics-glance';
import BarChart from './BarChart';

interface Props {
  title: string;
  keyText: string;
  rows: ChartRow[];
  ctx: TargetContext;
}

export default function TimeStrip({ title, keyText, rows, ctx }: Props) {
  return (
    <BarChart
      title={title}
      keyText={keyText}
      rows={rows}
      unit="seconds"
      ctx={ctx}
      seriesLabel={null}
      ticksIn="seconds"
    />
  );
}
