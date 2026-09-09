/**
 * `AcceptBox.tsx` (6.6, FR-31, AD-17) — the protected-path stop's own control.
 *
 * Stateless, so the static render is the whole component. The one thing worth stating twice
 * is why there are no checkboxes: `use_cases/signals.py` refuses any list that is not exactly
 * the park's hits, because a partial accept would leave a flagged file unaccepted and park
 * the resumed check on it again. So the button always posts every path it lists, and the
 * per-file control the Operator gets is the diff link.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import AcceptBox from '../../src/components/run/AcceptBox';
import type { ProtectedHit } from '../../src/lib/run/accept';

const RUN_ID = '01a06887-79ab-759b-97a0-71c32ad939c2';
const HITS: ProtectedHit[] = [
  { path: 'tests/a.py', kind: 'modified' },
  { path: 'AGENTS.md', kind: 'added' },
];

function render(over: Partial<Parameters<typeof AcceptBox>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(AcceptBox, {
      runId: RUN_ID,
      hits: HITS,
      storyId: '4-1',
      onAccept: () => {},
      posting: false,
      ...over,
    }),
  );
}

/** Click the one element carrying a `data-testid`, wherever it is in the returned tree.
 * `vitest.config.ts` runs without a DOM, so the tree is walked rather than mounted — and
 * walking it by name rather than by child index keeps this assertion about the button. */
function clickByTestId(node: unknown, testId: string): void {
  const element = node as { props?: Record<string, unknown> } | null;
  const props = element?.props;
  if (!props) return;
  if (props['data-testid'] === testId) {
    (props['onClick'] as () => void)();
    return;
  }
  const children = props['children'];
  for (const child of Array.isArray(children) ? children : [children]) {
    clickByTestId(child, testId);
  }
}

describe('AcceptBox', () => {
  it('lists one row per file, each marked with what happened to it', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-accept-file-tests/a.py"');
    expect(html).toContain('data-testid="wf-accept-file-AGENTS.md"');
    expect(html.match(/wf-accept-mark/g)).toHaveLength(2);
  });

  it('links every file to its own unified diff, opened away from the polling screen', () => {
    const html = render();

    expect(html).toContain(`href="/api/runs/${RUN_ID}/files?path=AGENTS.md&amp;diff=1"`);
    expect(html).toContain('target="_blank"');
    expect(html).toContain('rel="noreferrer"');
  });

  it('names the story and every consequence before the button that accepts', () => {
    const html = render();

    expect(html).toContain('accepted for story 4-1;');
    expect(html).toContain('the check resumes on the same tree and the files ship with the story');
  });

  it('offers one button, which posts the whole list', () => {
    const html = render();

    expect(html).toContain('data-testid="wf-accept"');
    expect(html).toContain('Accept changes');
    expect(html).not.toContain('type="checkbox"');
  });

  it('hands the callback exactly the paths it listed', () => {
    let posted: string[] | null = null;
    const tree = AcceptBox({
      runId: RUN_ID,
      hits: HITS,
      storyId: '4-1',
      onAccept: (paths: string[]) => {
        posted = paths;
      },
      posting: false,
    });

    clickByTestId(tree, 'wf-accept');

    expect(posted).toEqual(['tests/a.py', 'AGENTS.md']);
  });

  it('refuses the button while a signal is in flight', () => {
    expect(render({ posting: true })).toContain('disabled=""');
  });

  it('escapes a path rather than rendering it as markup', () => {
    const html = render({ hits: [{ path: '<img src=x>', kind: 'added' }] });

    expect(html).not.toContain('<img src=x>');
    expect(html).toContain('&lt;img src=x&gt;');
  });
});
