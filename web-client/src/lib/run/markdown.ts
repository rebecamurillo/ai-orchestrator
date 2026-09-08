/**
 * A small, allowlisted Markdown-to-blocks parser for the Question block (5.10, UX-DR9):
 * headings, lists and fenced code, nothing else. Link and image syntax (`[x](y)`, `![x](y)`)
 * is deliberately left unparsed — the binding rule reads "no images or links executed" — so
 * it prints as the literal characters the agent wrote, never a navigable `<a>`/loaded `<img>`.
 *
 * Returns data, not HTML: `QuestionBlock.tsx` renders each block as React elements built
 * from these strings, so nothing here (or there) ever calls `dangerouslySetInnerHTML` — a
 * `<script>` or an `on*=` attribute typed into a story file's `## Auto Run Result` prints as
 * inert escaped text, the same as any other word, by construction rather than by escaping.
 */

export type MdBlock =
  | { kind: 'heading'; level: number; text: string }
  | { kind: 'list'; items: string[] }
  | { kind: 'code'; text: string }
  | { kind: 'paragraph'; text: string };

const HEADING = /^(#{1,6})\s+(.*)$/;
const LIST_ITEM = /^[-*]\s+(.*)$/;
const FENCE = '```';

export function parseQuestionMarkdown(source: string): MdBlock[] {
  const lines = source.split('\n');
  const blocks: MdBlock[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i]!;
    if (line.trim() === '') {
      i += 1;
    } else if (HEADING.test(line)) {
      const [, hashes, text] = HEADING.exec(line)!;
      blocks.push({ kind: 'heading', level: hashes!.length, text: text!.trim() });
      i += 1;
    } else if (line.trim().startsWith(FENCE)) {
      i += 1;
      const code: string[] = [];
      while (i < lines.length && !lines[i]!.trim().startsWith(FENCE)) {
        code.push(lines[i]!);
        i += 1;
      }
      i += 1;
      blocks.push({ kind: 'code', text: code.join('\n') });
    } else if (LIST_ITEM.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length && LIST_ITEM.test(lines[i]!.trim())) {
        items.push(LIST_ITEM.exec(lines[i]!.trim())![1]!);
        i += 1;
      }
      blocks.push({ kind: 'list', items });
    } else {
      const para: string[] = [];
      while (
        i < lines.length &&
        lines[i]!.trim() !== '' &&
        !HEADING.test(lines[i]!) &&
        !lines[i]!.trim().startsWith(FENCE) &&
        !LIST_ITEM.test(lines[i]!.trim())
      ) {
        para.push(lines[i]!);
        i += 1;
      }
      blocks.push({ kind: 'paragraph', text: para.join(' ').trim() });
    }
  }
  return blocks;
}
