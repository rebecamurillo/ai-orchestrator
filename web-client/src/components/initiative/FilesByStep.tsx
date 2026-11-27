/**
 * The right column's FILES BY WORKFLOW AND STEP. State words, `draft` and `changed` are the
 * API's; a file with a Run id opens the artifact modal read-only (no Run to edit on).
 */
import { useState } from 'react';

import ArtifactModal from '../run/ArtifactModal';
import {
  AUTO_FILES_LINK,
  fileMeta,
  filePath,
  stepGroupHeading,
  workflowHeading,
} from '../../lib/initiative/files';
import { isInteractive, type InitiativeDetail, type Selection } from '../../lib/initiative/page';

interface Props {
  detail: InitiativeDetail;
  selection: Selection;
}

interface RowFile {
  path: string;
  run_id: string | null;
  time?: string | null;
  draft?: boolean;
  changed?: boolean;
}

type Opened = { runId: string; path: string } | null;

function FileRow({
  file,
  folder,
  onOpen,
}: {
  file: RowFile;
  folder: string;
  onOpen: (o: Opened) => void;
}) {
  const content = (
    <>
      {file.changed ? (
        <span
          className="ini-file-chip"
          data-testid="ini-file-changed"
          aria-label="changed since your last view"
        />
      ) : null}
      <span className="ini-file-path">{filePath(file.path, folder)}</span>
      <span className="ini-file-time">
        {fileMeta({ time: file.time ?? null, draft: !!file.draft })}
      </span>
    </>
  );
  const runId = file.run_id;
  if (runId === null) return <span className="ini-file">{content}</span>;
  return (
    <button
      type="button"
      className="ini-file"
      data-testid="ini-file"
      onClick={() => onOpen({ runId, path: file.path })}
    >
      {content}
    </button>
  );
}

export default function FilesByStep({ detail, selection }: Props) {
  const [opened, setOpened] = useState<Opened>(null);
  const folder = detail.folder;
  return (
    <section className="ini-files" data-testid="ini-files">
      <div className="ini-section-head ini-files-head">
        <span>FILES BY WORKFLOW AND STEP</span>
        <span>{folder}/</span>
      </div>
      {detail.workflows.map((w) => (
        <div className="ini-files-wf" key={w.position}>
          <h3 className="ini-files-wf-name">{workflowHeading(w.position, w.workflow)}</h3>
          {isInteractive(w) ? (
            w.steps.map((s) => {
              const files = s.files ?? [];
              const selected = selection.position === w.position && selection.stepId === s.id;
              return (
                <div
                  className="ini-files-group"
                  data-testid={`ini-files-${w.position}-${s.id}`}
                  data-selected={selected ? 'true' : undefined}
                  key={s.id}
                >
                  <div className="ini-files-group-head">
                    <span>{stepGroupHeading(s.id)}</span>
                    <span>{s.files_state}</span>
                  </div>
                  {files.length === 0 ? (
                    <p className="ini-files-none">no file yet</p>
                  ) : (
                    files.map((f) => (
                      <FileRow key={f.path} file={f} folder={folder} onOpen={setOpened} />
                    ))
                  )}
                </div>
              );
            })
          ) : (
            <div className="ini-files-group">
              {w.run_id === null ? (
                <p className="ini-files-none">not started</p>
              ) : (
                <>
                  {(w.files ?? []).map((f) => (
                    <FileRow key={f.path} file={f} folder={folder} onOpen={setOpened} />
                  ))}
                  <a className="ini-files-all" href={`/workflows/${w.run_id}`}>
                    {AUTO_FILES_LINK}
                  </a>
                </>
              )}
            </div>
          )}
        </div>
      ))}
      {opened ? (
        <ArtifactModal
          runId={opened.runId}
          path={opened.path}
          run={null}
          folder={folder}
          onClose={() => setOpened(null)}
        />
      ) : null}
    </section>
  );
}
