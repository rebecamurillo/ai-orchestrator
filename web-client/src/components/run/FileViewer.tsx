/**
 * The ARTIFACTS column's own read-only view (6.3, FR-19, UX-DR9): the selected file,
 * Markdown rendered minimally or plain text otherwise, and either the Edit control or the
 * list file's own read-only line in the one slot below it (never both).
 *
 * `QuestionBlock.tsx`'s own block renderer (headings, lists, fenced and inline code, plain
 * paragraphs) is duplicated here rather than imported — its `renderBlock`/`renderInline` are
 * private to that module, `StoryFileBlock.tsx`'s own precedent for this exact duplication
 * (its module doc names `AnswerBox`/`RejectBox` drawing the same line). No
 * `dangerouslySetInnerHTML`, same as every renderer this one is copied from: every string
 * here is a plain React child.
 */
import type { ReactNode } from 'react';

import { isMarkdown } from '../../lib/run/artifacts';
import { parseQuestionMarkdown, type MdBlock } from '../../lib/run/markdown';

interface Props {
  path: string;
  content: string;
  readOnlyLine: string | null;
  canEdit: boolean;
  editing: boolean;
  onEditToggle: () => void;
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

export default function FileViewer({
  path,
  content,
  readOnlyLine,
  canEdit,
  editing,
  onEditToggle,
}: Props) {
  return (
    <div className="wf-artifacts-viewer" data-testid="wf-file-viewer">
      <div className="wf-artifacts-viewer-body">
        {isMarkdown(path) ? (
          parseQuestionMarkdown(content).map((block, index) => renderBlock(block, index))
        ) : (
          <pre>{content}</pre>
        )}
      </div>
      {readOnlyLine ? (
        <p className="wf-artifacts-readonly" data-testid="artifacts-readonly">
          {readOnlyLine}
        </p>
      ) : null}
      {!readOnlyLine && canEdit && !editing ? (
        <button
          type="button"
          className="wf-signal wf-artifacts-edit"
          data-testid="wf-artifacts-edit"
          onClick={onEditToggle}
        >
          Edit
        </button>
      ) : null}
    </div>
  );
}
