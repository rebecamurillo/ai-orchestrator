/**
 * The MODEL field becomes a select when the harness publishes models (FR-27, story 7.3).
 *
 * `local` dispatches to models the host itself serves, and their aliases are this instance's
 * own `LOCAL_MODELS` — so `GET /harnesses` states them per harness and the New workflow offers
 * exactly those. A free-text name for that harness is a Run that pre-flights clean, starts, and
 * fails at its first model call, because the Gateway has no route for it.
 *
 * `tests/unit/newwf-fields.test.ts` and `newwf-state.test.ts` are frozen and cover the field as
 * 4.13 shipped it: a text input, for every harness there was. Both still pass unchanged — the
 * prop is optional and an absent list renders exactly that text input — so this is a sibling
 * module for the shape that did not exist when they were written.
 *
 * Rendered with `renderToStaticMarkup` in `environment: 'node'`, the precedent `newwf-fields`
 * and `Diagram` already set: the component holds no state and runs no effect. Interaction is
 * `tests/e2e/new-workflow.spec.ts`'s job, in a real browser.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import NewWorkflowFields from '../../src/components/NewWorkflowFields';
import { defaultFormState, modelsFor, withHarness } from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';

type HarnessOut = components['schemas']['HarnessOut'];

const LOCAL_MODELS = ['local-coder', 'local-general'];

function harness(name: string, models?: string[]): HarnessOut {
  return {
    name,
    enabled: true,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '1.18.26',
    ...(models === undefined ? {} : { models }),
  };
}

const HARNESSES: HarnessOut[] = [
  harness('claude', []),
  harness('codex', []),
  harness('local', LOCAL_MODELS),
];

function render(models: string[] | undefined, model = ''): string {
  return renderToStaticMarkup(
    createElement(NewWorkflowFields, {
      state: { ...defaultFormState(), model },
      projects: [],
      repositories: [],
      models,
      note: undefined,
      onChange: () => {},
    }),
  );
}

describe('modelsFor', () => {
  it('answers the models the named harness publishes', () => {
    expect(modelsFor(HARNESSES, 'local')).toEqual(LOCAL_MODELS);
  });

  it('answers none for a harness that takes a free-text model name', () => {
    expect(modelsFor(HARNESSES, 'claude')).toEqual([]);
  });

  it('answers none while no harness is selected at all', () => {
    expect(modelsFor(HARNESSES, '')).toEqual([]);
  });

  it('answers none for a backend that predates the field', () => {
    // `models` is optional in the generated type (AD-3), so an older backend reads exactly
    // like a harness with none: the text field, as before
    expect(modelsFor([harness('local')], 'local')).toEqual([]);
  });
});

describe('withHarness', () => {
  it('keeps a model the newly selected harness still offers', () => {
    const state = { ...defaultFormState(), harness: 'local', model: 'local-coder' };

    expect(withHarness(state, 'local', HARNESSES).model).toBe('local-coder');
  });

  it('clears a model the newly selected harness does not offer', () => {
    // a select cannot show a value that is not one of its options: carrying the old string
    // would leave the control blank while the form still submitted it
    const state = { ...defaultFormState(), harness: 'claude', model: 'claude-opus-5' };

    expect(withHarness(state, 'local', HARNESSES).model).toBe('');
  });

  it('keeps a typed model when the new harness offers no list to check it against', () => {
    const state = { ...defaultFormState(), harness: 'local', model: 'local-coder' };

    expect(withHarness(state, 'claude', HARNESSES).model).toBe('local-coder');
  });

  it('records the harness that was selected, whichever way the model went', () => {
    expect(withHarness(defaultFormState(), 'local', HARNESSES).harness).toBe('local');
  });

  it('changes nothing else about the form', () => {
    const state = { ...defaultFormState(), budgetUsd: '40', baseBranch: 'main' };

    const next = withHarness(state, 'local', HARNESSES);

    expect({ ...next, harness: '', model: '' }).toEqual({ ...state, harness: '', model: '' });
  });
});

describe('the MODEL field', () => {
  it('is a select over exactly the models it was given', () => {
    const markup = render(LOCAL_MODELS);

    expect(markup).toContain('<select data-testid="newwf-model"');
    for (const model of LOCAL_MODELS) expect(markup).toContain(`value="${model}"`);
  });

  it('offers no model the instance does not serve', () => {
    expect(render(LOCAL_MODELS)).not.toContain('claude-opus-5');
  });

  it('still offers the harness default, as the empty option every select here uses', () => {
    expect(render(LOCAL_MODELS)).toContain('<option value="" selected="">—</option>');
  });

  it('marks the selected model as selected', () => {
    expect(render(LOCAL_MODELS, 'local-general')).toContain(
      '<option value="local-general" selected="">local-general</option>',
    );
  });

  it('is the text field for a harness that publishes no models', () => {
    const markup = render([]);

    expect(markup).toContain('data-testid="newwf-model"');
    expect(markup).toContain('placeholder="harness default"');
    expect(markup).not.toContain('<select data-testid="newwf-model"');
  });

  it('is the text field when the prop is absent altogether', () => {
    // the frozen `newwf-fields.test.ts` renders it exactly this way
    expect(render(undefined)).toContain('placeholder="harness default"');
  });

  it('carries no signal colour either way: a model list is nothing to report (NFR-6)', () => {
    for (const markup of [render(LOCAL_MODELS), render([])]) {
      expect(markup).not.toMatch(/amber|--red|status-err/);
    }
  });
});
