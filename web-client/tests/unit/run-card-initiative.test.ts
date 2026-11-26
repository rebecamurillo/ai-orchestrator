/** Story 10.4 (2026-11-26): the initiative tag, the stretched link and the type eyebrow on a Board card. */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RunCard from '../../src/components/RunCard';
import type { components } from '../../src/api/schema';
import { cardHref, cardStepText, cardTypeText } from '../../src/lib/board/format';

type CardOut = components['schemas']['CardOut'];

const INI = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: 'run-1',
    token: 'RUN',
    status: 'running',
    park_kind: null,
    branch: 'epics/1',
    project_name: 'demo',
    repository_slug: 'demo-repo',
    current_step_label: 'build',
    harness: 'claude',
    template: 'initiative',
    version: 1,
    progress: null,
    kind_label: null,
    age_seconds: 60,
    needs_you_since: null,
    ...overrides,
  };
}

function render(overrides: Partial<CardOut> = {}): string {
  return renderToStaticMarkup(createElement(RunCard, { card: card(overrides) }));
}

const linked = {
  id: INI,
  position: 1,
  slug: 'website-recruiter-inbound',
  step: 'ux',
  workflow_count: 2,
};

describe('RunCard initiative tag', () => {
  it('AC1: an auto linked card reads AUTO · CLAUDE with a tag link and one card link', () => {
    const html = render({ template_type: 'auto', initiative: linked });
    expect(html).toContain('AUTO · CLAUDE');
    expect(html).toMatch(
      new RegExp(
        `<a[^>]*href="/initiatives/${INI}"[^>]*data-testid="board-initiative-tag"|<a[^>]*data-testid="board-initiative-tag"[^>]*href="/initiatives/${INI}"`,
      ),
    );
    expect(html).toContain('website-recruiter-inbound');
    expect(html.match(/run-card-link/g)).toHaveLength(1);
    expect(html).toMatch(
      /<a[^>]*class="run-card-link"[^>]*href="\/workflows\/run-1"|<a[^>]*href="\/workflows\/run-1"[^>]*class="run-card-link"/,
    );
  });

  it('AC2: an interactive linked card opens the initiative and reads your turn', () => {
    const html = render({
      template_type: 'interactive',
      attention: 'your_turn',
      initiative: linked,
    });
    expect(html).toContain('INTERACTIVE');
    expect(html).toContain(`href="/initiatives/${INI}?workflow=1"`);
    expect(html).toContain('ux · your turn');
  });

  it('AC3: an unlinked card is an article with no tag', () => {
    const html = render();
    expect(html).not.toContain('board-initiative-tag');
    expect(html).toMatch(/^<article class="run-card" data-testid="board-card-run-1"/);
    expect(html).toContain('build');
  });

  it('never nests an anchor in an anchor', () => {
    const html = render({ template_type: 'auto', initiative: linked });
    expect(html).not.toMatch(/<a [^>]*>(?:(?!<\/a>).)*<a /);
  });
});

describe('card helpers', () => {
  it('cardTypeText', () => {
    expect(cardTypeText('interactive', 'claude')).toBe('INTERACTIVE');
    expect(cardTypeText('auto', 'claude')).toBe('AUTO · CLAUDE');
    expect(cardTypeText('auto', null)).toBe('AUTO');
    expect(cardTypeText(null, 'codex')).toBe('AUTO · CODEX');
    expect(cardTypeText(undefined, null)).toBe('AUTO');
  });

  it('cardHref', () => {
    expect(cardHref(card({ template_type: 'interactive', initiative: linked }))).toBe(
      `/initiatives/${INI}?workflow=1`,
    );
    expect(cardHref(card({ template_type: 'interactive' }))).toBe('/workflows/run-1');
    expect(cardHref(card({ template_type: 'auto', initiative: linked }))).toBe('/workflows/run-1');
  });

  it('cardStepText', () => {
    const base = { template_type: 'interactive', attention: 'your_turn' } as const;
    expect(cardStepText(card({ ...base, initiative: linked }))).toBe('ux · your turn');
    expect(
      cardStepText(card({ template_type: 'auto', attention: 'your_turn', initiative: linked })),
    ).toBe('build');
    expect(cardStepText(card({ ...base, initiative: { ...linked, step: null } }))).toBe('build');
    expect(cardStepText(card({ ...base }))).toBe('build');
  });
});
