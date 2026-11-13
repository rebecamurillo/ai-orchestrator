/** The Run-scope metric list by group, headline or all metrics (EXPERIENCE §3). */
import { Fragment } from 'react';
import { useStore } from '@nanostores/react';

import type { components } from '../../api/schema';
import { metricList, type MetricsSet } from '../../lib/run/metrics-tab';
import { targetFor, type TargetContext } from '../../lib/run/metrics-glance';
import { $catalogue } from '../../stores/catalogue';
import HintControl from '../metrics/HintControl';
import ValueCell from '../metrics/ValueCell';

type MetricValueOut = components['schemas']['MetricValueOut'];

interface Props {
  items: readonly MetricValueOut[];
  set: MetricsSet;
  ctx: TargetContext;
}

export default function MetricsList({ items, set, ctx }: Props) {
  const { entries } = useStore($catalogue);
  const groups = metricList(entries, items, set);
  return (
    <div className="wf-metrics-list" data-testid="wf-metrics-list">
      {groups.map((group) => (
        <section key={group.group}>
          <h4 className="wf-metrics-group">{group.group}</h4>
          <dl className="wf-metrics-kv">
            {group.entries.flatMap(({ entry, values }) =>
              values.map((value, at) => (
                <Fragment key={`${entry.id}-${at}`}>
                  <dt>
                    <HintControl metricId={entry.id} showLabel />
                    {value.source ? ` · ${value.source}` : null}
                  </dt>
                  <dd>
                    <ValueCell target={targetFor(value, ctx)} />
                  </dd>
                </Fragment>
              )),
            )}
          </dl>
        </section>
      ))}
    </div>
  );
}
