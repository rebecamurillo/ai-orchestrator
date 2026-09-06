/**
 * The Templates screen's diagram column: the picture, kept level with the editor (3.6).
 *
 * The initial graph arrives as a prop — the page reads it server-side, so the column is
 * drawn before any island runs. After that this island follows the editor: `TemplateEditor`
 * publishes `{seq, yaml, ok}` to `src/stores/template-validation.ts` at the one place a
 * fresh validation outcome lands, and this island subscribes.
 *
 * **Who fetches the graph.** The editor publishes text and validity, never a graph. Fetching
 * it here keeps the editor's job unchanged (it validates) and this column's job whole (it
 * draws), at the cost of one extra round trip after each successful validation — which is
 * exactly what the brief describes.
 *
 * **The last-valid rule.** `reduceDiagram` (`src/lib/diagram/diagram-state.ts`) holds it: a
 * validation that succeeds swaps the graph in, anything else keeps the previous graph and
 * shows the stale line. The diagram is never blank and never silently wrong.
 *
 * **Why `handledRef` and `seqRef`.** `useStore` re-runs the effect for every published
 * outcome, and React may run an effect twice in development; `handledRef` makes each `seq`
 * fetch once. `seqRef` is the one the *response* checks: a slow graph request for an earlier
 * outcome must not overwrite a later one, the same rule `TemplateEditor`'s own
 * `requestSeqRef` states for its two calls.
 */
import { useEffect, useRef, useState } from 'react';
import { useStore } from '@nanostores/react';

import type { components } from '../api/schema';
import { api } from '../api/client';
import { STALE_LINE, reduceDiagram, type DiagramState } from '../lib/diagram/diagram-state';
import { $templateValidation } from '../stores/template-validation';
import Diagram from './Diagram';

type Graph = components['schemas']['GraphOut'];

interface Props {
  name: string;
  version: number;
  /** The stored version's graph, read by the page. Empty when that read failed. */
  graph: Graph;
}

/** `template {name} v{n} · {nodes} steps` — what the picture announces itself as. */
export function diagramAriaLabel(name: string, version: number, steps: number): string {
  return `template ${name} v${version} · ${steps} steps`;
}

export default function TemplateDiagram({ name, version, graph }: Props) {
  const outcome = useStore($templateValidation);
  const [state, setState] = useState<DiagramState>({ graph, stale: false });
  const handledRef = useRef(0);
  const seqRef = useRef(0);

  useEffect(() => {
    if (outcome === null || outcome.seq === handledRef.current) return;
    handledRef.current = outcome.seq;
    seqRef.current = outcome.seq;
    const seq = outcome.seq;

    if (!outcome.ok) {
      setState((previous) => reduceDiagram(previous, { type: 'validated-failed' }));
      return;
    }

    void (async () => {
      try {
        const { data, error } = await api.POST('/templates/{name}/graph', {
          params: { path: { name } },
          body: { yaml: outcome.yaml },
        });
        if (seq !== seqRef.current) return; // superseded by a later validation
        if (error || !data) {
          setState((previous) => reduceDiagram(previous, { type: 'graph-failed' }));
          return;
        }
        setState((previous) => reduceDiagram(previous, { type: 'validated-ok', graph: data }));
      } catch {
        if (seq === seqRef.current) {
          setState((previous) => reduceDiagram(previous, { type: 'graph-failed' }));
        }
      }
    })();
  }, [outcome, name]);

  return (
    <div className="template-diagram">
      {/* above the picture, where the brief puts it: the reader meets the caveat before the
          thing it qualifies */}
      {state.stale ? (
        <p className="template-diagram-stale" data-testid="templates-diagram-stale">
          {STALE_LINE}
        </p>
      ) : null}
      <Diagram
        graph={state.graph}
        ariaLabel={diagramAriaLabel(name, version, state.graph.nodes.length)}
      />
    </div>
  );
}
