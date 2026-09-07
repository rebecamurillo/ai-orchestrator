/**
 * `NewWorkflowFields.tsx` (4.13) — the form's own fields, split out of `NewWorkflow.tsx` so
 * each file stays inside `web-client/AGENTS.md`'s "a component file ≤ 300 lines". It holds no
 * state and runs no effect, so it renders outright with `renderToStaticMarkup` in
 * `environment: 'node'` (the `Diagram.tsx` precedent). Interaction is
 * `tests/e2e/new-workflow.spec.ts`'s job.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import NewWorkflowFields from '../../src/components/NewWorkflowFields';
import { defaultFormState, withTemplate } from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';

type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

function render(
  state = defaultFormState(),
  projects: ProjectRead[] = [],
  repositories: RepositoryOut[] = [],
  note: string | undefined = undefined,
): string {
  return renderToStaticMarkup(
    createElement(NewWorkflowFields, { state, projects, repositories, note, onChange: () => {} }),
  );
}

describe('NewWorkflowFields', () => {
  it('offers the three root templates and never story', () => {
    const markup = render();

    expect(markup).toContain('value="initiative"');
    expect(markup).toContain('value="epic"');
    expect(markup).toContain('value="repo-init"');
    expect(markup).not.toContain('value="story"');
  });

  it('renders initiative’s one input, and epic’s two instead', () => {
    expect(render()).toContain('data-testid="newwf-input-initiative_folder"');

    const epic = render(withTemplate(defaultFormState(), 'epic'));
    expect(epic).toContain('data-testid="newwf-input-branch"');
    expect(epic).toContain('data-testid="newwf-input-spec_folder"');
    expect(epic).not.toContain('newwf-input-initiative_folder');
  });

  it('renders no template input at all for repo-init', () => {
    expect(render(withTemplate(defaultFormState(), 'repo-init'))).not.toContain('newwf-input-');
  });

  it('carries every test id the brief names for a field', () => {
    const markup = render();

    for (const id of [
      'newwf-template',
      'newwf-project',
      'newwf-repository',
      'newwf-base',
      'newwf-budget',
      'newwf-estimate',
      'newwf-rereview',
      'newwf-model',
    ]) {
      expect(markup, id).toContain(`data-testid="${id}"`);
    }
  });

  it('marks the model field with the harness-default placeholder the brief states', () => {
    expect(render()).toContain('placeholder="harness default"');
  });

  it('marks budget required, since a run cannot start without one', () => {
    expect(render()).toMatch(/data-testid="newwf-budget"[^>]*required|required[^>]*newwf-budget/);
  });

  it('renders the clone-check note beside the repository only when given one', () => {
    expect(render()).not.toContain('newwf-field-note');
    expect(render(defaultFormState(), [], [], 'clone check failed · new runs blocked')).toContain(
      'clone check failed · new runs blocked',
    );
  });
});
