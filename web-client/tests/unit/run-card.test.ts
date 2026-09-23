/**
 * `RunCard.tsx` (4.14) holds no state and runs no effect, so it renders outright in
 * `environment: 'node'` with `renderToStaticMarkup` (`PreflightLines.tsx`'s own precedent).
 * JSX stays out of this file because `vitest.config.ts` collects `.test.ts` only.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RunCard from '../../src/components/RunCard';
import type { components } from '../../src/api/schema';

type CardOut = components['schemas']['CardOut'];

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: '11111111-1111-1111-1111-111111111111',
    token: 'RUN',
    status: 'running',
    park_kind: null,
    branch: 'epics/1',
    project_name: 'demo',
    repository_slug: 'demo-repo',
    current_step_label: 'epic 1 · story 3-2 · build',
    harness: 'claude',
    template: 'initiative',
    version: 1,
    progress: { epics_done: 1, epics_total: 2, stories_done: 5, stories_total: 8, links: 1 },
    kind_label: null,
    age_seconds: 60,
    needs_you_since: null,
    ...overrides,
  };
}

function render(overrides: Partial<CardOut> = {}): string {
  return renderToStaticMarkup(createElement(RunCard, { card: card(overrides) }));
}

describe('RunCard', () => {
  it('links the whole card to its Run detail', () => {
    const markup = render({ id: 'run-1' });
    expect(markup).toContain('data-testid="board-card-run-1"');
    expect(markup).toContain('href="/workflows/run-1"');
  });

  it('renders the fixed field order: token, branch, project/repository, step, progress, template, age', () => {
    const markup = render();
    const tokenAt = markup.indexOf('>RUN<');
    const branchAt = markup.indexOf('epics/1');
    const metaAt = markup.indexOf('demo-repo');
    const stepAt = markup.indexOf('build');
    const progressAt = markup.indexOf('1/2 epics');
    const templateAt = markup.indexOf('initiative v1');
    const ageAt = markup.indexOf('1m');

    expect(tokenAt).toBeGreaterThan(-1);
    expect(branchAt).toBeGreaterThan(tokenAt);
    expect(metaAt).toBeGreaterThan(branchAt);
    expect(stepAt).toBeGreaterThan(metaAt);
    expect(progressAt).toBeGreaterThan(stepAt);
    expect(templateAt).toBeGreaterThan(progressAt);
    expect(ageAt).toBeGreaterThan(templateAt);
  });

  it('shows the harness name, tertiary', () => {
    expect(render({ harness: 'claude' })).toContain('claude');
  });

  it('omits the harness segment when none is set', () => {
    expect(render({ harness: null })).not.toContain('run-card-harness');
  });

  it('shows repo-init in place of progress when progress is null', () => {
    expect(render({ progress: null, kind_label: 'repo-init' })).toContain('repo-init');
  });

  it('marks a cancelled card with the CAN token and the word cancelled', () => {
    const markup = render({ token: 'CAN', status: 'cancelled' });
    expect(markup).toContain('>CAN<');
    expect(markup).toContain('cancelled');
  });

  it('carries the left rule for a BLK card, in the needs-you signal', () => {
    const markup = render({ token: 'BLK', status: 'needs_you' });
    expect(markup).toContain('data-left-rule="needs-you"');
  });

  it('carries the left rule for an ERR card, in the failed signal', () => {
    const markup = render({ token: 'ERR', status: 'failed' });
    expect(markup).toContain('data-left-rule="failed"');
  });

  it('carries no left rule for a CHK card', () => {
    const markup = render({ token: 'CHK', status: 'needs_you' });
    expect(markup).not.toContain('data-left-rule');
  });

  it('renders the initiative badge when the card is a member (S8)', () => {
    const markup = render({ initiative: 'q4', initiative_role: 'epic' });
    expect(markup).toContain('run-card-initiative');
    expect(markup).toContain('q4 · epic');
  });

  it('omits the initiative badge for a Run started on its own', () => {
    expect(render({ initiative: null })).not.toContain('run-card-initiative');
  });

  it('colours the age amber only when the card is an aged BLK/CHK (>48h)', () => {
    const ageSpan = /<span class="run-card-age"[^>]*>/;
    const aged = render({ token: 'BLK', status: 'needs_you', age_seconds: 49 * 3600 });
    const fresh = render({ token: 'BLK', status: 'needs_you', age_seconds: 3600 });

    expect(ageSpan.exec(aged)?.[0]).toContain('data-signal="needs-you"');
    expect(ageSpan.exec(fresh)?.[0]).not.toContain('data-signal');
  });
});
