/** One comparison chart on screen: the model `compare-charts.ts` built, drawn from zero (or a range). */
import { useState, type KeyboardEvent } from 'react';

import type { components } from '../../api/schema';
import type { CompareChart, CompareRow } from '../../lib/charts/compare-charts';
import {
  chartTicks,
  compareSvg,
  dotWords,
  drawn,
  markWord,
  type CompareExportMeta,
} from '../../lib/charts/compare-png';
import { SCROLL_RUNS, keyEntries, sharedWords } from '../../lib/charts/compare-runs';
import { svgDataUrl } from '../../lib/charts/export';
import {
  CHART_WIDTH,
  FONT,
  GRID_OPACITY,
  GUTTER,
  PAIR_BAR,
  PAIR_GAP,
  VALUE_SPACE,
  layoutRows,
  rowHeight,
  scale,
  tickLabel,
} from '../../lib/charts/layout';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import { openOrigin } from '../../stores/metric-ui';
import ChartMark, { INK, Patterns, markParts } from './ChartMark';
import type { Preview } from './ChartSwitch';
import './charts.css';

type CompareRunHeaderOut = components['schemas']['CompareRunHeaderOut'];

interface Props {
  chart: CompareChart;
  headers: CompareRunHeaderOut[];
  followed: string | null;
  onFollow: (runId: string) => void;
  onPng: (chart: CompareChart) => void;
  preview: Preview;
  meta: CompareExportMeta;
}

const PLOT = CHART_WIDTH - GUTTER - VALUE_SPACE;
const AXIS = 22;
const HEAD = 20;
const DOT = 5;

const ctxOf = (h: CompareRunHeaderOut): TargetContext => ({
  runLabel: h.label,
  versions: [],
  selected: h.selected_version,
  latest: h.selected_version,
  items: [],
  subscription: h.subscription === true,
});

