/** `Header` with the Run label as its title (epic 3 story 3, AC1 and the AC4 actions slot). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import Header from '../../src/components/run/Header';
import RecalculateControl from '../../src/components/run/RecalculateControl';
import type { RunDetailOut } from '../../src/lib/run/detail';
import { metaLine } from '../../src/lib/run/detail';

const LABEL = 'familio familio-snake-v2 bench-v1-staged 2026-11-10 10:23';

function detail(over: Partial<RunDetailOut['run']> = {}): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'done',
      admitted_signals: [],
      branch: 'feat/snake-v2-y3f',
      label: LABEL,
      label_set_by_operator: false,
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
      ...over,
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
    admitted_signals: [],
    summary: null,
  } as unknown as RunDetailOut;
}

const NOW = Date.parse('2026-09-07T09:01:00Z');
const html = (d: RunDetailOut, extra: Record<string, unknown> = {}) =>
  renderToStaticMarkup(createElement(Header, { detail: d, token: 'DON', now: NOW, ...extra }));

describe('Header title', () => {
  it('shows the label as the title and moves the branch to the front of the meta line', () => {
    const d = detail();
    const out = html(d);
    expect(out).toMatch(/data-testid="wf-title"[^>]*>familio familio-snake-v2/);
    expect(out).not.toContain('wf-branch');
    expect(out).toContain(
      `data-testid="wf-meta"><span class="wf-meta-branch">feat/snake-v2-y3f</span> · ${metaLine(d)}`,
    );
  });

  it('falls back to the branch when the payload has no label', () => {
    const out = html(detail({ label: undefined }));
    expect(out).toMatch(/data-testid="wf-title"[^>]*>feat\/snake-v2-y3f</);
  });
});

describe('Header actions', () => {
  const control = (status: string) =>
    createElement(RecalculateControl, {
      status,
      versions: [],
      calc: null,
      calcError: null,
      onConfirm: () => {},
    });

  it('renders the actions slot after the meta line', () => {
    const out = html(detail(), { actions: control('done') });
    expect(out).toContain('wf-header-actions');
    expect(out).toContain('RECALCULATE METRICS');
    expect(out.indexOf('wf-header-actions')).toBeGreaterThan(out.indexOf('wf-meta'));
  });

  it('has no recalculate button for a running Run', () => {
    const out = html(detail({ status: 'running' }), { actions: control('running') });
    expect(out).not.toContain('RECALCULATE METRICS');
  });

  it('has no actions block without actions', () => {
    expect(html(detail())).not.toContain('wf-header-actions');
  });
});
