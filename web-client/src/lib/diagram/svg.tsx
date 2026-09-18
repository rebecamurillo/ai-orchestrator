/**
 * The three things a Template diagram is made of, as SVG (3.6).
 *
 * Read-only, and deliberately so: this release draws a Template's shape and nothing else —
 * no run status, no token, no click-to-row, no drag, no edit. Epic 8 extends the same
 * renderers with a Run's statuses, which is why `DiagramNode` already accepts `status` and
 * `current` and puts them on the element as data attributes. They are unused today; a prop
 * that arrived later would mean restructuring the renderer instead of adding one rule to the
 * stylesheet.
 *
 * Every colour, size and dash lives in `src/styles/diagram.css` and reaches an element
 * through a class — never an inline `style`, and never a signal hue. A Template has no
 * status, so nothing here can be amber or red; the accent marks the one step that dispatches
 * a harness, and `unvalidated` and `human` are plain words in the same grey as every other.
 * A `human` node carries one thing more: the `line-strong` hairline the brief puts under the
 * word, which is what marks a stop a person answers without spending a signal hue on it.
 */
import type { components } from '../../api/schema';
import { tokenSignal } from '../board/format';
import { type PlacedEdge, type PlacedGroup, type PlacedNode } from './layout';

type NodeOut = components['schemas']['NodeOut'];

/** Inset of a node's text from its box. */
const TEXT_INSET = 9;
/** The three baselines inside a node box: eyebrow, title, gate. */
const EYEBROW_BASELINE = 14;
const TITLE_BASELINE = 28;
const GATE_BASELINE = 39;

/** The hairline under a human gate's word, and how wide one character of it is. */
const HAIRLINE_BASELINE = 43;
const GATE_CHAR_WIDTH = 6.9;

/** How far a group's name sits above the rectangle it labels. */
const GROUP_LABEL_OFFSET = 4;

/** The arrow head's length back along the connector, and its half-width. */
const HEAD_LENGTH = 6;
const HEAD_HALF_WIDTH = 3;

/** Right-margin for the token chip and text. */
const TOKEN_INSET = TEXT_INSET;
const CHIP_RADIUS = 3;
const CHIP_OFFSET_Y = 5;

/** Sub-step words baseline inside the node box (near the bottom). */
const SUBSTEPS_BASELINE = 44;

/** k/n count text baseline near the bottom of a group box (group boxes are taller). */
const GROUP_KN_BASELINE = 14;

/** Three-letter display token for each status (AD-15 dialect, story 1-5). */
const STATUS_TOKEN: Record<string, string> = {
  running: 'RUN',
  done: 'DON',
  blocked: 'BLK',
  checkpoint: 'CHK',
  error: 'ERR',
  skipped: 'SKP',
  queued: 'QUE',
  cancelled: 'CAN',
  planned: 'QUE',
};

/** The longest label a box can hold before it is cut; the boxes are a fixed width. */
const LABEL_LIMIT = 17;

/**
 * The word under a node's title: what the Template declared, or `unvalidated` where it
 * declared nothing (NFR-2). `null` on a collapsed call, which has no gate of its own — a
 * call is a path segment, never a stop, so the line is omitted rather than filled.
 */
export function gateWord(node: NodeOut): string | null {
  return node.gate;
}

/**
 * The eyebrow: a step kind's last segment — `git.worktree` reads `worktree`, `agent` reads
 * `agent`, `template` reads `template`.
 *
 * The last segment rather than the whole kind because the box is a fixed 132px and a dotted
 * kind set at 10.5px uppercase does not fit one, while the exact `uses:` value is on screen
 * in the YAML column beside the diagram. Nothing is conflated by the shortening: the kind
 * registry (`application/steps`) holds eleven kinds and their last segments are eleven
 * distinct words, which `tests/unit/diagram-svg.test.ts` asserts over the whole table rather
 * than leaving as an observation.
 */
export function kindWord(kind: string): string {
  const segments = kind.split('.');
  return segments[segments.length - 1]!;
}

/** A label that would overflow its box, cut with a single character rather than three. */
function fit(text: string): string {
  return text.length <= LABEL_LIMIT ? text : `${text.slice(0, LABEL_LIMIT - 1)}…`;
}

export interface DiagramNodeProps {
  placed: PlacedNode;
  /**
   * A Run's status token for this node. Epic 8 fills it in; nothing reads it in this
   * release, and a Template has no status of its own.
   */
  status?: string | null;
  /** Whether this node is the step a Run is on. Epic 8's, for the same reason. */
  current?: boolean;
  /** The display token for this node (e.g. "BLK", "DON"). Sets `data-signal` on the `<g>`. */
  token?: string | null;
  /** Sub-step words to render inside the node (Epic 8's story-aggregate nodes). */
  substeps?: string[] | null;
  /** Click handler for node navigation (Epic 8's run diagram). */
  onClick?: () => void;
}

