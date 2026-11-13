/** Gateway above harness per row, one shared axis; a word takes the slot of a figure it replaces. */
import { useState } from 'react';

import {
  GUTTER,
  PAIR_BAR,
  PAIR_GAP,
  layoutRows,
  markFor,
  niceTicks,
  rowHeight,
  scale,
  wrapLabel,
} from '../../lib/charts/layout';
import type { PairRow } from '../../lib/charts/run-charts';
import type { TargetContext } from '../../lib/run/metrics-glance';
import ChartFrame from './ChartFrame';
import ChartMark, { INK } from './ChartMark';

interface Props {
  title: string;
  keyText: string;
  rows: PairRow[];
  unit: string;
  ctx: TargetContext;
  labels: { gateway: string; harness: string };
}

export default function PairedBarChart({ title, keyText, rows, unit, ctx, labels }: Props) {
  const [tip, setTip] = useState<string | null>(null);
  const nums = rows.flatMap((r) =>
    [r.gateway, r.harness].flatMap((v) => (v?.value_num == null ? [] : [Number(v.value_num)])),
  );
  const ticks = niceTicks(Math.max(0, ...nums));
  const maxTick = ticks.ticks[ticks.ticks.length - 1];
  const heights = rows.map((r) => rowHeight('pair', wrapLabel(r.label).length));
  const { tops, total } = layoutRows(heights);
  const span = 2 * PAIR_BAR + PAIR_GAP;
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
        const y0 = tops[i] + (heights[i] - span) / 2;
        const shareOf = (v: PairRow['gatewayShare']): number =>
          v?.value_num == null ? 0 : scale(Number(v.value_num), maxTick);
        return (
          <g key={row.id}>
            {row.gatewayWord !== undefined ? (
              <text x={GUTTER + 4} y={y0 + PAIR_BAR} fill={INK} fontSize={12}>
                {row.gatewayWord}
              </text>
            ) : row.gateway ? (
              <ChartMark
                x={GUTTER}
                y={y0}
                height={PAIR_BAR}
                mark={markFor(row.gateway, maxTick)}
                series={1}
                share={shareOf(row.gatewayShare)}
                value={row.gateway}
                ctx={ctx}
                rowLabel={row.label}
                seriesLabel={labels.gateway}
                onTip={setTip}
              />
            ) : null}
            {row.harness ? (
              <ChartMark
                x={GUTTER}
                y={y0 + PAIR_BAR + PAIR_GAP}
                height={PAIR_BAR}
                mark={markFor(row.harness, maxTick)}
                series={2}
                share={shareOf(row.harnessShare)}
                value={row.harness}
                ctx={ctx}
                rowLabel={row.label}
                seriesLabel={labels.harness}
                onTip={setTip}
              />
            ) : null}
          </g>
        );
      })}
    </ChartFrame>
  );
}
