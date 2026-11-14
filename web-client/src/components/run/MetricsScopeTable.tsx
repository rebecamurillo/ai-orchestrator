/**
 * The by-scope metric table: Run → epics → stories → steps → attempts, one level per caret.
 * Heads, hints and missing words come from the catalogue and the API (RM-2); an uncatalogued
 * column is not rendered, and a scope with no value for a column has an empty cell.
 */
import { Fragment } from 'react';
import { useStore } from '@nanostores/react';

import type { components } from '../../api/schema';
import { scopeTree, TABLE_COLUMNS, valuesAt, type ScopeNode } from '../../lib/run/metrics-tab';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import { $catalogue } from '../../stores/catalogue';
import { $metricsTab, isExpanded, toggleRow } from '../../stores/metrics-tab';
import HintControl from '../metrics/HintControl';
import ValueCell from '../metrics/ValueCell';

type MetricValueOut = components['schemas']['MetricValueOut'];

export function useColumns(): string[] {
  const { entries } = useStore($catalogue);
  return TABLE_COLUMNS.filter((id) => entries[id]);
}

export function ColumnHeads({ columns }: { columns: readonly string[] }) {
  return (
    <>
      {columns.map((id) => (
        <th key={id} scope="col">
          <HintControl metricId={id} showLabel />
        </th>
      ))}
    </>
  );
}

/** Every value at one scope for one metric; several (one per source) are joined by ` · `. */
export function FigureCell({
  items,
  metricId,
  scopeType,
  scopeKey,
  ctx,
}: {
  items: readonly MetricValueOut[];
  metricId: string;
  scopeType: string;
  scopeKey: string;
  ctx: TargetContext;
}) {
  const values = valuesAt(items, metricId, scopeType, scopeKey);
  return (
    <td className="wf-metrics-figure">
      {values.map((value, at) => (
        <Fragment key={`${value.source ?? ''}-${at}`}>
          {at > 0 ? ' · ' : null}
          <ValueCell target={targetFor(value, ctx)} />
        </Fragment>
      ))}
    </td>
  );
}

interface Props {
  items: readonly MetricValueOut[];
  stepOrder: readonly string[];
  ctx: TargetContext;
}

export default function MetricsScopeTable({ items, stepOrder, ctx }: Props) {
  const columns = useColumns();
  const state = useStore($metricsTab);
  const root = scopeTree(items, stepOrder);

  function rows(node: ScopeNode, depth: number): React.ReactNode {
    const open = depth === 0 || isExpanded(state, node.id);
    return (
      <Fragment key={node.id}>
        <tr data-testid="wf-metrics-row">
          <th scope="row" data-depth={depth}>
            {depth > 0 && node.children.length > 0 ? (
              <button
                type="button"
                className="wf-metrics-caret"
                aria-expanded={open}
                aria-label={`expand ${node.label}`}
                onClick={() => toggleRow(node.id)}
              >
                {open ? '▾' : '▸'}
              </button>
            ) : null}
            {node.label}
          </th>
          {columns.map((id) => (
            <FigureCell
              key={id}
              items={items}
              metricId={id}
              scopeType={node.type}
              scopeKey={node.key}
              ctx={ctx}
            />
          ))}
        </tr>
        {open ? node.children.map((child) => rows(child, depth + 1)) : null}
      </Fragment>
    );
  }

  return (
    <div className="wf-metrics-scroll">
      <table className="wf-metrics-table" data-testid="wf-metrics-scope">
        <thead>
          <tr>
            <th scope="col">scope</th>
            <ColumnHeads columns={columns} />
          </tr>
        </thead>
        <tbody>{rows(root, 0)}</tbody>
      </table>
    </div>
  );
}
