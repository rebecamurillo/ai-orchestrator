/** Story 10.4 (2026-11-26): the initiative link and the type on the Run page header. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import Header from '../../src/components/run/Header';
import type { RunDetailOut } from '../../src/lib/run/detail';

const INI = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

function detail(overrides: Partial<RunDetailOut> = {}): RunDetailOut {
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
    gate_record: [],
    admitted_signals: ['cancel'],
    summary: null,
    ...overrides,
  };
}

function render(d: RunDetailOut): string {
  const now = new Date('2026-09-07T09:01:00Z').getTime();
  return renderToStaticMarkup(createElement(Header, { detail: d, token: 'RUN', now }));
}

describe('Header initiative', () => {
  it('AC4: shows the initiative link and the type', () => {
    const html = render(
      detail({
        template_type: 'auto',
        initiative: { id: INI, position: 2, slug: 'site', step: null, workflow_count: 2 },
      }),
    );
    expect(html).toContain('data-testid="wf-initiative-tag"');
    expect(html).toContain(`href="/initiatives/${INI}"`);
    expect(html).toContain('site · workflow 2 of 2');
    expect(html).toContain('data-testid="wf-template-type"');
    expect(html).toContain('AUTO · CLAUDE');
  });

  it('reads INTERACTIVE for an interactive Run', () => {
    expect(render(detail({ template_type: 'interactive' }))).toContain('>INTERACTIVE<');
  });

  it('an unlinked header has no initiative tag', () => {
    expect(render(detail())).not.toContain('wf-initiative-tag');
  });
});
