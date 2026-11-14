/** The New workflow `label` field and its request body (epic 3 story 3, AC8). */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import NewWorkflowFields from '../../src/components/NewWorkflowFields';
import { defaultFormState, runBody, withInput, type FormState } from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';
import { fixtureCatalog } from './newwf-catalog-fixture';

type ProjectRead = components['schemas']['ProjectRead'];

const NOW = Date.parse('2026-11-10T10:23:40Z');
const catalog = fixtureCatalog();
const projects = [{ id: 'p1', name: 'familio' } as ProjectRead];
const templates = [
  { name: defaultFormState(catalog).template, description: null, latest_version: 2, versions: [2] },
];

function filled(label: string): FormState {
  let state: FormState = {
    ...defaultFormState(catalog),
    projectId: 'p1',
    repositoryId: 'r1',
    baseBranch: 'main',
    label,
  };
  state = withInput(state, 'initiative_folder', 'docs/familio-snake-v2');
  return state;
}

function render(state: FormState, now: number | undefined = NOW): string {
  return renderToStaticMarkup(
    createElement(NewWorkflowFields, {
      state,
      catalog,
      projects,
      repositories: [],
      note: undefined,
      onChange: () => {},
      now,
    }),
  );
}

describe('the label field', () => {
  it('shows the computed default as its placeholder', () => {
    const markup = render({ ...filled(''), template: 'initiative' });
    expect(markup).toContain('LABEL (optional)');
    expect(markup).toContain('data-testid="newwf-label"');
    expect(markup).toContain('maxLength="120"');
    expect(markup).toContain(
      `placeholder="default: familio familio-snake-v2 ${filled('').template} 2026-11-10 10:23"`,
    );
  });

  it('has a blank project word while no project is chosen, and defaults now', () => {
    const markup = render({ ...defaultFormState(catalog), projectId: '' }, undefined);
    expect(markup).toContain('placeholder="default: ');
  });
});

describe('runBody label', () => {
  it('carries the trimmed label when typed', () => {
    expect(runBody(filled('  snake round 1 '), templates)?.label).toBe('snake round 1');
  });
  it('carries no label key when blank', () => {
    expect(runBody(filled('   '), templates)).not.toHaveProperty('label');
  });
});
