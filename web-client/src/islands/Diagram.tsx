/**
 * A Template's (or, from Epic 8, a Run's) shape as read-only SVG (3.6).
 *
 * Reusable and stateless on purpose: it is handed a `Graph` and a label, lays it out with
 * dagre (`src/lib/diagram/layout.ts`) and draws it with the three renderers
 * (`src/lib/diagram/svg.tsx`). It fetches nothing, holds nothing, and parses nothing — the
 * browser never reads YAML (AD-15), so every node, edge and group in the picture came from
 * the API. `TemplateDiagram.tsx` is the wrapper that owns the fetching and the state; Epic 8
 * adds its own beside it and mounts this same island.
 *
 * One `role="img"` with an `aria-label` rather than a labelled tree of shapes: the picture is
 * a single readable statement — which Template, which version, how many steps — and a screen
 * reader walking six unlabelled `<g>` elements would be worse than one sentence.
 *
 * The SVG scrolls inside its own container. A left-to-right Template of six steps is wider
 * than the 300px column the Templates screen gives it, and shrinking the boxes to fit would
 * make the type illegible at the one size this product sets it in.
 */
import { useMemo } from 'react';

import type { components } from '../api/schema';
import { layoutGraph } from '../lib/diagram/layout';
import { DiagramEdge, DiagramGroup, DiagramNode } from '../lib/diagram/svg';
import '../styles/diagram.css';

type Graph = components['schemas']['GraphOut'];

interface Props {
  graph: Graph;
  /** What the picture announces itself as. `TemplateDiagram` builds the Templates one. */
  ariaLabel: string;
}

export default function Diagram({ graph, ariaLabel }: Props) {
  // `TemplateDiagram` re-renders on every published validation outcome; the layout only
  // changes when the graph does
  const layout = useMemo(() => layoutGraph(graph), [graph]);

  return (
    <div className="diagram" data-testid="templates-diagram">
      <svg
        className="diagram-svg"
        role="img"
        aria-label={ariaLabel}
        width={layout.width}
        height={layout.height}
        viewBox={`0 0 ${layout.width} ${layout.height}`}
      >
        {/* groups first, so a dashed rectangle sits behind the boxes it encloses */}
        {layout.groups.map((placed) => (
          <DiagramGroup key={placed.group.id} placed={placed} />
        ))}
        {layout.edges.map((placed) => (
          <DiagramEdge key={placed.id} placed={placed} />
        ))}
        {layout.nodes.map((placed) => (
          <DiagramNode key={placed.node.id} placed={placed} />
        ))}
      </svg>
    </div>
  );
}
