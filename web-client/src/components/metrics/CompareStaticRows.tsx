import { Fragment } from 'react';

import type { components } from '../../api/schema';
import {
  cellTarget,
  NO_CELL,
  NOT_RUN_WORD,
  RECALC_WORD,
  recalcHref,
  runCells,
  staticRows,
  type CompareState,
} from '../../lib/metrics/compare';
import {
  TEST_FIRST,
  cellWords,
  splitCells,
  toolFlag,
  toolLine,
} from '../../lib/metrics/static-signals';
import HintControl from './HintControl';
import MissingWord from './MissingWord';
import ValueCell from './ValueCell';

type CompareOut = components['schemas']['CompareOut'];
type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];

interface Props {
  payload: CompareOut;
  entries: Record<string, CatalogueEntryOut>;
  set: CompareState['set'];
}

/** The `code` rows under STATIC SIGNALS: raw values, then the stored rate, then the tool version. */
export default function CompareStaticRows({ payload, entries, set }: Props) {
  return (
    <>
      {staticRows(entries, payload.metrics, set).map((m) => {
        const flag = toolFlag(m, payload.runs);
        return (
          <tr key={m.metric_id} data-testid={`compare-row-${m.metric_id}`}>
            <th scope="row" className="compare-metric">
              <span className="metric-label">{entries[m.metric_id].label}</span>
              <HintControl metricId={m.metric_id} />
              {flag !== null && <span className="compare-flag"> {flag}</span>}
            </th>
            {payload.runs.map((h) => {
              const cells = runCells(m, h.run_id);
              const { raws, rates, small } = splitCells(cells);
              const under = toolLine(m, h.run_id);
              const place = (c: (typeof cells)[number]) => (
                <ValueCell
                  key={c.method_id + c.scope_key + c.source}
                  target={cellTarget(c, m.metric_id, h)}
                />
              );
              return (
                <td key={h.run_id} data-testid={`compare-cell-${m.metric_id}-${h.run_id}`}>
                  {cells.length === 0 ? (
                    m.metric_id !== TEST_FIRST && payload.diff_size[h.run_id] === NOT_RUN_WORD ? (
                      <>
                        <MissingWord word={NOT_RUN_WORD} />{' '}
                        <a href={recalcHref(h.run_id)}>{RECALC_WORD}</a>
                      </>
                    ) : (
                      NO_CELL
                    )
                  ) : (
                    <>
                      {raws.map((c, at) => (
                        <Fragment key={at}>
                          {at > 0 && ' / '}
                          {raws.length > 1 && cellWords(m.metric_id, c.source).before !== null && (
                            <span className="metric-label">
                              {cellWords(m.metric_id, c.source).before}{' '}
                            </span>
                          )}
                          {place(c)}
                          {cellWords(m.metric_id, c.source).after !== null && (
                            <span className="metric-label">
                              {' '}
                              {cellWords(m.metric_id, c.source).after}
                            </span>
                          )}
                        </Fragment>
                      ))}
                      {rates.map((c) => (
                        <Fragment key={c.source}>
                          {' · '}
                          {place(c)}
                        </Fragment>
                      ))}
                      {small.map(place)}
                    </>
                  )}
                  {under !== null && <div className="compare-under">{under}</div>}
                </td>
              );
            })}
          </tr>
        );
      })}
    </>
  );
}
