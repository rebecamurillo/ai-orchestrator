import { useStore } from '@nanostores/react';

import type { components } from '../../api/schema';
import { LIST_PRICE_WORDS, NOT_AVAILABLE_WORD } from '../../lib/metrics/format';
import { anySubscription, orderSpend, spendTarget } from '../../lib/metrics/home';
import { $catalogue } from '../../stores/catalogue';
import '../../styles/metrics-home.css';
import HintControl from './HintControl';
import MissingWord from './MissingWord';
import ValueCell from './ValueCell';

type ProjectSpendOut = components['schemas']['ProjectSpendOut'];

interface Props {
  items: ProjectSpendOut[];
  projectId: string | null;
}

export default function SpendTable({ items, projectId }: Props) {
  const { entries } = useStore($catalogue);

  function money(item: ProjectSpendOut, metricId: string, amount: string, reported: boolean) {
    if (!reported) return <MissingWord word={NOT_AVAILABLE_WORD} />;
    return <ValueCell target={spendTarget(item, metricId, amount, entries[metricId] ?? null)} />;
  }

  return (
    <>
      <div className="metrics-scroll">
        <table className="metrics-table" data-testid="metrics-spend-table">
          <thead>
            <tr>
              <th>project</th>
              <th>
                gateway <HintControl metricId="spend.month" />
              </th>
              <th>
                harness <HintControl metricId="cost.harness" />
              </th>
              <th>runs</th>
              <th>
                of which cancelled · gateway <HintControl metricId="spend.month_cancelled" />
              </th>
              <th>
                · harness <HintControl metricId="cost.harness" />
              </th>
              <th>cancelled runs</th>
            </tr>
          </thead>
          <tbody>
            {orderSpend(items, projectId).map((item) => (
              <tr
                key={item.project_id}
                data-testid={`metrics-spend-row-${item.project_id}`}
                data-current={item.project_id === projectId ? 'true' : undefined}
              >
                <td>{item.project_name}</td>
                <td>{money(item, 'spend.month', item.gateway, item.gateway_reported)}</td>
                <td>{money(item, 'cost.harness', item.harness, item.harness_reported)}</td>
                <td>{item.runs}</td>
                <td>
                  {money(
                    item,
                    'spend.month_cancelled',
                    item.cancelled.gateway,
                    item.gateway_reported,
                  )}
                </td>
                <td>
                  {money(item, 'cost.harness', item.cancelled.harness, item.harness_reported)}
                </td>
                <td>{item.cancelled.runs}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {anySubscription(items) && (
        <p className="metrics-note" data-testid="metrics-spend-list-price">
          {LIST_PRICE_WORDS}
        </p>
      )}
    </>
  );
}
