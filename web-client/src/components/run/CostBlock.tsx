/**
 * The COST & TRACE kv (4.15, right column; provisional marker and trace row 5.10): spent/
 * budget as a ratio with `provisional` after it when any attempt's cost is still an estimate,
 * tokens in/out, wall-clock, `your active time` as `hh:mm:ss` (8.2), a `trace` row linking
 * `open in Langfuse` to `cost.trace_url` when one
 * exists (absent — no row at all — when it does not), the compare links, and the branch link.
 *
 * A `done` Run that gave up on a Story names it on the compare line itself — `{url} · skipped:
 * {ids}` (6.4, FR-11, FR-20). It is written there rather than counted out of the progress:
 * `summary.progress` deliberately reads the epic as complete, so the link is where the skip
 * stays visible.
 *
 * A ratio is printed as a ratio, never a bar or a percentage (`KvTable.astro`'s own rule,
 * restated here since a `.astro` component cannot be nested inside a React island).
 * Stateless (`renderToStaticMarkup`).
 */
import FailedFetch from '../FailedFetch';
import HintControl from '../metrics/HintControl';
import VersionSelector from '../metrics/VersionSelector';
import type { RunDetailOut } from '../../lib/run/detail';
import {
  activeTimeText,
  branchLinkHref,
  moneyRatio,
  tokensText,
  wallClockText,
} from '../../lib/run/detail';
import { compareLinkText } from '../../lib/run/skip';
import type { RunMetricsState } from '../../stores/run-metrics';
import CostGlance, { FiguresGap } from './CostGlance';

interface Props {
  detail: RunDetailOut;
  /** The metric reads; absent, the block shows the Run record's own rows only. */
  glance?: RunMetricsState;
  subscription?: boolean;
  onSelectVersion?: (n: number) => void;
  onRetryMetrics?: () => void;
}

const NOOP = (): void => undefined;

export default function CostBlock({
  detail,
  glance,
  subscription = false,
  onSelectVersion = NOOP,
  onRetryMetrics = NOOP,
}: Props) {
  const cost = detail.cost;
  const showGlance = glance !== undefined && detail.run.status !== 'queued';
  const latest = Math.max(0, ...(glance?.versions.map((v) => v.n) ?? []));
  const branchHref = branchLinkHref(detail);

  return (
    <section className="wf-cost" data-testid="wf-cost">
      <h2 className="wf-section-head">COST &amp; TRACE</h2>
      {showGlance && glance.versions.length > 0 ? (
        <VersionSelector
          versions={glance.versions}
          selected={glance.selected ?? glance.metrics?.latest ?? latest}
          onSelect={onSelectVersion}
        />
      ) : null}
      {showGlance && glance.failed ? (
        <FailedFetch
          method="GET"
          path={glance.failed.path}
          status={glance.failed.status}
          onRetry={onRetryMetrics}
        />
      ) : null}
      {showGlance ? (
        <CostGlance detail={detail} glance={glance} subscription={subscription} />
      ) : null}
      <table className="wf-cost-kv">
        <tbody>
          <tr>
            <th scope="row">budget used</th>
            <td>
              {moneyRatio(cost)}
              {cost.provisional ? (
                <span data-testid="wf-cost-provisional"> provisional</span>
              ) : null}
              <HintControl metricId="budget.used" />
            </td>
          </tr>
          <tr>
            <th scope="row">tokens</th>
            <td>{tokensText(cost)}</td>
          </tr>
          <tr>
            <th scope="row">wall-clock</th>
            <td>{wallClockText(cost)}</td>
          </tr>
          <tr>
            <th scope="row">your active time</th>
            <td>{activeTimeText(cost)}</td>
          </tr>
          {cost.trace_url ? (
            <tr>
              <th scope="row">trace</th>
              <td>
                <a href={cost.trace_url} data-testid="wf-trace">
                  open in Langfuse
                </a>
              </td>
            </tr>
          ) : null}
        </tbody>
      </table>
      {showGlance ? <FiguresGap glance={glance} /> : null}
      <ul className="wf-cost-links">
        {detail.run.compare_urls.map((url) => (
          <li key={url}>
            <a href={url}>{compareLinkText(detail, url)}</a>
          </li>
        ))}
        {branchHref ? (
          <li>
            <a href={branchHref}>{detail.run.branch}</a>
          </li>
        ) : null}
      </ul>
    </section>
  );
}
