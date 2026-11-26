import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { expect, it } from 'vitest';

import InitiativeColumn from '../../src/components/initiatives/InitiativeColumn';
import type { InitiativeRow } from '../../src/lib/initiatives/format';

const NOW = Date.parse('2026-11-26T12:00:00Z');
const row = (status: InitiativeRow['status'], slug: string): InitiativeRow =>
  ({
    id: slug,
    slug,
    name: slug,
    status,
    line: '',
    progress: '',
    project_name: 'p',
    repo_tag: [],
    updated_at: new Date(NOW).toISOString(),
    workflow: 'spec',
    workflows: [],
  }) as unknown as InitiativeRow;

const render = (props: Record<string, unknown>) =>
  renderToStaticMarkup(createElement(InitiativeColumn, { nowMs: NOW, ...props } as never));

it('head words and count line without need you', () => {
  const html = render({
    testId: 'initiatives-col-spec',
    name: 'spec',
    type: 'interactive',
    items: [row('running', 'a')],
  });
  expect(html).toContain('data-testid="initiatives-col-spec"');
  expect(html).toContain('SPEC');
  expect(html).toContain('INTERACTIVE');
  expect(html).toContain('1 ongoing');
  expect(html).not.toContain('need you');
  expect(html).not.toContain('needs-you');
});

it('count line with need you', () => {
  const html = render({
    testId: 'c',
    name: 'build',
    type: 'auto',
    items: [row('running', 'a'), row('waiting for her', 'b')],
  });
  expect(html).toContain('2 ongoing');
  expect(html).toContain('1 need you');
  expect(html).toContain('AUTO');
});

it('empty shows a dash', () => {
  const html = render({ testId: 'c', name: 'deploy', type: 'auto', items: [] });
  expect(html).toContain('—');
});

it('done column: head only, footer rendered', () => {
  const html = render({
    testId: 'initiatives-col-done',
    name: 'DONE · LAST 30 DAYS',
    items: [],
    footer: createElement('button', null, 'show'),
  });
  expect(html).toContain('DONE · LAST 30 DAYS');
  expect(html).not.toContain('ongoing');
  expect(html).toContain('<button>show</button>');
});
