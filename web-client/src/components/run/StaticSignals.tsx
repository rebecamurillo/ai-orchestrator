/**
 * STATIC SIGNALS ON THE CHANGE (epic 5 story 5): the Run row then one row per repository, per
 * tier, with the tool footer always printed. Every figure is a stored value, printed as given.
 */
import { useStore } from '@nanostores/react';
import { useEffect } from 'react';

import type { components } from '../../api/schema';
import {
  RATE_HEAD,
  RAW_HEAD,
  STATIC_HEAD,
  STATIC_SUB,
  footerLines,
  hasAnalysisCode,
  isEmptyTier,
  notRunLine,
  staticTable,
  tierThree,
} from '../../lib/metrics/static-signals';
import type { TargetContext } from '../../lib/run/metrics-glance';
import { $catalogue } from '../../stores/catalogue';
import { $runAnalysis, loadRunAnalysis } from '../../stores/run-analysis';
import FailedFetch from '../FailedFetch';
import { NotAvailable, TierRows } from './StaticSignalsRows';
import StaticTierThree from './StaticTierThree';

type MetricValueOut = components['schemas']['MetricValueOut'];

interface Props {
  runId: string;
  shown: number;
  items: readonly MetricValueOut[];
  ctx: TargetContext;
  set: 'headline' | 'all';
}

export default function StaticSignals({ runId, shown, items, ctx, set }: Props) {
  const state = useStore($runAnalysis);
  const { entries } = useStore($catalogue);

  useEffect(() => {
    void loadRunAnalysis(runId, shown);
  }, [runId, shown]);

  const current = state.runId === runId && state.version === shown;
  const analyses = current ? state.items : [];
  const stepEntries = current ? (state.stepEntries ?? []) : [];
  const hasTestFirst = tierThree(items, [], set).testFirst !== null;

  let body;
  if (!current || state.status === 'idle' || state.status === 'loading') {
    body = <p className="wf-metrics-note">…</p>;
  } else if (state.status === 'failed' && state.failed) {
    body = (
      <FailedFetch
        method="GET"
        path={state.failed.path}
        status={state.failed.status}
        onRetry={() => void loadRunAnalysis(runId, shown)}
      />
    );
  } else if (analyses.length === 0 && !hasAnalysisCode(items)) {
    body = (
      <>
        <p className="wf-metrics-note">{notRunLine(shown)}</p>
        {hasTestFirst && (
          <table className="wf-metrics-static" data-testid="static-signals-table">
            <tbody>
              <StaticTierThree items={items} stepEntries={stepEntries} set={set} ctx={ctx} />
            </tbody>
          </table>
        )}
      </>
    );
  } else {
    const tiers = staticTable(items, analyses, entries, set);
    body = (
      <>
        <table className="wf-metrics-static" data-testid="static-signals-table">
          <thead>
            <tr>
              <th scope="col">signal</th>
              <th scope="col">{RAW_HEAD}</th>
              <th scope="col">{RATE_HEAD}</th>
            </tr>
          </thead>
          <tbody>
            {tiers.map((tier) =>
              tier.tier === '2' && isEmptyTier(tier) ? (
                <NotAvailable key={tier.tier} head={tier.head} />
              ) : (
                <TierRows
                  key={tier.tier}
                  head={tier.head}
                  scopes={tier.scopes}
                  analyses={analyses}
                  runId={runId}
                  ctx={ctx}
                />
              ),
            )}
            <StaticTierThree items={items} stepEntries={stepEntries} set={set} ctx={ctx} />
          </tbody>
        </table>
        {analyses.length > 0 && (
          <div className="static-foot" data-testid="static-foot">
            {footerLines(analyses).map((line) => (
              <div key={line}>{line}</div>
            ))}
          </div>
        )}
      </>
    );
  }

  return (
    <section className="wf-metrics-static-block" data-testid="static-signals">
      <h3 className="wf-metrics-section">{STATIC_HEAD}</h3>
      <p className="wf-metrics-note">{STATIC_SUB}</p>
      {body}
    </section>
  );
}
