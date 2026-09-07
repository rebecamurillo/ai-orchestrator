import { describe, expect, it } from 'vitest';

import {
  CLONE_CHECK_FAILED_NOTE,
  DEFAULT_TEMPLATE,
  READINESS_LINK_LABEL,
  TEMPLATE_INPUT_FIELDS,
  TEMPLATE_ORDER,
  checkSlug,
  cloneCheckNote,
  defaultFormState,
  harnessLine,
  harnessLineText,
  isTemplateName,
  latestVersion,
  lineWord,
  preflightBody,
  readinessHref,
  reconcileInitial,
  repositoriesFor,
  repositoryById,
  runBody,
  usesHarness,
  withInput,
  withTemplate,
} from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';

type RepositoryOut = components['schemas']['RepositoryOut'];
type ProjectRead = components['schemas']['ProjectRead'];
type HarnessOut = components['schemas']['HarnessOut'];

function repository(overrides: Partial<RepositoryOut> = {}): RepositoryOut {
  return {
    id: 'repo-1',
    project_id: 'project-1',
    slug: 'repo',
    url: 'https://github.com/example/repo.git',
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
    ...overrides,
  };
}

function project(overrides: Partial<ProjectRead> = {}): ProjectRead {
  return {
    id: 'project-1',
    slug: 'project',
    name: 'Project',
    context_text: '',
    context_paths: [],
    env_vars: [],
    log_prompt_content: false,
    repositories: [],
    runs: [],
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
    ...overrides,
  };
}

describe('TEMPLATE_ORDER and TEMPLATE_INPUT_FIELDS', () => {
  it('lists the three root Templates, initiative first, story never', () => {
    expect(TEMPLATE_ORDER).toEqual(['initiative', 'epic', 'repo-init']);
    expect(DEFAULT_TEMPLATE).toBe('initiative');
    expect(TEMPLATE_ORDER).not.toContain('story');
  });

  it('gives initiative one input, epic two, repo-init none', () => {
    expect(TEMPLATE_INPUT_FIELDS.initiative.map((field) => field.key)).toEqual([
      'initiative_folder',
    ]);
    expect(TEMPLATE_INPUT_FIELDS.epic.map((field) => field.key)).toEqual(['branch', 'spec_folder']);
    expect(TEMPLATE_INPUT_FIELDS['repo-init']).toEqual([]);
  });
});

describe('isTemplateName', () => {
  it('accepts the three fixed names and refuses anything else', () => {
    expect(isTemplateName('initiative')).toBe(true);
    expect(isTemplateName('epic')).toBe(true);
    expect(isTemplateName('repo-init')).toBe(true);
    expect(isTemplateName('story')).toBe(false);
    expect(isTemplateName('')).toBe(false);
  });
});

describe('withTemplate', () => {
  it('keeps every other field but resets the inputs to the new template’s own keys', () => {
    const state = withInput(defaultFormState(), 'initiative_folder', 'docs/initiative');
    const switched = withTemplate({ ...state, projectId: 'p1' }, 'epic');

    expect(switched.template).toBe('epic');
    expect(switched.projectId).toBe('p1');
    expect(switched.inputs).toEqual({ branch: '', spec_folder: '' });
  });
});

describe('withInput', () => {
  it('sets one input key without disturbing the others', () => {
    const state = withInput(withTemplate(defaultFormState(), 'epic'), 'branch', 'chore/x');
    const next = withInput(state, 'spec_folder', 'specs/');

    expect(next.inputs).toEqual({ branch: 'chore/x', spec_folder: 'specs/' });
  });
});

describe('repositoriesFor and repositoryById', () => {
  it('reads the Repositories of the selected Project, and none for no selection', () => {
    const repo = repository();
    const projects = [project({ id: 'p1', repositories: [repo] })];

    expect(repositoriesFor(projects, 'p1')).toEqual([repo]);
    expect(repositoriesFor(projects, 'unknown')).toEqual([]);
    expect(repositoryById([repo], repo.id)).toBe(repo);
    expect(repositoryById([repo], 'missing')).toBeUndefined();
  });
});

