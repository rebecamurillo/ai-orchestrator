import { describe, expect, it } from 'vitest';

import {
  CLONE_CHECK_FAILED_NOTE,
  READINESS_LINK_LABEL,
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
import { EMPTY_CATALOG } from '../../src/lib/newwf/catalog';
import {
  NO_HARNESS_TEMPLATE,
  OPTIONAL_INPUT_DEFAULT,
  OPTIONAL_INPUT_TEMPLATE,
  catalogWithDefaulted,
  catalogWithQuiet,
  fixtureCatalog,
} from './newwf-catalog-fixture';
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

/**
 * Revised 2026-09-22 (Operator instruction: templates come from `ROOT_TEMPLATES`). This
 * pinned `TEMPLATE_ORDER`, `DEFAULT_TEMPLATE` and `TEMPLATE_INPUT_FIELDS`, none of which
 * exist now; the rules that replaced them are pinned in `newwf-catalog.test.ts`.
 */
describe('the offered Templates come from the catalog', () => {
  it('opens on the catalog’s first Template, with its fields seeded', () => {
    const catalog = fixtureCatalog();

    expect(defaultFormState(catalog).template).toBe(catalog.names[0]);
    expect(Object.keys(defaultFormState(catalog).inputs)).toEqual(['initiative_folder']);
  });

  it('opens on no Template at all when the catalog offers none', () => {
    const empty = EMPTY_CATALOG;

    expect(defaultFormState(empty).template).toBe('');
    expect(defaultFormState(empty).inputs).toEqual({});
  });
});

/** `field.initial` is wired into three call sites and no fixture had a default, so replacing
 * it with `''` everywhere kept the suite green. */
describe('a Template input that declares a default', () => {
  it('opens at that default rather than blank', () => {
    const catalog = catalogWithDefaulted();

    expect(defaultFormState(catalog).template).not.toBe(OPTIONAL_INPUT_TEMPLATE);
    expect(
      withTemplate(defaultFormState(catalog), OPTIONAL_INPUT_TEMPLATE, catalog).inputs,
    ).toEqual({ spec_folder: '', skill_dir: OPTIONAL_INPUT_DEFAULT });
  });

  it('keeps what the Operator already typed instead of the default', () => {
    const catalog = catalogWithDefaulted();
    const typed = withInput(
      withTemplate(defaultFormState(catalog), OPTIONAL_INPUT_TEMPLATE, catalog),
      'skill_dir',
      '/elsewhere',
    );

    expect(withTemplate(typed, OPTIONAL_INPUT_TEMPLATE, catalog).inputs.skill_dir).toBe(
      '/elsewhere',
    );
  });
});

describe('isTemplateName', () => {
  it('accepts exactly what the catalog offers, and never a name outside it', () => {
    const catalog = fixtureCatalog();

    for (const name of catalog.names) {
      expect(isTemplateName(name, catalog)).toBe(true);
    }
    // `story` is called by another Template and is never started directly (FR-33); with the
    // list now configurable, what keeps it out is its absence from the catalog
    expect(isTemplateName('story', catalog)).toBe(false);
    expect(isTemplateName('ghost', catalog)).toBe(false);
    expect(isTemplateName('', catalog)).toBe(false);
  });
});

describe('withTemplate', () => {
  it('keeps every other field but resets the inputs to the new template’s own keys', () => {
    const state = withInput(
      defaultFormState(fixtureCatalog()),
      'initiative_folder',
      'docs/initiative',
    );
    const switched = withTemplate({ ...state, projectId: 'p1' }, 'epic', fixtureCatalog());

    expect(switched.template).toBe('epic');
    expect(switched.projectId).toBe('p1');
    expect(switched.inputs).toEqual({ branch: '', spec_folder: '' });
  });
});

describe('withInput', () => {
  it('sets one input key without disturbing the others', () => {
    const state = withInput(
      withTemplate(defaultFormState(fixtureCatalog()), 'epic', fixtureCatalog()),
      'branch',
      'chore/x',
    );
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
    const state = withInput(defaultFormState(fixtureCatalog()), 'initiative_folder', 'docs/x');

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
    expect(preflightBody(defaultFormState(fixtureCatalog()), []).template_version).toBeNull();
  });
});

describe('runBody', () => {
  const templates = [
    { name: 'initiative', description: null, latest_version: 2, versions: [1, 2] },
  ];

  it('is null while a required field is missing', () => {
    expect(runBody(defaultFormState(fixtureCatalog()), templates)).toBeNull();
  });

  it('is null while the Template’s version is unresolved', () => {
    const state = {
      ...defaultFormState(fixtureCatalog()),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'main',
      budgetUsd: '10',
    };

    expect(runBody(state, [])).toBeNull();
  });

  it('builds the full request once every required field is set', () => {
    const state = {
      ...defaultFormState(fixtureCatalog()),
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

/**
 * Revised 2026-09-22 (Operator instruction). These pinned `usesHarness('repo-init') === false`
 * from a rule that named the Template. The rule is now "declares a `harness` input", and
 * `repo-init` declares one and has a `uses: agent` step, so hiding the list was wrong.
 */
describe('usesHarness', () => {
  it('is true for every Template that declares a harness input', () => {
    const catalog = catalogWithQuiet();

    expect(usesHarness('initiative', catalog)).toBe(true);
    expect(usesHarness('epic', catalog)).toBe(true);
    expect(usesHarness('repo-init', catalog)).toBe(true);
  });

  it('is false for one that declares none', () => {
    expect(usesHarness(NO_HARNESS_TEMPLATE, catalogWithQuiet())).toBe(false);
  });
});

describe('withTemplate — the harness it carries', () => {
  it('clears a chosen harness when switching to a Template that dispatches none', () => {
    const catalog = catalogWithQuiet();
    const state = { ...defaultFormState(catalog), harness: 'claude' };

    expect(withTemplate(state, NO_HARNESS_TEMPLATE, catalog).harness).toBe('');
  });

  it('keeps it when switching between two templates that dispatch one', () => {
    const catalog = catalogWithQuiet();
    const state = { ...defaultFormState(catalog), harness: 'claude' };

    expect(withTemplate(state, 'epic', catalog).harness).toBe('claude');
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
    const state = {
      ...defaultFormState(fixtureCatalog()),
      projectId: 'p1',
      repositoryId: 'r-other',
    };

    expect(reconcileInitial(state, projects, [], fixtureCatalog()).repositoryId).toBe('');
  });

  it('keeps a repository that does belong to it, and seeds the base branch from it', () => {
    const repo = repository({ id: 'r1', default_branch: 'trunk' });
    const projects = [project({ id: 'p1', repositories: [repo] })];
    const state = { ...defaultFormState(fixtureCatalog()), projectId: 'p1', repositoryId: 'r1' };

    const reconciled = reconcileInitial(state, projects, [], fixtureCatalog());

    expect(reconciled.repositoryId).toBe('r1');
    expect(reconciled.baseBranch).toBe('trunk');
  });

  it('never replaces a base branch the link already named', () => {
    const repo = repository({ id: 'r1', default_branch: 'trunk' });
    const projects = [project({ id: 'p1', repositories: [repo] })];
    const state = {
      ...defaultFormState(fixtureCatalog()),
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'release/1',
    };

    expect(reconcileInitial(state, projects, [], fixtureCatalog()).baseBranch).toBe('release/1');
  });

  it('drops a harness that is not enabled — a disabled one is not selectable', () => {
    const state = { ...defaultFormState(fixtureCatalog()), harness: 'claude' };

    expect(reconcileInitial(state, [], [disabled], fixtureCatalog()).harness).toBe('');
  });

  it('keeps an enabled harness', () => {
    const state = { ...defaultFormState(fixtureCatalog()), harness: 'codex' };

    expect(reconcileInitial(state, [], [enabled], fixtureCatalog()).harness).toBe('codex');
  });

  // Revised 2026-09-22 (Operator instruction): `repo-init` declares a harness input, so the
  // Template with no harness list is now one that declares none.
  it('drops even an enabled harness for a Template whose form has no harness list', () => {
    const catalog = catalogWithQuiet();
    const state = {
      ...withTemplate(defaultFormState(catalog), NO_HARNESS_TEMPLATE, catalog),
      harness: 'codex',
    };

    expect(reconcileInitial(state, [], [enabled], catalog).harness).toBe('');
  });
});
