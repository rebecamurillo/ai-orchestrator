/**
 * The Run page's files column: every epic's and story's files, grouped the way the plan is
 * (epic 2 story 1, EXPERIENCE § 6.1). Reads `GET /runs/{id}/files-by-epic` on mount, on each
 * `$poll` tick and after a save; a changed path opens its unified diff inline.
 */
import { useStore } from '@nanostores/react';
import { useEffect, useRef, useState } from 'react';

import { api } from '../../api/client';
import type { RunDetailOut } from '../../lib/run/detail';
import {
  buildFilesView,
  diffLines,
  filesByEpicRequestPath,
  focusAnchor,
  type EpicView,
  type FileRef,
  type StoryView,
} from '../../lib/run/files-by-epic';
import { $filesFocus } from '../../stores/files-focus';
import { $poll } from '../../stores/poll';
import ArtifactModal from './ArtifactModal';

interface Props {
  runId: string;
  run: RunDetailOut['run'];
  folder: string;
}

type DiffState = { text: string } | { error: true };

export default function FilesByEpic({ runId, run, folder }: Props) {
  const [view, setView] = useState<EpicView[]>([]);
  const [failed, setFailed] = useState(false);
  const [selected, setSelected] = useState<string | null>(null);
  const [open, setOpen] = useState<Set<string>>(new Set());
  const [diffs, setDiffs] = useState<Record<string, DiffState>>({});
  const tick = useStore($poll);
  const focus = useStore($filesFocus);
  // a slow, stale response must not land after a newer one (mount, tick and save all fetch)
  const seq = useRef(0);

  async function load(): Promise<void> {
    const mine = ++seq.current;
    const { data, error } = await api.GET('/runs/{run_id}/files-by-epic', {
      params: { path: { run_id: runId } },
    });
    if (mine !== seq.current) return;
    if (error || !data || !Array.isArray(data.epics)) {
      setFailed(true);
      setView([]);
      return;
    }
    setFailed(false);
    setView(buildFilesView(data));
  }

  useEffect(() => setSelected(null), [runId]);

  // a tick must not close an open modal: the operator may be mid-edit
  useEffect(() => {
    void load();
  }, [runId, tick]);

  const focused = focusAnchor(view, focus);
  useEffect(() => {
    if (focused) document.getElementById(focused)?.scrollIntoView({ block: 'nearest' });
  }, [focused, view]);

  function toggle(key: string): void {
    const next = new Set(open);
    if (!next.delete(key)) next.add(key);
    setOpen(next);
  }

  async function showDiff(epic: number, story: string, path: string): Promise<void> {
    const key = `${epic}/${story}/${path}`;
    if (diffs[key]) {
      setDiffs((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => k !== key)));
      return;
    }
    const { data, error } = await api.GET('/runs/{run_id}/files-by-epic/diff', {
      params: { path: { run_id: runId }, query: { epic, story, path } },
    });
    setDiffs((prev) => ({
      ...prev,
      [key]: error || !data ? { error: true } : { text: data.diff },
    }));
  }

  const fileButton = (file: FileRef) => (
    <button
      type="button"
      className="wf-files-file"
      data-testid={`artifacts-file-${file.path}`}
      onClick={() => setSelected(file.path)}
    >
      {file.name}
    </button>
  );

  function storyRows(epic: EpicView, story: StoryView) {
    const key = `${epic.index}/${story.id}`;
    return (
      <div key={story.anchor}>
        <div id={story.anchor} className={rowClass('wf-files-story', story.anchor, focused)}>
          {story.label}
        </div>
        {story.file ? fileButton(story.file) : null}
        {story.noFile ? <p className="wf-files-none">no file yet</p> : null}
        {story.changedLabel ? (
          <button
            type="button"
            className="wf-files-changed"
            aria-expanded={open.has(key)}
            onClick={() => toggle(key)}
          >
            {story.changedLabel}
          </button>
        ) : null}
        {open.has(key)
          ? story.changed.map((path) => {
              const diff = diffs[`${epic.index}/${story.id}/${path}`];
              return (
                <div key={path}>
                  <button
                    type="button"
                    className="wf-files-path"
                    onClick={() => void showDiff(epic.index, story.id, path)}
                  >
                    {path}
                  </button>
                  {diff && 'error' in diff ? (
                    <p className="wf-artifacts-error">could not read the diff of {path}</p>
                  ) : diff ? (
                    <pre className="wf-files-diff">
                      {diffLines(diff.text).map((line, i) => (
                        <span key={i} className={`wf-files-diff-${line.kind}`}>
                          {line.text + '\n'}
                        </span>
                      ))}
                    </pre>
                  ) : null}
                </div>
              );
            })
          : null}
      </div>
    );
  }

  return (
    <>
      <h2 className="wf-section-head">FILES · BY EPIC AND STORY</h2>
      {failed ? (
        <p className="wf-artifacts-error" data-testid="wf-artifacts-error">
          could not read {filesByEpicRequestPath(runId)}
        </p>
      ) : null}
      {view.map((epic) => (
        <div key={epic.anchor} className="wf-files-epic">
          <div id={epic.anchor} className={rowClass('wf-files-group', epic.anchor, focused)}>
            <span>{epic.label}</span>
            <span className="wf-files-folder">{epic.folder}</span>
          </div>
          {epic.files.map((file) => (
            <div key={file.path}>{fileButton(file)}</div>
          ))}
          {epic.stories.map((story) => storyRows(epic, story))}
        </div>
      ))}
      {selected ? (
        <ArtifactModal
          runId={runId}
          path={selected}
          run={run}
          folder={folder}
          onClose={() => setSelected(null)}
          onSaved={() => void load()}
        />
      ) : null}
    </>
  );
}

function rowClass(base: string, anchor: string, focused: string | null): string {
  return anchor === focused ? `${base} wf-files-focus` : base;
}