describe('cloneCheckNote', () => {
  it('names the failed-check note only when the check failed', () => {
    expect(
      cloneCheckNote(
        repository({ clone_check: { status: 'failed', at: null, output: '', bmad_version: null } }),
      ),
    ).toBe(CLONE_CHECK_FAILED_NOTE);
    expect(cloneCheckNote(repository())).toBeUndefined();
    expect(cloneCheckNote(undefined)).toBeUndefined();
  });
});

describe('latestVersion', () => {
  it('reads a Template’s latest_version by name, or undefined when unknown', () => {
    const templates = [
      { name: 'initiative', description: null, latest_version: 3, versions: [1, 2, 3] },
    ];

    expect(latestVersion(templates, 'initiative')).toBe(3);
    expect(latestVersion(templates, 'epic')).toBeUndefined();
  });
});

describe('preflightBody', () => {
  it('carries every field, template_version resolved and inputs passed through', () => {
    const templates = [{ name: 'initiative', description: null, latest_version: 1, versions: [1] }];
    const state = withInput(defaultFormState(), 'initiative_folder', 'docs/x');

    expect(preflightBody(state, templates)).toEqual({
      template_name: 'initiative',
      template_version: 1,
      project_id: null,
      repository_id: null,
      base_branch: null,
      inputs: { initiative_folder: 'docs/x' },
      harness: null,
      model: null,
      budget_usd: null,
      re_review_done: false,
    });
  });

  it('carries template_version null when the name is not yet resolved', () => {
    expect(preflightBody(defaultFormState(), []).template_version).toBeNull();
  });
});

describe('runBody', () => {
  const templates = [
    { name: 'initiative', description: null, latest_version: 2, versions: [1, 2] },
  ];

  it('is null while a required field is missing', () => {
    expect(runBody(defaultFormState(), templates)).toBeNull();
  });

  it('is null while the Template’s version is unresolved', () => {
    const state = {
      ...defaultFormState(),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'main',
      budgetUsd: '10',
    };

    expect(runBody(state, [])).toBeNull();
  });

  it('builds the full request once every required field is set', () => {
    const state = {
      ...defaultFormState(),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'main',
      budgetUsd: '10',
      harness: 'claude',
      model: 'opus',
      manualEstimateH: '4',
      reReviewDone: true,
    };

    expect(runBody(state, templates)).toEqual({
      template_name: 'initiative',
      template_version: 2,
      project_id: 'p1',
      repository_id: 'r1',
      base_branch: 'main',
      budget_usd: '10',
      inputs: { initiative_folder: '' },
      harness: 'claude',
      model: 'opus',
      manual_estimate_h: '4',
      re_review_done: true,
    });
  });
});

describe('lineWord', () => {
  it('renders the four words, never an icon', () => {
    expect(lineWord('ok')).toBe('ok');
    expect(lineWord('warn')).toBe('!');
    expect(lineWord('fail')).toBe('x');
    expect(lineWord('skip')).toBe('—');
  });
});

describe('checkSlug', () => {
  it('lower-kebabs a check name for a test-id', () => {
    expect(checkSlug('origin reachable')).toBe('origin-reachable');
  });

  it('folds every non-alphanumeric run to one dash, so the id needs no escaping', () => {
    expect(checkSlug('SPEC.md')).toBe('spec-md');
    expect(checkSlug('stories.yaml')).toBe('stories-yaml');
    expect(checkSlug('  what  will   run  ')).toBe('what-will-run');
  });
});

