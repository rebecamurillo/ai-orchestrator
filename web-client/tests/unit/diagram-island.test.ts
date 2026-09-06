/**
 * `src/islands/Diagram.tsx` — the reusable, read-only picture (3.6).
 *
 * The island holds no state and runs no effect, so unlike `TemplateEditor` it can be rendered
 * outright in `environment: 'node'`: `renderToStaticMarkup` is enough, and JSX stays out of
 * the file because `vitest.config.ts` collects `.test.ts` only.
 *
 * The golden renders are the story's own acceptance criteria — `epic@1`'s six nodes and its
 * one group, `story@1`'s agent step — asserted against the same graphs backend-api answers
 * for those two shipped files.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import Diagram from '../../src/islands/Diagram';
import { EMPTY, EPIC_GRAPH, STORY_GRAPH } from './diagram-fixtures';

/** The three signal hues `tokens.css` reserves, and the raw values behind them. */
const SIGNAL_TOKENS = ['--color-signal-run', '--color-signal-needs-you', '--color-signal-failed'];
const SIGNAL_VALUES = ['#4fb477', '#e4b33c', '#e05252'];

function render(graph: typeof EPIC_GRAPH, ariaLabel = 'template epic v1 · 6 steps'): string {
  return renderToStaticMarkup(createElement(Diagram, { graph, ariaLabel }));
}

describe('the Diagram island', () => {
  it('is exported as the function component the Templates screen mounts', () => {
    expect(typeof Diagram).toBe('function');
  });

  it('holds the picture in a slot of its own, under the screen test id', () => {
    expect(render(EPIC_GRAPH)).toContain('data-testid="templates-diagram"');
  });

  it('announces itself as one image, with the label it was given', () => {
    const markup = render(EPIC_GRAPH);

    expect(markup).toContain('role="img"');
    expect(markup).toContain('aria-label="template epic v1 · 6 steps"');
  });
});

describe("epic@1's golden render", () => {
  it('draws one box per node, each keyed on the node id', () => {
    const markup = render(EPIC_GRAPH);

    for (const id of ['checkout', 'baseline', 'stories.story', 'stories.after', 'push', 'link']) {
      expect(markup, id).toContain(`data-testid="diagram-node-${id}"`);
    }
  });

  it('draws the loop as one dashed box around its members', () => {
    expect(render(EPIC_GRAPH)).toContain('data-testid="diagram-group-stories"');
  });

  it('draws one connector per edge, so the sequence the picture exists to show is in it', () => {
    const markup = render(EPIC_GRAPH);

    for (const edge of EPIC_GRAPH.edges) {
      expect(markup, `${edge.from}->${edge.to}`).toContain(
        `data-testid="diagram-edge-${edge.from}-&gt;${edge.to}"`,
      );
    }
  });

  it('reads the call as story@1 under the eyebrow template, and the checkpoint as human', () => {
    const markup = render(EPIC_GRAPH);

    expect(markup).toContain('story@1');
    expect(markup).toContain('>template<');
    expect(markup).toContain('>human<');
  });

  it('carries no signal token and no amber or red value anywhere in the markup', () => {
    const markup = render(EPIC_GRAPH);

    for (const token of [...SIGNAL_TOKENS, ...SIGNAL_VALUES]) {
      expect(markup, token).not.toContain(token);
    }
    expect(markup).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
    expect(markup).not.toContain('style=');
  });
});

describe("story@1's golden render", () => {
  it('marks the build step as the one that dispatches a harness', () => {
    const markup = render(STORY_GRAPH, 'template story v1 · 4 steps');

    expect(markup).toMatch(/data-testid="diagram-node-build"[^>]*data-agent="true"/);
    expect(markup).toContain('>agent<');
  });
});

describe('the empty graph', () => {
  it('draws an SVG with the label it was given and no node at all', () => {
    const markup = render(EMPTY, 'template demo v1 · 0 steps');

    expect(markup).toContain('aria-label="template demo v1 · 0 steps"');
    expect(markup).not.toContain('data-testid="diagram-node-');
  });

  it('puts no NaN in the viewBox', () => {
    const markup = render(EMPTY, 'template demo v1 · 0 steps');

    expect(markup).not.toContain('NaN');
    expect(markup).toContain('viewBox="0 0 0 0"');
  });
});

describe('the diagram stylesheet', () => {
  /** The markup carries no colour — every one of them is in this file, which is therefore
   * the only place a signal hue could enter the picture. The e2e sweep reads computed styles
   * for the elements that are painted; this reads the decision itself, for all of them. */
  const css = readFileSync(
    fileURLToPath(new URL('../../src/styles/diagram.css', import.meta.url)),
    'utf8',
  );

  it('names no signal token: a Template has no status to report', () => {
    for (const token of SIGNAL_TOKENS) expect(css, token).not.toContain(token);
  });

  it('paints the picture from the hairlines, the greys, one ground and the accent', () => {
    const referenced = [...css.matchAll(/var\(\s*(--color-[a-z0-9-]+)/g)].map((match) => match[1]);

    expect([...new Set(referenced)].sort()).toEqual([
      '--color-accent',
      '--color-bg',
      '--color-line',
      '--color-line-strong',
      '--color-surface',
      '--color-text',
      '--color-text-secondary',
      '--color-text-tertiary',
    ]);
  });
});
