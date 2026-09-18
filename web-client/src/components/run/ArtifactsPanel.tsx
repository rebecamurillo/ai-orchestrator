/**
 * The Run detail's own ARTIFACTS column (6.3, SPEC CAP-2, FR-19, FR-23, UX-DR9): fetches
 * the tree on mount and after every successful save, opens an `ArtifactModal` overlay when
 * a file row is clicked, and re-fetches the tree when the modal signals a successful save
 * so the row's own `mtime` updates (AC5's own words).
 *
 * Three props (`runId`, `run`, `folder`), the same three facts `RunDetail.tsx`'s own
 * `plannedFile` effect already reads off `detail` — this panel owns its own tree/selection/
 * edit state entirely, so the island's own growth stays a handful of lines (the Code Map's
 * own reasoning).
 */
import { useEffect, useRef, useState } from 'react';

import { api } from '../../api/client';
import type { RunDetailOut } from '../../lib/run/detail';
import { isTree, treeRequestPath, type RunFilesTreeChangedOut } from '../../lib/run/artifacts';
import ArtifactsTree from './ArtifactsTree';
import ArtifactModal from './ArtifactModal';

type RunSummary = RunDetailOut['run'];

interface Props {
  runId: string;
  run: RunSummary;
  folder: string;
}

export default function ArtifactsPanel({ runId, run, folder }: Props) {
  const [tree, setTree] = useState<RunFilesTreeChangedOut | null>(null);
  const [treeError, setTreeError] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  // `RunDetail.tsx`'s own `requestSeqRef` precedent: `fetchTree` is called from both an
  // effect and the modal's own `onSaved` callback, so a sequence number keeps a slow,
  // stale response from landing after a newer one.
  const treeSeqRef = useRef(0);

  async function fetchTree(): Promise<void> {
    const seq = ++treeSeqRef.current;
    const { data, error } = await api.GET('/runs/{run_id}/files', {
      params: { path: { run_id: runId } },
    });
    if (seq !== treeSeqRef.current) return;
    if (error || !data || !isTree(data)) {
      setTreeError(true);
      setTree(null);
      return;
    }
    setTreeError(false);
    setTree(data);
  }

  useEffect(() => {
    setSelectedPath(null);
    void fetchTree();
    // fires once on mount and again whenever the Run itself changes underneath this panel
  }, [runId]);

  return (
    <section className="wf-artifacts" data-testid="wf-artifacts">
      <h2 className="wf-section-head">ARTIFACTS</h2>
      {treeError ? (
        <p className="wf-artifacts-error" data-testid="wf-artifacts-error">
          could not read {treeRequestPath(runId)}
        </p>
      ) : null}
      {tree ? (
        <ArtifactsTree
          entries={tree.entries}
          root={tree.root}
          selectedPath={selectedPath}
          onSelect={(path) => setSelectedPath(path)}
        />
      ) : null}
      {selectedPath ? (
        <ArtifactModal
          runId={runId}
          path={selectedPath}
          run={run}
          folder={folder}
          onClose={() => setSelectedPath(null)}
          onSaved={() => void fetchTree()}
        />
      ) : null}
    </section>
  );
}
