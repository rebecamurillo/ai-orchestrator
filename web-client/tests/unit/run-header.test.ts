/**
 * `Header.tsx` (4.15, UX-DR9): stateless, so it renders outright with `renderToStaticMarkup`
 * (`RunCard.tsx`'s own precedent).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import Header from '../../src/components/run/Header';
import type { RunDetailOut } from '../../src/lib/run/detail';

function detail(): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'running',
      admitted_signals: ['cancel'],
      branch: 'epics/1',
      budget_usd: '15',
      compare_urls: [],
      created_at: '2026-09-07T09:00:00Z',
      inputs: {},
      manual_estimate_h: null,
      plan_ref: null,
      project: 'p1',
      repository: 'r1',
      spend_usd: '0',
      template: 'initiative',
      terminal_session: false,
      version: 1,
      worktree_path: null,
      worktrees: [],
      accepted_paths: [],
    },
    header: {
      meta: {
        project: 'demo',
        repository: 'demo-repo',
        base_branch: 'main',
        folder: 'docs/initiative',
        template: 'initiative',
        version: 1,
        harness: 'claude',
        started_at: '2026-09-07T09:00:05Z',
        worktree_path: '/work/demo',
      },
    },
    alert: null,
    steps: [],
    stories: [],
    cost: {
      spent_usd: '0',
      budget_usd: '15',
      tokens_in: 0,
      tokens_out: 0,
      wall_clock_seconds: 0,
      active_seconds: 0,
      provisional: false,
      trace_url: null,
    },
    gate_record: [
      {
        id: 'g1',
        at: '2026-09-07T09:00:00Z',
        path: null,
        event: 'start',
        actor: 'machine',
        text: '',
        attempt_n: null,
      },
    ],
    admitted_signals: ['cancel'],
    summary: null,
  };
}

describe('Header', () => {
  it('carries the crumb, token, branch and meta testids, and no view toggle', () => {
    const now = new Date('2026-09-07T09:01:00Z').getTime();
    const html = renderToStaticMarkup(
      createElement(Header, { detail: detail(), token: 'RUN', now }),
    );

    expect(html).toContain('data-testid="wf-header"');
    expect(html).toContain('workflows / epics/1');
    expect(html).toContain('data-testid="wf-token"');
    expect(html).toContain('>RUN<');
    expect(html).toContain('epics/1');
    expect(html).toContain('data-testid="wf-meta"');
    expect(html).toContain('demo · demo-repo · main · docs/initiative · initiative v1 · claude');
    // 2026-09-24, run-diagram v3 (EXPERIENCE-v1 delta 21): the `DIAGRAM · DETAIL` toggle and
    // the `?view=diagram` redirect it pointed at are deleted, so the header has no toggle to
    // assert. What the toggle was here to prove — that the header states the run's identity
    // and its meta line unabridged — is asserted above and is unchanged.
    expect(html).not.toContain('wf-toggle-diagram');
  });

  it('colours the token by its own signal', () => {
    const html = renderToStaticMarkup(
      createElement(Header, { detail: detail(), token: 'BLK', now: Date.now() }),
    );

    expect(html).toContain('data-signal="needs-you"');
  });
});