export default function CompareChartPanel(props: Props) {
  const { chart, headers, followed, onFollow, onPng, preview, meta } = props;
  const [tip, setTip] = useState<string | null>(null);
  const label = (id: string): string => meta.entries[id]?.label ?? id;
  const broken = chart.groups[0]?.name != null;
  const shared = sharedWords(headers.map((h) => h.label)).join(' ');
  const items: { head?: string; row?: CompareRow; h: number }[] = [];
  for (const g of chart.groups) {
    if (g.name !== null) items.push({ head: g.name, h: HEAD });
    for (const row of g.rows) {
      items.push({ row, h: rowHeight(chart.kind === 'pair' ? 'pair' : 'single', row.name.length) });
    }
  }
  const { tops, total } = layoutRows(items.map((i) => i.h));
  const ticks = chartTicks(chart);
  const maxTick = ticks.ticks[ticks.ticks.length - 1];
  const span = maxTick - ticks.origin;
  const px = (t: number): number => GUTTER + scale(t - ticks.origin, span, PLOT);
  const toggle = (event: KeyboardEvent, runId: string): void => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    onFollow(runId);
  };
  const header = (runId: string): CompareRunHeaderOut =>
    headers.find((h) => h.run_id === runId) as CompareRunHeaderOut;

  const rowMarks = (row: CompareRow, top: number, height: number) => {
    const h = header(row.runId);
    const ctx = ctxOf(h);
    const on = followed === row.runId;
    const pair = chart.kind === 'pair';
    const span2 = 2 * PAIR_BAR + PAIR_GAP;
    if (chart.kind === 'dot') {
      const [g, hv] = row.marks;
      if (g?.value == null || hv?.value == null) {
        return (
          <text x={GUTTER + 4} y={top + height / 2 + 4} fill={INK} fontSize={FONT}>
            {dotWords(g, hv)}
          </text>
        );
      }
      const xg = px(Number(g.value.value_num));
      const xh = px(Number(hv.value.value_num));
      const mid = top + height / 2;
      const parts = markParts(g.value, ctx, row.name[0], label(chart.metricIds[0]));
      const open = () => openOrigin(targetFor(g.value as NonNullable<typeof g.value>, ctx));
      return (
        <g
          role="button"
          tabIndex={0}
          aria-label={`${parts.join(' ')} · ${markWord(hv)}`}
          onClick={open}
          onKeyDown={(e) => {
            if (e.key !== 'Enter' && e.key !== ' ') return;
            e.preventDefault();
            open();
          }}
          onMouseEnter={() => setTip(parts.join(' · '))}
          onMouseLeave={() => setTip(null)}
        >
          <line x1={xg} x2={xh} y1={mid} y2={mid} stroke={INK} strokeWidth={1} />
          <circle data-series="gateway" cx={xg} cy={mid} r={DOT} fill="var(--color-chart-data-1)" />
          <circle
            data-series="harness"
            cx={xh}
            cy={mid}
            r={DOT}
            fill="none"
            stroke="var(--color-chart-data-2)"
            strokeWidth={1}
          />
          {on ? (
            <rect
              data-follow="1"
              x={Math.min(xg, xh) - DOT - 1}
              y={mid - DOT - 1}
              width={Math.abs(xg - xh) + 2 * DOT + 2}
              height={2 * DOT + 2}
              fill="none"
              stroke="var(--color-accent)"
              strokeWidth={1}
            />
          ) : null}
          <text x={Math.max(xg, xh) + DOT + 6} y={mid + 4} fill={INK} fontSize={FONT}>
            {markWord(g)} · {markWord(hv)}
          </text>
        </g>
      );
    }
    return row.marks.map((m, k) => {
      if (m === undefined) return null;
      const y0 = pair
        ? top + (height - span2) / 2 + k * (PAIR_BAR + PAIR_GAP)
        : top + (height - 12) / 2;
      const bar = pair ? PAIR_BAR : 12;
      const found = drawn(m, maxTick, PLOT);
      if (found === null) return null;
      if (m.word !== undefined || m.value === null) {
        return (
          <text key={k} x={GUTTER + 4} y={y0 + bar} fill={INK} fontSize={FONT}>
            {m.word}
          </text>
        );
      }
      const share =
        m.share?.value_num == null ? 0 : scale(Number(m.share.value_num), maxTick, PLOT);
      return (
        <ChartMark
          key={k}
          x={GUTTER}
          y={y0}
          height={bar}
          mark={found}
          series={k === 1 ? 2 : 1}
          value={m.value}
          ctx={ctx}
          rowLabel={row.name[0]}
          seriesLabel={label(chart.metricIds[k])}
          share={share}
          hatched={pair && k === 1 && chart.second === 'hatch'}
          dotted={m.dotted !== undefined}
          outlined={on}
          onTip={setTip}
        />
      );
    });
  };

  const svg = (
    <svg width="100%" viewBox={`0 0 ${CHART_WIDTH} ${total + AXIS}`} fontSize={FONT}>
      <Patterns />
      {ticks.ticks.map((t) => (
        <g key={t}>
          <line
            x1={px(t)}
            x2={px(t)}
            y1={0}
            y2={total}
            stroke={INK}
            strokeOpacity={GRID_OPACITY}
            strokeWidth={1}
          />
          <text x={px(t)} y={total + 14} textAnchor="middle" fill={INK} fontSize={FONT}>
            {tickLabel(t, ticks.step, chart.unit)}
          </text>
        </g>
      ))}
      {items.map((item, i) => {
        const top = tops[i];
        if (item.head !== undefined) {
          return (
            <text
              key={`h${i}`}
              x={8}
              y={top + 14}
              fill={INK}
              fontSize={FONT}
              data-testid={`chart-group-${item.head}`}
            >
              {item.head}
            </text>
          );
        }
        const row = item.row as CompareRow;
        const on = followed === row.runId;
        const first = top + item.h / 2 - ((row.name.length - 1) * 14) / 2 + 4;
        return (
          <g key={row.id}>
            <text
              role="button"
              tabIndex={0}
              aria-pressed={on}
              className={`chart-run-name${on ? ' is-followed' : ''}`}
              data-testid={`chart-run-${row.runId}`}
              x={GUTTER - 8}
              textAnchor="end"
              fill={INK}
              fontSize={FONT}
              onClick={() => onFollow(row.runId)}
              onKeyDown={(e) => toggle(e, row.runId)}
            >
              {row.name.map((line, n) => (
                <tspan key={n} x={GUTTER - 8} y={first + n * 14}>
                  {line}
                </tspan>
              ))}
            </text>
            {rowMarks(row, top, item.h)}
          </g>
        );
      })}
    </svg>
  );

  return (
    <div className="chart-panel" role="figure" aria-label={chart.title}>
      <h4 className="chart-head">
        <span className="chart-title">{chart.title}</span>
        <span className="chart-key">{chart.metricIds.map(label).join(' · ')}</span>
        <button
          type="button"
          className="chart-png"
          aria-label={`PNG ${chart.title}`}
          onClick={() => onPng(chart)}
        >
          PNG
        </button>
      </h4>
      {!broken && shared !== '' ? (
        <p className="compare-chart-line" data-testid="chart-shared-words">
          {shared}
        </p>
      ) : null}
      {broken ? (
        <ul className="compare-chart-line" data-testid="chart-run-key">
          {keyEntries(headers).map((entry) => (
            <li key={entry}>{entry}</li>
          ))}
        </ul>
      ) : null}
      {chart.context
        .filter((line) => broken || line !== shared)
        .map((line) => (
          <p key={line} className="compare-chart-line" data-testid="chart-context">
            {line}
          </p>
        ))}
      {chart.flag !== null ? (
        <p className="compare-chart-line" data-testid="chart-flag">
          {chart.flag}
        </p>
      ) : null}
      {preview === 'screen' ? (
        headers.length > SCROLL_RUNS ? (
          <div className="compare-chart-scroll">{svg}</div>
        ) : (
          svg
        )
      ) : (
        <img
          className="chart-preview"
          alt={chart.title}
          src={svgDataUrl(compareSvg(chart, meta, preview))}
        />
      )}
      {tip !== null ? (
        <div role="tooltip" className="chart-tooltip">
          {tip}
        </div>
      ) : null}
    </div>
  );
}
