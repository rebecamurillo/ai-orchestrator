/** Story 11.1: InitiativeHeader (AC1, AC2). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import InitiativeHeader from '../../src/components/initiative/InitiativeHeader';
import { detail, workflow } from './initiative-fixtures';

const html = (d = detail(), actions?: string) =>
  renderToStaticMarkup(
    createElement(InitiativeHeader, {
      detail: d,
      actions: actions ? createElement('button', null, actions) : undefined,
    }),
  );

describe('InitiativeHeader', () => {
  it('renders the crumb, state line, position, tags and meta line', () => {
    const out = html();
    expect(out).toContain('data-testid="ini-header"');
    expect(out).toContain('href="/initiatives"');
    expect(out).toContain('familio-dessin-v2');
    expect(out).toContain('running · spec · ux · your turn');
    expect(out).toContain('workflow 1 of 2 · spec · step 3 of 6');
    expect(out).toContain('Familio');
    expect(out).toContain('familio-web');
    expect(out).toContain('familio-api');
    expect(out).toContain(
      'hub hub-repo · folder initiatives/familio-dessin-v2 · package orchestrator-default (2 workflows, fixed 2026-11-20) · created 2026-11-19T09:00:00Z',
    );
  });

  it('shows the token chip for the status', () => {
    const out = html();
    expect(out).toContain('RUN');
    expect(out).toContain('data-signal="run"');
  });

  it('ends the state line with the reason instead of your turn', () => {
    const out = html(detail({ reason: 'budget reached' }));
    expect(out).toContain('running · spec · ux · budget reached');
    expect(out).not.toContain('your turn');
  });

  it('says agent answering', () => {
    expect(html(detail({ attention: 'answering' }))).toContain('ux · agent answering');
  });

  it('drops the step part for an auto current workflow', () => {
    const d = detail({ current_position: 2, workflow: 'build', current_step: null });
    const out = html(d);
    expect(out).toContain('workflow 2 of 2 · build');
    expect(out).not.toContain('step 3 of 6');
  });

  it('never truncates the meta line', () => {
    expect(html()).not.toContain('…');
    expect(html()).not.toContain('text-overflow');
  });

  it('renders the actions slot', () => {
    expect(html(detail(), 'Cancel initiative')).toContain('Cancel initiative');
  });

  it('omits the hub part when the API sends none', () => {
    const d = detail({ hub: null, workflows: [workflow('spec', 1)] });
    expect(html(d)).toContain('folder initiatives/familio-dessin-v2');
  });
});
