/**
 * The artifact viewer/editor modal (1-6, FR-19, UX-DR9): the second modal in the product,
 * after `CancelModal`. Presents a RENDERED · SOURCE · RAW toggle, a download control, and —
 * when the run is parked without a terminal session and the path is not a list file — an
 * Edit + Save path through `PUT /runs/{id}/files`. Save errors are surfaced verbatim so git
 * output is never lost. The modal follows `CancelModal`'s own structure: outer div (fixed
 * inset, flex centre), backdrop div (fixed inset, opacity 0.8, onClick=onClose), panel div
 * (relative, raised surface, border). Never a native `<dialog>`.
 */
import { useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';

import { EditorState } from '@codemirror/state';
import { EditorView } from '@codemirror/view';
import { yaml } from '@codemirror/lang-yaml';

import { api } from '../../api/client';
import type { components } from '../../api/schema';
import type { RunDetailOut } from '../../lib/run/detail';
import {
  canEditFile,
  editHint,
  isFile,
  isListFile,
  isMarkdown,
  readOnlyLine,
} from '../../lib/run/artifacts';
import { parseQuestionMarkdown, type MdBlock } from '../../lib/run/markdown';
import FileEditor from './FileEditor';

type ProblemDetail = components['schemas']['ProblemDetail'];
type RunSummary = RunDetailOut['run'];
type Tab = 'rendered' | 'source' | 'raw';

interface Props {
  runId: string;
  path: string;
  run: RunSummary;
  folder: string;
  onClose: () => void;
  onSaved?: () => void;
}

function renderInline(text: string, keyPrefix: string): ReactNode[] {
  const parts = text.split('`');
  return parts.map((part, index) =>
    index % 2 === 1 ? <code key={`${keyPrefix}-${index}`}>{part}</code> : part,
  );
}

function renderBlock(block: MdBlock, key: number): ReactNode {
  if (block.kind === 'heading') {
    const level = Math.min(Math.max(block.level, 1), 6);
    const Heading = `h${level}` as 'h1' | 'h2' | 'h3' | 'h4' | 'h5' | 'h6';
    return <Heading key={key}>{renderInline(block.text, `h${key}`)}</Heading>;
  }
  if (block.kind === 'list') {
    return (
      <ul key={key}>
        {block.items.map((item, index) => (
          <li key={index}>{renderInline(item, `li${key}-${index}`)}</li>
        ))}
      </ul>
    );
  }
  if (block.kind === 'code') {
    return (
      <pre key={key}>
        <code>{block.text}</code>
      </pre>
    );
  }
  return <p key={key}>{renderInline(block.text, `p${key}`)}</p>;
}

export default function ArtifactModal({ runId, path, run, folder, onClose, onSaved }: Props) {
  const [content, setContent] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('rendered');
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const cmRef = useRef<HTMLDivElement>(null);

  // Fetch the file content on mount and whenever the path or runId changes.
  useEffect(() => {
    let cancelled = false;
    async function load(): Promise<void> {
      const { data, error } = await api.GET('/runs/{run_id}/files', {
        params: { path: { run_id: runId }, query: { path } },
      });
      if (cancelled || error || !data || !isFile(data)) return;
      setContent(data.content);
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [runId, path]);

  // Mount a read-only CodeMirror view for YAML files in RENDERED mode.
  useEffect(() => {
    if (tab !== 'rendered' || editing || content === null || !cmRef.current) return;
    if (!path.endsWith('.yaml') && !path.endsWith('.yml')) return;
    const view = new EditorView({
      state: EditorState.create({
        doc: content,
        extensions: [yaml(), EditorState.readOnly.of(true), EditorView.lineWrapping],
      }),
      parent: cmRef.current,
    });
    return () => {
      view.destroy();
    };
  }, [tab, content, editing, path]);

  /** Trigger a client-side download of the current content as a plain-text file. */
  function download(): void {
    if (content === null) return;
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = path.split('/').at(-1) ?? 'file';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  async function save(text: string): Promise<void> {
    setSaving(true);
    setSaveError(null);
    try {
      const { data, error } = await api.PUT('/runs/{run_id}/files', {
        params: { path: { run_id: runId } },
        body: { path, content: text },
      });
      if (error || !data) {
        const e = error as ProblemDetail | undefined;
        setSaveError(e?.detail ?? e?.title ?? 'save failed');
        return;
      }
      setContent(text);
      setEditing(false);
      onSaved?.();
    } finally {
      setSaving(false);
    }
  }

  const canEdit = canEditFile(run, path, folder);
  const listFile = isListFile(folder, path);
  const isYaml = path.endsWith('.yaml') || path.endsWith('.yml');
  const basename = path.split('/').at(-1) ?? path;

  function renderBody(): ReactNode {
    if (content === null) return null;

    if (tab !== 'rendered') {
      return <pre className="wf-artifact-modal-body">{content}</pre>;
    }

    if (isMarkdown(path)) {
      return (
        <div className="wf-artifact-modal-body">
          {parseQuestionMarkdown(content).map((block, index) => renderBlock(block, index))}
        </div>
      );
    }

    if (isYaml) {
      // CodeMirror mounts into this div via the useEffect above.
      return <div className="wf-artifact-modal-body" ref={cmRef} />;
    }

    return <pre className="wf-artifact-modal-body">{content}</pre>;
  }

  return (
    <div className="wf-artifact-modal">
      <div className="wf-artifact-modal-backdrop" onClick={onClose} />
      <div
        className="wf-artifact-modal-panel"
        data-testid="wf-artifact-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="wf-artifact-modal-title"
      >
        <div className="wf-artifact-modal-header">
          <span id="wf-artifact-modal-title" className="wf-artifact-modal-path">
            {basename}
          </span>
          <button
            type="button"
            className="wf-artifact-modal-close"
            onClick={onClose}
            aria-label="Close"
          >
            ×
          </button>
        </div>
        <div className="wf-artifact-modal-tabs">
          <button
            type="button"
            data-testid="wf-artifact-modal-tab-rendered"
            aria-pressed={tab === 'rendered'}
            onClick={() => {
              setTab('rendered');
              setEditing(false);
            }}
          >
            RENDERED
          </button>
          <button
            type="button"
            data-testid="wf-artifact-modal-tab-source"
            aria-pressed={tab === 'source'}
            onClick={() => {
              setTab('source');
              setEditing(false);
            }}
          >
            SOURCE
          </button>
          <button
            type="button"
            data-testid="wf-artifact-modal-tab-raw"
            aria-pressed={tab === 'raw'}
            onClick={() => {
              setTab('raw');
              setEditing(false);
            }}
          >
            RAW
          </button>
          <button type="button" className="wf-artifact-modal-download" onClick={download}>
            Download {basename}
          </button>
        </div>
        <div data-testid="wf-file-viewer">
          {!editing ? renderBody() : null}
          {editing && content !== null ? (
            <div className="wf-artifact-modal-body">
              <FileEditor
                path={path}
                initialContent={content}
                branch={run.branch}
                saving={saving}
                error={null}
                onSave={(text) => void save(text)}
                onCancel={() => {
                  setEditing(false);
                  setSaveError(null);
                }}
              />
              <p className="wf-artifact-modal-hint">{editHint(run.branch)}</p>
              {saveError ? (
                <div className="wf-artifact-modal-error" data-testid="wf-artifact-modal-error-zone">
                  {saveError}
                </div>
              ) : null}
            </div>
          ) : null}
          {listFile ? (
            <p className="wf-artifact-modal-readonly" data-testid="artifacts-readonly">
              {readOnlyLine(run.plan_ref)}
            </p>
          ) : null}
          {!listFile && canEdit && !editing ? (
            <button
              type="button"
              className="wf-signal wf-artifact-modal-edit-btn"
              data-testid="wf-artifacts-edit"
              onClick={() => {
                if (content !== null) {
                  setSaveError(null);
                  setEditing(true);
                }
              }}
            >
              Edit
            </button>
          ) : null}
        </div>
      </div>
    </div>
  );
}
