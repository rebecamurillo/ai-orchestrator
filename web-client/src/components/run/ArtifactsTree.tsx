/**
 * The ARTIFACTS column's own tree (6.3, FR-23, UX-DR9): one row per entry, 14px indent per
 * depth with a guide rule, filename left / mtime right-aligned (`DESIGN.md`'s own artifact-
 * tree shape). A directory row is structural only — clicking opens nothing; every other
 * control (viewer, Edit, read-only line) belongs to a *file* row, `ArtifactsPanel`'s own.
 *
 * The depth is rendered through `data-depth`, not an inline style: `web-client/AGENTS.md`
 * forbids inline styles, so the 14px multiplier lives in `run-detail.css` as a small,
 * bounded set of `[data-depth]` rules — the same attribute-selector shape `.wf-token[data-
 * signal=...]` already uses for a value this component cannot know ahead of time either.
 */
import { fileName, mtimeText, treeDepth, type RunFileEntryOut } from '../../lib/run/artifacts';

//: `changed` is optional so pre-8-3 callers (and the frozen unit test) that pass plain
//: `RunFileEntryOut[]` without the field still type-check; `=== true` guards the template.
type TreeEntry = RunFileEntryOut & { changed?: boolean };

interface Props {
  entries: TreeEntry[];
  root: string;
  selectedPath: string | null;
  onSelect: (path: string) => void;
}

//: `run-detail.css` declares `[data-depth]` rules up to this bound; a spec/initiative
//: folder nested deeper than this still renders, just at the deepest rule's own indent.
const MAX_DEPTH = 8;

export default function ArtifactsTree({ entries, root, selectedPath, onSelect }: Props) {
  return (
    <ul className="wf-artifacts-tree" data-testid="artifacts-tree">
      {entries.map((entry) => {
        const depth = Math.min(treeDepth(entry.path, root), MAX_DEPTH);
        return (
          <li key={entry.path} className="wf-artifacts-row" data-depth={depth}>
            {entry.kind === 'dir' ? (
              <span className="wf-artifacts-dir" data-testid={`artifacts-file-${entry.path}`}>
                {fileName(entry.path)}
              </span>
            ) : (
              <button
                type="button"
                className="wf-artifacts-file"
                data-testid={`artifacts-file-${entry.path}`}
                data-changed={entry.changed ? 'true' : undefined}
                aria-current={selectedPath === entry.path}
                onClick={() => onSelect(entry.path)}
              >
                {entry.changed ? <span className="wf-artifacts-chip" aria-hidden="true" /> : null}
                <span className="wf-artifacts-name">{fileName(entry.path)}</span>
                <span className="wf-artifacts-mtime">{mtimeText(entry)}</span>
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
