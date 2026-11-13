/** The chart container: head, SVG with axis, gridlines and row labels, and the one tooltip. */
import type { ReactNode } from 'react';

import {
  CHART_WIDTH,
  FONT,
  GRID_OPACITY,
  GUTTER,
  scale,
  tickLabel,
  wrapLabel,
  type Ticks,
} from '../../lib/charts/layout';
import { INK, Patterns } from './ChartMark';
import './charts.css';

export interface FrameRow {
  id: string;
  label: string;
  top: number;
  height: number;
}

interface Props {
  title: string;
  keyText: string;
  ticks: Ticks;
  unit: string;
  rows: FrameRow[];
  height: number;
  tip: string | null;
  children: ReactNode;
}

const AXIS = 22;

export default function ChartFrame({
  title,
  keyText,
  ticks,
  unit,
  rows,
  height,
  tip,
  children,
}: Props) {
  const maxTick = ticks.ticks[ticks.ticks.length - 1];
  const total = height + AXIS;
  return (
    <div className="chart-panel" role="figure" aria-label={title}>
      <h4 className="chart-head">
        <span className="chart-title">{title}</span>
        <span className="chart-key">{keyText}</span>
      </h4>
      <svg width="100%" viewBox={`0 0 ${CHART_WIDTH} ${total}`} fontSize={FONT}>
        <Patterns />
        {ticks.ticks.map((t) => {
          const x = GUTTER + scale(t, maxTick);
          return (
            <g key={t}>
              <line
                x1={x}
                x2={x}
                y1={0}
                y2={height}
                stroke={INK}
                strokeOpacity={GRID_OPACITY}
                strokeWidth={1}
              />
              <text x={x} y={height + 14} textAnchor="middle" fill={INK} fontSize={FONT}>
                {tickLabel(t, ticks.step, unit)}
              </text>
            </g>
          );
        })}
        {rows.map((row) => {
          const lines = wrapLabel(row.label);
          const first = row.top + row.height / 2 - ((lines.length - 1) * 14) / 2 + 4;
          return (
            <text key={row.id} x={GUTTER - 8} textAnchor="end" fill={INK} fontSize={FONT}>
              {lines.map((line, i) => (
                <tspan key={i} x={GUTTER - 8} y={first + i * 14}>
                  {line}
                </tspan>
              ))}
            </text>
          );
        })}
        {children}
      </svg>
      {tip !== null ? (
        <div role="tooltip" className="chart-tooltip">
          {tip}
        </div>
      ) : null}
    </div>
  );
}
