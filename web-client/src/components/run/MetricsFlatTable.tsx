/** The by-role and by-model tables: the by-scope columns, one row per key, gateway descending. */
import type { components } from '../../api/schema';
import { flatRows } from '../../lib/run/metrics-tab';
import type { TargetContext } from '../../lib/run/metrics-glance';
import { ColumnHeads, FigureCell, useColumns } from './MetricsScopeTable';

type MetricValueOut = components['schemas']['MetricValueOut'];

interface Props {
  scopeType: 'role' | 'model';
  items: readonly MetricValueOut[];
  ctx: TargetContext;
}

export default function MetricsFlatTable({ scopeType, items, ctx }: Props) {
  const columns = useColumns();
  const keys = flatRows(items, scopeType);
  if (keys.length === 0) return null;
  return (
    <div className="wf-metrics-scroll">
      <h3 className="wf-metrics-section">{scopeType === 'role' ? 'BY ROLE' : 'BY MODEL'}</h3>
      <table className="wf-metrics-table" data-testid={`wf-metrics-${scopeType}`}>
        <thead>
          <tr>
            <th scope="col">{scopeType}</th>
            <ColumnHeads columns={columns} />
          </tr>
        </thead>
        <tbody>
          {keys.map((key) => (
            <tr key={key}>
              <th scope="row">{key}</th>
              {columns.map((id) => (
                <FigureCell
                  key={id}
                  items={items}
                  metricId={id}
                  scopeType={scopeType}
                  scopeKey={key}
                  ctx={ctx}
                />
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
