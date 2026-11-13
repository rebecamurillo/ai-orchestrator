/** One bar per row on a single axis from zero; a missing value is a word in its row, not a bar. */
import { useState } from 'react';

import {
  BAR,
  GUTTER,
  layoutRows,
  markFor,
  niceTicks,
  rowHeight,
  secondsTicks,
  wrapLabel,
} from '../../lib/charts/layout';
import type { ChartRow } from '../../lib/charts/run-charts';
import type { TargetContext } from '../../lib/run/metrics-glance';
import ChartFrame from './ChartFrame';
import ChartMark from './ChartMark';

interface Props {
  title: string;
  keyText: string;
  rows: ChartRow[];
  unit: string;
  ctx: TargetContext;
  /** Named in each mark's name and tooltip; null where the row label already says it. */
  seriesLabel: string | null;
  /** Duration axis: ticks on whole minutes so each tick label differs. */
  ticksIn?: 'seconds';
}

export default function BarChart({ title, keyText, rows, unit, ctx, seriesLabel, ticksIn }: Props) {
  const [tip, setTip] = useState<string | null>(null);
  const nums = rows.flatMap((r) => (r.value?.value_num == null ? [] : [Number(r.value.value_num)]));
  const max = Math.max(0, ...nums);
  const ticks = ticksIn === 'seconds' ? secondsTicks(max) : niceTicks(max);
  const maxTick = ticks.ticks[ticks.ticks.length - 1];
  const heights = rows.map((r) => rowHeight('single', wrapLabel(r.label).length));
  const { tops, total } = layoutRows(heights);
  return (
    <ChartFrame
      title={title}
      keyText={keyText}
      ticks={ticks}
      unit={unit}
      height={total}
      tip={tip}
      rows={rows.map((r, i) => ({ id: r.id, label: r.label, top: tops[i], height: heights[i] }))}
    >
      {rows.map((row, i) => {
        if (row.value === null) return null;
        const y = tops[i] + (heights[i] - BAR) / 2;
        return (
          <ChartMark
            key={row.id}
            x={GUTTER}
            y={y}
            height={BAR}
            mark={markFor(row.value, maxTick)}
            series={row.texture === 'hatch' ? 2 : 1}
            hatched={row.texture === 'hatch'}
            value={row.value}
            ctx={ctx}
            rowLabel={row.label}
            seriesLabel={seriesLabel}
            onTip={setTip}
          />
        );
      })}
    </ChartFrame>
  );
}
