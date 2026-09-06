/**
 * `src/islands/TemplateDiagram.tsx` — the Templates screen's stateful wrapper (3.6).
 *
 * Unlike `Diagram`, this island subscribes to a store, runs an effect and calls the API, so
 * it cannot be rendered in `environment: 'node'` any more than `TemplateEditor` can — the
 * same constraint `project-form-island.test.ts` and `template-editor-island.test.ts`
 * document. What it holds that *is* pure is the label the picture announces itself with, and
 * that is exported and covered here; the wiring is proven in a real browser by
 * `tests/e2e/template-diagram.spec.ts`.
 */
import { describe, expect, it } from 'vitest';

import TemplateDiagram, { diagramAriaLabel } from '../../src/islands/TemplateDiagram';

describe('the TemplateDiagram island', () => {
  it('is exported as the function component [version].astro mounts with client:load', () => {
    expect(typeof TemplateDiagram).toBe('function');
  });
});

describe('diagramAriaLabel', () => {
  it('names the Template, the version, and how many steps are drawn', () => {
    expect(diagramAriaLabel('demo', 1, 2)).toBe('template demo v1 · 2 steps');
  });

  it('counts an empty graph as zero steps rather than saying nothing', () => {
    expect(diagramAriaLabel('demo', 1, 0)).toBe('template demo v1 · 0 steps');
  });

  it('keeps a dotted or hyphenated name exactly as it was given', () => {
    expect(diagramAriaLabel('repo-init', 3, 5)).toBe('template repo-init v3 · 5 steps');
  });
});
