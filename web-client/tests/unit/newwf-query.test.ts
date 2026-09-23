import { describe, expect, it } from 'vitest';

import { formStateToQuery, parseFormStateFromQuery } from '../../src/lib/newwf/query';
import { defaultFormState, withInput, withTemplate } from '../../src/lib/newwf/state';
import {
  OPTIONAL_INPUT_DEFAULT,
  OPTIONAL_INPUT_TEMPLATE,
  catalogWithDefaulted,
  fixtureCatalog,
} from './newwf-catalog-fixture';

describe('parseFormStateFromQuery', () => {
  it('defaults to initiative with every other field blank, for an empty query', () => {
    expect(parseFormStateFromQuery('', fixtureCatalog())).toEqual(
      defaultFormState(fixtureCatalog()),
    );
  });

  it('reads the brief’s own four prefill keys', () => {
    const state = parseFormStateFromQuery(
      'template=epic&project=p1&repository=r1&branch=main',
      fixtureCatalog(),
    );

    expect(state.template).toBe('epic');
    expect(state.projectId).toBe('p1');
    expect(state.repositoryId).toBe('r1');
    expect(state.baseBranch).toBe('main');
  });

  it('falls back to initiative for an unknown or missing template name', () => {
    expect(parseFormStateFromQuery('template=story', fixtureCatalog()).template).toBe('initiative');
    expect(parseFormStateFromQuery('template=', fixtureCatalog()).template).toBe('initiative');
  });

  it('reads a template’s own inputs under the in_ prefix, scoped to that template', () => {
    const state = parseFormStateFromQuery(
      'template=epic&in_branch=chore/x&in_spec_folder=specs/&in_initiative_folder=ignored',
      fixtureCatalog(),
    );

    expect(state.inputs).toEqual({ branch: 'chore/x', spec_folder: 'specs/' });
  });

  it('reads harness, model, budget, re_review and estimate', () => {
    const state = parseFormStateFromQuery(
      'harness=claude&model=opus&budget=10&re_review=1&estimate=4',
      fixtureCatalog(),
    );

    expect(state.harness).toBe('claude');
    expect(state.model).toBe('opus');
    expect(state.budgetUsd).toBe('10');
    expect(state.reReviewDone).toBe(true);
    expect(state.manualEstimateH).toBe('4');
  });

  it('reads re_review as false for anything but the literal "1"', () => {
    expect(parseFormStateFromQuery('re_review=true', fixtureCatalog()).reReviewDone).toBe(false);
    expect(parseFormStateFromQuery('', fixtureCatalog()).reReviewDone).toBe(false);
  });
});

describe('formStateToQuery', () => {
  it('round-trips the default state to the template key alone', () => {
    const query = formStateToQuery(defaultFormState(fixtureCatalog()), fixtureCatalog());

    expect(query.toString()).toBe('template=initiative');
    expect(parseFormStateFromQuery(query, fixtureCatalog())).toEqual(
      defaultFormState(fixtureCatalog()),
    );
  });

  it('round-trips a fully filled state, including template-scoped inputs', () => {
    let state = withTemplate(defaultFormState(fixtureCatalog()), 'epic', fixtureCatalog());
    state = withInput(state, 'branch', 'chore/x');
    state = withInput(state, 'spec_folder', 'specs/');
    state = {
      ...state,
      projectId: 'p1',
      repositoryId: 'r1',
      baseBranch: 'main',
      harness: 'claude',
      model: 'opus',
      budgetUsd: '10',
      reReviewDone: true,
      manualEstimateH: '4',
    };

    expect(
      parseFormStateFromQuery(formStateToQuery(state, fixtureCatalog()), fixtureCatalog()),
    ).toEqual(state);
  });

  it('drops an input that does not belong to the current template', () => {
    let state = withTemplate(defaultFormState(fixtureCatalog()), 'initiative', fixtureCatalog());
    state = withInput(state, 'initiative_folder', 'docs/x');
    state = withTemplate(state, 'repo-init', fixtureCatalog());

    const query = formStateToQuery(state, fixtureCatalog());

    expect(query.toString()).not.toContain('initiative_folder');
    expect(query.toString()).not.toContain('in_');
  });
});

/** The round-trip test compares a parse against `defaultFormState`, so both sides moved
 * together and an ignored `field.initial` stayed green. */
describe('a declared default and the query string', () => {
  it('seeds a field the link does not name', () => {
    const catalog = catalogWithDefaulted();

    const state = parseFormStateFromQuery(`template=${OPTIONAL_INPUT_TEMPLATE}`, catalog);

    expect(state.inputs.skill_dir).toBe(OPTIONAL_INPUT_DEFAULT);
  });

  it('lets the link override it', () => {
    const catalog = catalogWithDefaulted();

    const state = parseFormStateFromQuery(
      `template=${OPTIONAL_INPUT_TEMPLATE}&in_skill_dir=/elsewhere`,
      catalog,
    );

    expect(state.inputs.skill_dir).toBe('/elsewhere');
  });
});
