import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import InitiativeCard from '../../src/components/initiatives/InitiativeCard';
import type { InitiativeRow } from '../../src/lib/initiatives/format';

const NOW = Date.parse('2026-11-26T12:00:00Z');
const item = (over: Partial<InitiativeRow>): InitiativeRow => ({
  attention: null,
  id: 'abc',
  line: 'ux · your turn · 14 turns',
  name: 'Initiative steps',
  position: 0,
  progress: '2 of 5 steps',
  project_id: 'p',
  project_name: 'Orchestrator',
  reason: '',
  repo_tag: ['ai-orchestrator', 'brain'],
  repository_id: 'r',
  slug: 'initiative-steps',
  status: 'running',
  step: 's',
  updated_at: new Date(NOW - 5 * 60_000).toISOString(),
  workflow: 'build',
  workflow_count: 3,
  workflows: [
    { workflow: 'spec', type: 'interactive', state: 'completed' },
    { workflow: 'build', type: 'auto', state: 'ongoing' },
    { workflow: 'deploy', type: 'auto', state: null },
  ],
  ...over,
});
const render = (i: InitiativeRow) =>
  renderToStaticMarkup(createElement(InitiativeCard, { item: i, nowMs: NOW }));

it('AC4: aged waiting item is amber everywhere', () => {
  const html = render(
    item({ status: 'waiting for her', updated_at: new Date(NOW - 49 * 3600_000).toISOString() }),
  );
  expect(html).toContain('data-left-rule="needs-you"');
  expect(html).toContain('BLK');
  expect(html).toMatch(/class="ini-card-token" data-signal="needs-you"/);
  expect(html).toMatch(/class="ini-card-line" data-signal="needs-you"/);
  expect(html).toMatch(/class="ini-card-age" data-signal="needs-you">2d 01h</);
});

it('AC4: running item carries no needs-you signal', () => {
  const html = render(item({}));
  expect(html).not.toContain('needs-you');
  expect(html).toContain('ux · your turn · 14 turns');
});

it('AC5: one link, fields in order', () => {
  const html = render(item({}));
  expect(html.startsWith('<a ')).toBe(true);
  expect(html).toContain('href="/initiatives/abc"');
  expect(html).toContain('data-testid="initiatives-card-initiative-steps"');
  expect(html).toContain('draggable="false"');
  const at = (s: string) => html.indexOf(s);
  const order = [
    at('RUN'),
    at('5m'),
    at('Initiative steps'),
    at('Orchestrator'),
    at('ai-orchestrator'),
    at('brain'),
    at('ux · your turn'),
    at('2 of 5 steps'),
    at('spec · completed'),
  ];
  expect(order.every((i) => i >= 0)).toBe(true);
  expect([...order].sort((a, b) => a - b)).toEqual(order);
  expect(html.replace(/<[^>]*>/g, '')).toContain('spec · completed ▸ build · ongoing ▸ deploy');
});

it('a young waiting item has no aged age signal but keeps the rule', () => {
  const html = render(item({ status: 'waiting for her' }));
  expect(html).toContain('data-left-rule="needs-you"');
  expect(html).toMatch(/class="ini-card-age">5m</);
});
