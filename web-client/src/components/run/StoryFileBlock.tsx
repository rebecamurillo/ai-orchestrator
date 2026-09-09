/**
 * The spec-checkpoint body's own planned-file view (6.2, FR-19, UX-DR10): the eyebrow, then
 * the planned story file rendered inline, read-only. `QuestionBlock.tsx`'s own block
 * renderer (headings, lists, fenced and inline code, plain paragraphs) is duplicated here
 * rather than imported — its `renderBlock`/`renderInline` are private to that module, and a
 * handful of pure lines is this codebase's own precedent for that (`run_views.py`'s module
 * doc; `AnswerBox`/`RejectBox` draw the same line). No `dangerouslySetInnerHTML`, same as
 * `QuestionBlock.tsx`: every string here is a plain React child.
 */
import type { ReactNode } from 'react';

import { parseQuestionMarkdown, type MdBlock } from '../../lib/run/markdown';

interface Props {
  eyebrow: string;
  content: string;
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

export default function StoryFileBlock({ eyebrow, content }: Props) {
  const blocks = parseQuestionMarkdown(content);
  return (
    <div className="wf-planned-file" data-testid="wf-planned-file">
      <p className="wf-planned-file-eyebrow" data-testid="wf-planned-file-eyebrow">
        {eyebrow}
      </p>
      <div className="wf-planned-file-body">
        {blocks.map((block, index) => renderBlock(block, index))}
      </div>
    </div>
  );
}
