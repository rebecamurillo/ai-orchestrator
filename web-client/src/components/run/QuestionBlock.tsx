/**
 * The Question block (5.10, UX-DR9, `DESIGN.md`): for `alert.park_kind === 'blocked'`, the
 * eyebrow `Agent · {harness} · {model} · {ended_at}` then the whole `## Auto Run Result`
 * section (`alert.reason`) rendered from `parseQuestionMarkdown` — headings, lists, fenced
 * and inline code, plain paragraphs, nothing else. No `[text](url)`/`![alt](url)` handling
 * anywhere in this file: that syntax prints as the literal text an agent wrote, never a
 * clickable link or a loaded image (the binding rule's own "no images or links executed").
 *
 * Stateless (`renderToStaticMarkup`); every string here comes from `MdBlock`/`AttributionOut`
 * values, so React's own text-node escaping is the only thing between an untrusted story
 * file and this markup — no `dangerouslySetInnerHTML` anywhere in this module.
 */
import type { ReactNode } from 'react';

import type { AlertOut } from '../../lib/run/detail';
import { questionEyebrow } from '../../lib/run/detail';
import { parseQuestionMarkdown, type MdBlock } from '../../lib/run/markdown';

interface Props {
  alert: AlertOut;
}

/** Inline `` `code` `` spans within one block's text, split on backticks and alternated —
 * still plain React children, never HTML. */
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

export default function QuestionBlock({ alert }: Props) {
  const blocks = parseQuestionMarkdown(alert.reason ?? '');
  return (
    <div className="wf-question" data-testid="wf-question">
      <p className="wf-question-eyebrow" data-testid="wf-question-eyebrow">
        {questionEyebrow(alert.attribution)}
      </p>
      <div className="wf-question-body">
        {blocks.map((block, index) => renderBlock(block, index))}
      </div>
    </div>
  );
}