describe('harnessLine', () => {
  function harness(overrides: Partial<HarnessOut> = {}): HarnessOut {
    return {
      name: 'claude',
      enabled: false,
      last_readiness_at: null,
      failing_check: null,
      version_pin: '1.0.0',
      ...overrides,
    };
  }

  it('renders the disabled line with no readiness run, verbatim', () => {
    expect(harnessLine(harness())).toBe(
      'claude · disabled: no readiness run · last readiness — · re-run readiness',
    );
  });

  it('renders a named failing check and a readiness time', () => {
    expect(
      harnessLine(
        harness({ failing_check: 'version pin', last_readiness_at: '2026-09-06T14:03:09Z' }),
      ),
    ).toBe(
      'claude · disabled: version pin · last readiness 2026-09-06 14:03:09 · re-run readiness',
    );
  });

  it('renders an enabled harness with no disabled reason', () => {
    expect(harnessLine(harness({ enabled: true }))).toBe(
      'claude · enabled · last readiness — · re-run readiness',
    );
  });

  it('splits the line so the re-run readiness half can be rendered as a control', () => {
    expect(harnessLineText(harness())).toBe(
      'claude · disabled: no readiness run · last readiness — · ',
    );
    expect(`${harnessLineText(harness())}${READINESS_LINK_LABEL}`).toBe(harnessLine(harness()));
  });
});

describe('readinessHref', () => {
  it('points at the harness readiness endpoint through the proxy, name encoded', () => {
    expect(readinessHref('claude')).toBe('/api/harnesses/claude/readiness');
    expect(readinessHref('a/b')).toBe('/api/harnesses/a%2Fb/readiness');
  });
});

describe('usesHarness', () => {
  it('is false only for repo-init, which runs no agent step', () => {
    expect(usesHarness('initiative')).toBe(true);
    expect(usesHarness('epic')).toBe(true);
    expect(usesHarness('repo-init')).toBe(false);
  });
});

describe('withTemplate — the harness it carries', () => {
  it('clears a chosen harness when switching to repo-init', () => {
    const state = { ...defaultFormState(), harness: 'claude' };

    expect(withTemplate(state, 'repo-init').harness).toBe('');
  });

  it('keeps it when switching between two templates that dispatch one', () => {
    const state = { ...defaultFormState(), harness: 'claude' };

    expect(withTemplate(state, 'epic').harness).toBe('claude');
  });
});

describe('reconcileInitial', () => {
  const enabled: HarnessOut = {
    name: 'codex',
    enabled: true,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '0.152.1',
  };
  const disabled: HarnessOut = { ...enabled, name: 'claude', enabled: false };

  it('drops a repository that does not belong to the named project', () => {
    const projects = [project({ id: 'p1', repositories: [repository({ id: 'r1' })] })];
    const state = { ...defaultFormState(), projectId: 'p1', repositoryId: 'r-other' };

    expect(reconcileInitial(state, projects, []).repositoryId).toBe('');
  });

  it('keeps a repository that does belong to it, and seeds the base branch from it', () => {
    const repo = repository({ id: 'r1', default_branch: 'trunk' });
    const projects = [project({ id: 'p1', repositories: [repo] })];
    const state = { ...defaultFormState(), projectId: 'p1', repositoryId: 'r1' };

    const reconciled = reconcileInitial(state, projects, []);

    expect(reconciled.repositoryId).toBe('r1');
    expect(reconciled.baseBranch).toBe('trunk');
  });

  it('never replaces a base branch the link already named', () => {
    const repo = repository({ id: 'r1', default_branch: 'trunk' });
    const projects = [project({ id: 'p1', repositories: [repo] })];
    const state = {
      ...defaultFormState(),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'release/1',
    };

    expect(reconcileInitial(state, projects, []).baseBranch).toBe('release/1');
  });

  it('drops a harness that is not enabled — a disabled one is not selectable', () => {
    const state = { ...defaultFormState(), harness: 'claude' };

    expect(reconcileInitial(state, [], [disabled]).harness).toBe('');
  });

  it('keeps an enabled harness', () => {
    const state = { ...defaultFormState(), harness: 'codex' };

    expect(reconcileInitial(state, [], [enabled]).harness).toBe('codex');
  });

  it('drops even an enabled harness for repo-init, whose form has no harness list', () => {
    const state = { ...withTemplate(defaultFormState(), 'repo-init'), harness: 'codex' };

    expect(reconcileInitial(state, [], [enabled]).harness).toBe('');
  });
});
