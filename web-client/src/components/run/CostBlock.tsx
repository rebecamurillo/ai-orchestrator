/**
 * The COST & TRACE kv (4.15, right column): spent/budget as a ratio, tokens in/out,
 * wall-clock, `your active time —` (Epic 8 is out of this story's scope, per its own Out
 * list), the trace link when one exists (Epic 5 — always absent this epic), the compare
 * links, and the branch link.
 *
 * A ratio is printed as a ratio, never a bar or a percentage (`KvTable.astro`'s own rule,
 * restated here since a `.astro` component cannot be nested inside a React island).
 * Stateless (`renderToStaticMarkup`).
 */
import type { RunDetailOut } from '../../lib/run/detail';
import { branchLinkHref, moneyRatio, tokensText, wallClockText } from '../../lib/run/detail';

interface Props {
  detail: RunDetailOut;
}

export default function CostBlock({ detail }: Props) {
  const cost = detail.cost;
  const branchHref = branchLinkHref(detail);

  return (
    <section className="wf-cost" data-testid="wf-cost">
      <h2 className="wf-section-head">COST &amp; TRACE</h2>
      <table className="wf-cost-kv">
        <tbody>
          <tr>
            <th scope="row">spent / budget</th>
            <td>{moneyRatio(cost)}</td>
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
            <td>—</td>
          </tr>
        </tbody>
      </table>
      {cost.trace_url ? (
        <p>
          <a href={cost.trace_url}>trace</a>
        </p>
      ) : null}
      <ul className="wf-cost-links">
        {detail.run.compare_urls.map((url) => (
          <li key={url}>
            <a href={url}>{url}</a>
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