export function DiagramNode({
  placed,
  status,
  current,
  token,
  substeps,
  onClick,
}: DiagramNodeProps) {
  const { node, x, y, width, height } = placed;
  const word = gateWord(node);

  return (
    <g
      className="diagram-node"
      data-testid={`diagram-node-${node.id}`}
      data-agent={node.agent ? 'true' : undefined}
      data-human={node.human ? 'true' : undefined}
      data-status={status ?? undefined}
      data-current={current ? 'true' : undefined}
      data-signal={token ? tokenSignal(token) : undefined}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onClick={onClick}
      onKeyDown={
        onClick
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') onClick();
            }
          : undefined
      }
    >
      <rect className="diagram-node-box" x={x} y={y} width={width} height={height} />
      <text className="diagram-node-eyebrow" x={x + TEXT_INSET} y={y + EYEBROW_BASELINE}>
        {current ? 'now' : fit(kindWord(node.kind))}
      </text>
      <text className="diagram-node-title" x={x + TEXT_INSET} y={y + TITLE_BASELINE}>
        {fit(node.label)}
      </text>
      {word === null ? null : (
        <text className="diagram-node-gate" x={x + TEXT_INSET} y={y + GATE_BASELINE}>
          {word}
        </text>
      )}
      {/* a person decides this step: the word, and the hairline the brief puts under it —
          never amber, because nothing here is running */}
      {node.human && word !== null ? (
        <line
          className="diagram-node-hairline"
          x1={x + TEXT_INSET}
          y1={y + HAIRLINE_BASELINE}
          x2={x + TEXT_INSET + word.length * GATE_CHAR_WIDTH}
          y2={y + HAIRLINE_BASELINE}
        />
      ) : null}
      {/* Run-status chip and token: right-aligned, only when the node carries a token */}
      {token ? (
        <>
          <circle
            className="diagram-node-chip"
            cx={x + width - TOKEN_INSET - CHIP_RADIUS}
            cy={y + EYEBROW_BASELINE - CHIP_OFFSET_Y}
            r={CHIP_RADIUS}
          />
          <text
            className="diagram-node-token"
            x={x + width - TOKEN_INSET}
            y={y + EYEBROW_BASELINE}
            textAnchor="end"
          >
            {token}
          </text>
        </>
      ) : null}
      {/* Sub-step words: the steps this story node summarises */}
      {substeps && substeps.length > 0 ? (
        <text className="diagram-node-substeps" x={x + TEXT_INSET} y={y + SUBSTEPS_BASELINE}>
          {substeps.join(' · ')}
        </text>
      ) : null}
    </g>
  );
}

export function DiagramGroup({
  placed,
  status,
  k,
  n,
}: {
  placed: PlacedGroup;
  status?: string | null;
  k?: number | null;
  n?: number | null;
}) {
  const { group, x, y, width, height } = placed;
  // Three-letter token: look up STATUS_TOKEN first; fall back to status as-is for raw tokens
  // passed by test fixtures (e.g. 'DON'), so existing assertions remain satisfied.
  const displayToken = status != null ? (STATUS_TOKEN[status] ?? status) : null;

  return (
    <g
      className="diagram-group"
      data-testid={`diagram-group-${group.id}`}
      data-status={status ?? undefined}
    >
      <rect className="diagram-group-box" x={x} y={y} width={width} height={height} />
      {/* Group label ABOVE the box — unchanged */}
      <text className="diagram-group-label" x={x} y={y - GROUP_LABEL_OFFSET}>
        {fit(group.label)}
      </text>
      {/* Status chip + 3-letter token at top-right inside the box */}
      {displayToken != null ? (
        <>
          <circle
            className="diagram-group-chip"
            cx={x + width - TOKEN_INSET - CHIP_RADIUS}
            cy={y + CHIP_OFFSET_Y}
            r={CHIP_RADIUS}
          />
          <text
            className="diagram-group-token"
            x={x + width - TOKEN_INSET}
            y={y + CHIP_OFFSET_Y + CHIP_RADIUS + 3}
            textAnchor="end"
          >
            {displayToken}
          </text>
        </>
      ) : null}
      {/* k/n step count at the bottom inside the box: "k/n steps". Omitted when n === 0. */}
      {(n ?? 0) > 0 ? (
        <text className="diagram-group-kn" x={x + TEXT_INSET} y={y + height - GROUP_KN_BASELINE}>
          {k}/{n} steps
        </text>
      ) : null}
    </g>
  );
}

export function DiagramEdge({ placed }: { placed: PlacedEdge }) {
  const points = placed.points.map((point) => `${point.x},${point.y}`).join(' ');
  const end = placed.points[placed.points.length - 1]!;
  const head = [
    `${end.x},${end.y}`,
    `${end.x - HEAD_LENGTH},${end.y - HEAD_HALF_WIDTH}`,
    `${end.x - HEAD_LENGTH},${end.y + HEAD_HALF_WIDTH}`,
  ].join(' ');

  return (
    <g className="diagram-edge" data-testid={`diagram-edge-${placed.id}`}>
      <polyline className="diagram-edge-line" points={points} />
      <polygon className="diagram-edge-head" points={head} />
    </g>
  );
}
