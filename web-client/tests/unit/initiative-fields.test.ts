/**
 * `InitiativeFields.tsx` (S7) — holds no state and runs no effect, so it renders outright
 * with `renderToStaticMarkup` in `environment: 'node'` (`NewWorkflowFields.tsx`'s own
 * precedent). Interaction is `tests/e2e/new-initiative.spec.ts`'s job.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import InitiativeFields from '../../src/components/initiative/InitiativeFields';
import { defaultFormState } from '../../src/lib/initiative/form';
import type { components } from '../../src/api/schema';

type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

const project: ProjectRead = {
  id: 'project-1',
  slug: 'project',
  name: 'Demo Project',
  context_text: '',
  context_paths: [],
  env_vars: [],
  log_prompt_content: false,
  repositories: [],
  runs: [],
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const repository: RepositoryOut = {
  id: 'repo-1',
  project_id: 'project-1',
  slug: 'hub',
  url: 'https://github.com/example/hub.git',
  default_branch: 'main',
  install_command: '',
  quality_gate_command: '',
  unit_test_command: '',
  test_globs: [],
  package_manager: 'other',
  clone_check: { status: 'ok', at: null, output: '', bmad_version: null },
  clone_check_lines: [],
  clone_check_hint: '',
  verify_skipped: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

function render(models: string[] = []): string {
  return renderToStaticMarkup(
    createElement(InitiativeFields, {
      state: defaultFormState(),
      projects: [project],
      repositories: [repository],
      models,
      onChange: () => {},
    }),
  );
}

describe('InitiativeFields', () => {
  it('offers the project and hub repository selects', () => {
    const markup = render();

    expect(markup).toContain('data-testid="newin-project"');
    expect(markup).toContain('Demo Project');
    expect(markup).toContain('data-testid="newin-repository"');
    expect(markup).toContain('>hub<');
  });

  it('renders folder, base branch and budget as text inputs', () => {
    const markup = render();

    expect(markup).toContain('data-testid="newin-folder"');
    expect(markup).toContain('data-testid="newin-base"');
    expect(markup).toContain('data-testid="newin-budget"');
  });

  it('renders the model field as free text with no probed models', () => {
    const markup = render([]);

    expect(markup).toMatch(/<input[^>]*data-testid="newin-model"/);
  });

  it('renders the model field as a select once models were probed', () => {
    const markup = render(['claude-opus-5']);

    expect(markup).toMatch(/<select[^>]*data-testid="newin-model"/);
    expect(markup).toContain('claude-opus-5');
  });
});
