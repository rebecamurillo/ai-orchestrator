import { describe, expect, it } from 'vitest';

import { formStateToQuery, parseFormStateFromQuery } from '../../src/lib/newwf/query';
import { defaultFormState, withInput, withTemplate } from '../../src/lib/newwf/state';

describe('parseFormStateFromQuery', () => {
  it('defaults to initiative with every other field blank, for an empty query', () => {
    expect(parseFormStateFromQuery('')).toEqual(defaultFormState());
  });

  it('reads the brief’s own four prefill keys', () => {
    const state = parseFormStateFromQuery('template=epic&project=p1&repository=r1&branch=main');

    expect(state.template).toBe('epic');
    expect(state.projectId).toBe('p1');
    expect(state.repositoryId).toBe('r1');
    expect(state.baseBranch).toBe('main');
  });

  it('falls back to initiative for an unknown or missing template name', () => {
    expect(parseFormStateFromQuery('template=story').template).toBe('initiative');
    expect(parseFormStateFromQuery('template=').template).toBe('initiative');
  });

  it('reads a template’s own inputs under the in_ prefix, scoped to that template', () => {
    const state = parseFormStateFromQuery(
      'template=epic&in_branch=chore/x&in_spec_folder=specs/&in_initiative_folder=ignored',
    );

    expect(state.inputs).toEqual({ branch: 'chore/x', spec_folder: 'specs/' });
  });

  it('reads harness, model, budget, re_review and estimate', () => {
    const state = parseFormStateFromQuery(
      'harness=claude&model=opus&budget=10&re_review=1&estimate=4',
    );

    expect(state.harness).toBe('claude');
    expect(state.model).toBe('opus');
    expect(state.budgetUsd).toBe('10');
    expect(state.reReviewDone).toBe(true);
    expect(state.manualEstimateH).toBe('4');
  });

  it('reads re_review as false for anything but the literal "1"', () => {
    expect(parseFormStateFromQuery('re_review=true').reReviewDone).toBe(false);
    expect(parseFormStateFromQuery('').reReviewDone).toBe(false);
  });
});

describe('formStateToQuery', () => {
  it('round-trips the default state to the template key alone', () => {
    const query = formStateToQuery(defaultFormState());

    expect(query.toString()).toBe('template=initiative');
    expect(parseFormStateFromQuery(query)).toEqual(defaultFormState());
  });

  it('round-trips a fully filled state, including template-scoped inputs', () => {
    let state = withTemplate(defaultFormState(), 'epic');
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

    expect(parseFormStateFromQuery(formStateToQuery(state))).toEqual(state);
  });

  it('drops an input that does not belong to the current template', () => {
    let state = withTemplate(defaultFormState(), 'initiative');
    state = withInput(state, 'initiative_folder', 'docs/x');
    state = withTemplate(state, 'repo-init');

    const query = formStateToQuery(state);

    expect(query.toString()).not.toContain('initiative_folder');
    expect(query.toString()).not.toContain('in_');
  });
});
