/**
 * `src/lib/run/markdown.ts` (5.10): the Question block's own allowlist Markdown parser —
 * headings, lists, fenced code, and plain paragraphs, blank lines dropped, everything else
 * (including link/image syntax) left as literal text.
 */
import { describe, expect, it } from 'vitest';

import { parseQuestionMarkdown } from '../../src/lib/run/markdown';

describe('parseQuestionMarkdown', () => {
  it('reads a heading, a paragraph, a list and a fenced code block in order', () => {
    const source = [
      '## Auto Run Result',
      '',
      'The migration needs a database choice.',
      '',
      '- postgres',
      '- sqlite',
      '',
      '```',
      'npm test',
      '```',
    ].join('\n');

    const blocks = parseQuestionMarkdown(source);

    expect(blocks).toEqual([
      { kind: 'heading', level: 2, text: 'Auto Run Result' },
      { kind: 'paragraph', text: 'The migration needs a database choice.' },
      { kind: 'list', items: ['postgres', 'sqlite'] },
      { kind: 'code', text: 'npm test' },
    ]);
  });

  it('joins multi-line paragraphs with a single space', () => {
    const blocks = parseQuestionMarkdown('line one\nline two');

    expect(blocks).toEqual([{ kind: 'paragraph', text: 'line one line two' }]);
  });

  it('drops blank lines between blocks', () => {
    const blocks = parseQuestionMarkdown('\n\nonly paragraph\n\n\n');

    expect(blocks).toEqual([{ kind: 'paragraph', text: 'only paragraph' }]);
  });

  it('is empty for an empty string', () => {
    expect(parseQuestionMarkdown('')).toEqual([]);
  });

  it('never recognises link or image syntax — it stays literal paragraph text', () => {
    const blocks = parseQuestionMarkdown('see [the docs](https://example.invalid) and ![x](y)');

    expect(blocks).toEqual([
      { kind: 'paragraph', text: 'see [the docs](https://example.invalid) and ![x](y)' },
    ]);
  });

  it('reads `*` list markers the same as `-`', () => {
    expect(parseQuestionMarkdown('* one\n* two')).toEqual([
      { kind: 'list', items: ['one', 'two'] },
    ]);
  });
});
