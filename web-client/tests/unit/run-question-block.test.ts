/**
 * `QuestionBlock.tsx` (5.10, UX-DR9): the whole `## Auto Run Result` section rendered from
 * `alert.reason`, the `Agent · {harness} · {model} · {ended_at}` eyebrow, and — the AC this
 * file exists to prove — no script or markup an agent's own story file might carry ever
 * becomes live HTML (`renderToStaticMarkup`, stateless).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import QuestionBlock from '../../src/components/run/QuestionBlock';
import type { AlertOut } from '../../src/lib/run/detail';

function alert(overrides: Partial<AlertOut> = {}): AlertOut {
  return {
    token: 'BLK',
    reason: '## Auto Run Result\n\nWhich database migration tool should this use?',
    park_kind: 'blocked',
    attribution: { harness: 'claude', model: 'claude-opus-4', ended_at: '2026-09-07T09:05:00Z' },
    ...overrides,
  };
}

describe('QuestionBlock', () => {
  it('shows the whole section and the eyebrow with agent attribution', () => {
    const html = renderToStaticMarkup(createElement(QuestionBlock, { alert: alert() }));

    expect(html).toContain('data-testid="wf-question"');
    expect(html).toContain('data-testid="wf-question-eyebrow"');
    expect(html).toContain('Agent · claude · claude-opus-4 · 2026-09-07T09:05:00Z');
    expect(html).toContain('Auto Run Result');
    expect(html).toContain('Which database migration tool should this use?');
  });

  it('reads em dashes for a missing attribution part', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, {
        alert: alert({ attribution: { harness: null, model: null, ended_at: null } }),
      }),
    );

    expect(html).toContain('Agent · — · — · —');
  });

  it('reads em dashes throughout when there is no attribution at all', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, { alert: alert({ attribution: null }) }),
    );

    expect(html).toContain('Agent · — · — · —');
  });

  it('renders three paragraphs, one per blank-line-separated section', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, {
        alert: alert({ reason: 'first paragraph\n\nsecond paragraph\n\nthird paragraph' }),
      }),
    );

    expect(html.match(/<p>/g)?.length).toBe(3);
  });

  it('never executes a script tag typed into the reason — no live <script> in the output', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, {
        alert: alert({ reason: '<script>window.hacked = true;</script> ignored text' }),
      }),
    );

    expect(html).not.toContain('<script>');
    expect(html).toContain('&lt;script&gt;');
  });

  it('never turns markdown link/image syntax into a live <a> or <img>', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, {
        alert: alert({ reason: '[click me](javascript:alert(1)) and ![x](javascript:alert(1))' }),
      }),
    );

    expect(html).not.toContain('<a ');
    expect(html).not.toContain('<img');
    expect(html).toContain('[click me](javascript:alert(1))');
  });

  it('renders a fenced code block inside <pre><code>', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, { alert: alert({ reason: '```\nnpm test\n```' }) }),
    );

    expect(html).toContain('<pre><code>npm test</code></pre>');
  });

  it('renders a list item per bullet', () => {
    const html = renderToStaticMarkup(
      createElement(QuestionBlock, { alert: alert({ reason: '- postgres\n- sqlite' }) }),
    );

    expect(html).toContain('<li>postgres</li>');
    expect(html).toContain('<li>sqlite</li>');
  });
});
