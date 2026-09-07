/**
 * `PreflightLines.tsx` (4.13) holds no state and runs no effect, so — like `Diagram.tsx`
 * (3.6) — it renders outright in `environment: 'node'` with `renderToStaticMarkup`. JSX
 * stays out of this file because `vitest.config.ts` collects `.test.ts` only.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import PreflightLines from '../../src/components/PreflightLines';
import type { components } from '../../src/api/schema';

type LineOut = components['schemas']['LineOut'];

function render(lines: LineOut[]): string {
  return renderToStaticMarkup(createElement(PreflightLines, { lines }));
}

describe('PreflightLines', () => {
  it('renders {word} · {check} · {text}, with ok as the plain word', () => {
    const markup = render([
      { check: 'origin reachable', status: 'ok', text: 'origin ok', fix: null },
    ]);

    expect(markup).toContain('data-testid="newwf-preflight-origin-reachable"');
    expect(markup).toContain('ok');
    expect(markup).toContain('origin reachable');
    expect(markup).toContain('origin ok');
  });

  it('renders warn as the plain "!" word, uncoloured', () => {
    const markup = render([
      { check: 'branch', status: 'warn', text: 'branch is unusual', fix: null },
    ]);

    expect(markup).not.toContain('data-signal="failed"');
    expect(markup).toContain('!');
  });

  it('renders fail as the coloured "x" word, with its fix as secondary text', () => {
    const markup = render([
      { check: 'harness', status: 'fail', text: 'claude is disabled', fix: 'enable claude first' },
    ]);

    expect(markup).toContain('data-signal="failed"');
    expect(markup).toContain('>x<');
    expect(markup).toContain('enable claude first');
  });

  it('renders skip as the "—" word, never a fix line', () => {
    const markup = render([
      { check: 'clone check', status: 'skip', text: 'no repository chosen', fix: null },
    ]);

    expect(markup).toContain('—');
    // no fix supplied on a skip line, so the fix span is never rendered
    expect(markup).not.toContain('newwf-preflight-fix');
  });
});
