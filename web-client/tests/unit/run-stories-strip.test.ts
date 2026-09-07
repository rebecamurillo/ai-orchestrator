/**
 * `StoriesStrip.tsx` (4.15): one section per epic, one cell per story, states carried on
 * `data-state` (`renderToStaticMarkup`, stateless).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import StoriesStrip from '../../src/components/run/StoriesStrip';
import type { StoryCellOut } from '../../src/lib/run/detail';

describe('StoriesStrip', () => {
  it('groups cells by epic and carries each state', () => {
    const stories: StoryCellOut[] = [
      { epic_index: 1, story_id: '4-1', state: 'done' },
      { epic_index: 1, story_id: '4-2', state: 'current' },
      { epic_index: 2, story_id: '4-3', state: 'future' },
      { epic_index: 2, story_id: '4-4', state: 'skipped' },
    ];
    const html = renderToStaticMarkup(createElement(StoriesStrip, { stories }));

    expect(html).toContain('data-testid="wf-stories"');
    expect(html).toContain('epic 1 · 1/2');
    expect(html).toContain('epic 2 · 0/2');
    expect(html).toContain('data-testid="wf-story-4-1"');
    expect(html).toContain('data-state="done"');
    expect(html).toContain('data-state="current"');
    expect(html).toContain('data-state="future"');
    expect(html).toContain('data-state="skipped"');
  });

  it('renders nothing for a Template with no Story frame (repo-init)', () => {
    expect(renderToStaticMarkup(createElement(StoriesStrip, { stories: [] }))).toBe('');
  });
});
