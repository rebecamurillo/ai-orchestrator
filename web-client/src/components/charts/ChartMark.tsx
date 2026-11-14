/** One chart mark: a focusable button with the table's text as its name, or a bare word. */
import type { KeyboardEvent } from 'react';

import type { components } from '../../api/schema';
import { FONT, HATCH, type Mark } from '../../lib/charts/layout';
import { formatValue, stateWords } from '../../lib/metrics/format';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import { openOrigin } from '../../stores/metric-ui';

type MetricValueOut = components['schemas']['MetricValueOut'];

export const INK = 'var(--color-chart-ink)';
export const seriesColour = (n: 1 | 2): string => `var(--color-chart-data-${n})`;

/** The ValueCell text of a value: its figure, or its missing word. */
export function valueText(value: MetricValueOut): string {
  return value.value_num === null
    ? (value.missing ?? '')
    : formatValue(value.value_num, value.unit);
}

export function markParts(
  value: MetricValueOut,
  ctx: TargetContext,
  rowLabel: string,
  seriesLabel: string | null,
): string[] {
  return [
    ctx.runLabel,
    rowLabel,
    ...(seriesLabel === null ? [] : [seriesLabel]),
    valueText(value),
    ...stateWords(value, ctx.subscription),
  ];
}

interface Props {
  x: number;
  y: number;
  height: number;
  mark: Mark;
  series: 1 | 2;
  value: MetricValueOut;
  ctx: TargetContext;
  rowLabel: string;
  seriesLabel: string | null;
  /** Width in px of the hatched share at the end of the bar. */
  share?: number;
  /** The whole bar hatched, outlined 1 px in its series colour. */
  hatched?: boolean;
  /** The Run is followed: an accent outline around the mark (never exported). */
  outlined?: boolean;
  /** Another method than the first Run's: the dot texture. */
  dotted?: boolean;
  onTip: (text: string | null) => void;
}

export default function ChartMark(props: Props) {
  const { x, y, height, mark, series, value, ctx, rowLabel, seriesLabel, onTip } = props;
  const colour = seriesColour(series);
  const mid = y + height / 2 + 4;
  if (mark.kind === 'missing') {
    return (
      <text x={x + 4} y={mid} fill={INK} fontSize={FONT}>
        {mark.word}
      </text>
    );
  }
  const parts = markParts(value, ctx, rowLabel, seriesLabel);
  const open = () => openOrigin(targetFor(value, ctx));
  const onKeyDown = (event: KeyboardEvent) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    open();
  };
  const share = props.share ?? 0;
  const solid = Math.max(0, mark.width - share);
  return (
    <g
      role="button"
      tabIndex={0}
      aria-label={parts.join(' ')}
      onFocus={() => onTip(parts.join(' · '))}
      onBlur={() => onTip(null)}
      onMouseEnter={() => onTip(parts.join(' · '))}
      onMouseLeave={() => onTip(null)}
      onClick={open}
      onKeyDown={onKeyDown}
    >
      {mark.kind === 'partial' ? (
        <rect
          x={x}
          y={y}
          width={mark.width}
          height={height}
          fill="none"
          stroke={colour}
          strokeWidth={1}
        />
      ) : props.dotted ? (
        <rect
          x={x}
          y={y}
          width={mark.width}
          height={height}
          fill="url(#dots-1)"
          stroke={colour}
          strokeWidth={1}
        />
      ) : props.hatched ? (
        <rect
          x={x}
          y={y}
          width={mark.width}
          height={height}
          fill={`url(#hatch-${series})`}
          stroke={colour}
          strokeWidth={1}
        />
      ) : (
        <>
          <rect x={x} y={y} width={share > 0 ? solid : mark.width} height={height} fill={colour} />
          {share > 0 ? (
            <rect
              x={x + solid}
              y={y}
              width={share}
              height={height}
              fill={`url(#hatch-${series})`}
            />
          ) : null}
        </>
      )}
      {props.outlined ? (
        <rect
          data-follow="1"
          x={x - 1}
          y={y - 1}
          width={mark.width + 2}
          height={height + 2}
          fill="none"
          stroke="var(--color-accent)"
          strokeWidth={1}
        />
      ) : null}
      <text x={x + mark.width + 6} y={mid} fill={INK} fontSize={FONT}>
        {mark.label}
      </text>
    </g>
  );
}

/** The hatch and dot patterns the marks reference (45°, 2.4 px lines on transparent). */
export function Patterns() {
  const period = HATCH.line * 2;
  return (
    <defs>
      {([1, 2] as const).map((n) => (
        <pattern
          key={n}
          id={`hatch-${n}`}
          patternUnits="userSpaceOnUse"
          width={period}
          height={period}
          patternTransform={`rotate(${HATCH.angle})`}
        >
          <line
            x1={0}
            y1={0}
            x2={0}
            y2={period}
            stroke={seriesColour(n)}
            strokeWidth={HATCH.line}
          />
        </pattern>
      ))}
      <pattern id="dots-1" patternUnits="userSpaceOnUse" width={5} height={5}>
        <circle cx={2.5} cy={2.5} r={1} fill={seriesColour(1)} />
      </pattern>
    </defs>
  );
}
