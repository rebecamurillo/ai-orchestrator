/**
 * The Run detail's own ARTIFACTS column (6.3, SPEC CAP-2, FR-19, FR-23, UX-DR9): fetches
 * the tree on mount and after every successful save, fetches one file's content on
 * selection, and PUTs on Save — then re-fetches the tree so the row's own `mtime` updates
 * (AC5's own words).
 *
 * Three props (`runId`, `run`, `folder`), the same three facts `RunDetail.tsx`'s own
 * `plannedFile` effect already reads off `detail` — this panel owns its own tree/selection/
 * edit state entirely, so the island's own growth stays a handful of lines (the Code Map's
 * own reasoning).
 */
import { useEffect, useRef, useState } from 'react';

import { api } from '../../api/client';
import type { components } from '../../api/schema';
import type { RunDetailOut } from '../../lib/run/detail';
import {
  canEditFile,
  isListFile,
  isTree,
  readOnlyLine as readOnlyLineText,
  treeRequestPath,
  type RunFileOut,
  type RunFilesTreeOut,
} from '../../lib/run/artifacts';
import ArtifactsTree from './ArtifactsTree';
import FileEditor from './FileEditor';
import FileViewer from './FileViewer';

type ProblemDetail = components['schemas']['ProblemDetail'];
type RunSummary = RunDetailOut['run'];

interface Props {
  runId: string;
  run: RunSummary;
  folder: string;
}

export default function ArtifactsPanel({ runId, run, folder }: Props) {
  const [tree, setTree] = useState<RunFilesTreeOut | null>(null);
  const [treeError, setTreeError] = useState(false);
  const [selected, setSelected] = useState<RunFileOut | null>(null);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<ProblemDetail | null>(null);
  // `RunDetail.tsx`'s own `requestSeqRef` precedent: `fetchTree`/`fetchFile` are called from
  // both an effect and the tree's own click handler, so a sequence number (not a single
  // effect-scoped `cancelled` boolean) is what keeps a slow, stale response from landing
  // after a newer one — a save's own tree/file re-fetch racing a fresh selection, or a
  // `runId` change outrunning the fetch it replaced.
  const treeSeqRef = useRef(0);
  const fileSeqRef = useRef(0);

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

  async function fetchFile(path: string): Promise<void> {
    const seq = ++fileSeqRef.current;
    const { data, error } = await api.GET('/runs/{run_id}/files', {
      params: { path: { run_id: runId }, query: { path } },
    });
    if (seq !== fileSeqRef.current) return;
    if (error || !data || isTree(data)) return;
    setSelected(data);
    setEditing(false);
    setSaveError(null);
  }

  useEffect(() => {
    void fetchTree();
    // fires once on mount and again whenever the Run itself changes underneath this panel
  }, [runId]);

  async function save(content: string): Promise<void> {
    if (!selected) return;
    setSaving(true);
    setSaveError(null);
    try {
      const { data, error } = await api.PUT('/runs/{run_id}/files', {
        params: { path: { run_id: runId } },
        body: { path: selected.path, content },
      });
      if (error || !data) {
        setSaveError(
          error ?? {
            status: 0,
            title: 'the request failed',
            type: 'about:blank',
            detail: `PUT ${treeRequestPath(runId)} → empty response`,
          },
        );
        return;
      }
      setEditing(false);
      await Promise.all([fetchFile(selected.path), fetchTree()]);
    } finally {
      setSaving(false);
    }
  }

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
          selectedPath={selected?.path ?? null}
          onSelect={(path) => void fetchFile(path)}
        />
      ) : null}
      {selected ? (
        editing ? (
          <FileEditor
            path={selected.path}
            initialContent={selected.content}
            branch={run.branch}
            saving={saving}
            error={saveError}
            onSave={(content) => void save(content)}
            onCancel={() => setEditing(false)}
          />
        ) : (
          <FileViewer
            path={selected.path}
            content={selected.content}
            readOnlyLine={isListFile(folder, selected.path) ? readOnlyLineText(run.plan_ref) : null}
            canEdit={canEditFile(run, selected.path, folder)}
            editing={editing}
            onEditToggle={() => setEditing(true)}
          />
        )
      ) : null}
    </section>
  );
}
