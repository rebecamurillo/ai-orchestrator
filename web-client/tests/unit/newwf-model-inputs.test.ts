/**
 * Model-named Template inputs (spec-model-input-selectors, Operator decision 2026-10-30):
 * name matching, reset, reconcile, and select-vs-input rendering — on a catalog this file owns.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import NewWorkflowFields from '../../src/components/NewWorkflowFields';
import type { components } from '../../src/api/schema';
import { buildCatalog, fieldsFor, isModelInput } from '../../src/lib/newwf/catalog';
import { formStateToQuery } from '../../src/lib/newwf/query';
import {
  defaultFormState,
  reconcileModelInputs,
  resetModelInputs,
  withInput,
  withTemplate,
} from '../../src/lib/newwf/state';

type InputDeclOut = components['schemas']['InputDeclOut'];

function decl(name: string, type: string, fallback: string | null = null): InputDeclOut {
  return { name, type, required: false, default: fallback, values: [] };
}

const catalog = buildCatalog(['one', 'two', 'plain'], {
  one: [
    decl('harness', 'enum', 'claude'),
    decl('model', 'string'),
    decl('model_x', 'string'),
    decl('model_y', 'string', 'foo'),
  ],
  two: [decl('model_y', 'string', 'bar'), decl('notes', 'string')],
  plain: [decl('model', 'string'), decl('notes', 'string')],
});

describe('isModelInput', () => {
  it.each(['model1', 'model_1', 'plan_model', 'review_model', 'data_model', 'modeling_notes'])(
    '%s qualifies',
    (name) => expect(isModelInput({ name, type: 'string' })).toBe(true),
  );
  it.each([
    ['remodeled', 'string'],
    ['model_count', 'number'],
    ['model_name_notes_v2', 'path'],
    ['my_model_x', 'string'],
  ])('%s (%s) does not', (name, type) => expect(isModelInput({ name, type })).toBe(false));
});

describe('resetModelInputs', () => {
  it('returns each model field to its default', () => {
    let state = defaultFormState(catalog);
    state = withInput(withInput(state, 'model_x', 'a'), 'model_y', 'b');
    expect(resetModelInputs(state, catalog).inputs).toEqual({ model_x: '', model_y: 'foo' });
  });

  it('leaves non-model inputs alone', () => {
    const state = withInput(withTemplate(defaultFormState(catalog), 'two', catalog), 'notes', 'n');
    expect(resetModelInputs(state, catalog).inputs.notes).toBe('n');
  });
});

describe('reconcileModelInputs', () => {
  it('clears values outside a non-empty list and keeps those inside', () => {
    const state = withInput(defaultFormState(catalog), 'model_x', 'in');
    const next = reconcileModelInputs(state, ['in', 'other'], catalog);
    expect(next.inputs).toEqual({ model_x: 'in', model_y: '' });
  });

  it('leaves an empty list and blank values untouched, returning the same state', () => {
    const state = withInput(defaultFormState(catalog), 'model_x', 'typed');
    expect(reconcileModelInputs(state, [], catalog)).toBe(state);
    const blank = withInput(withInput(defaultFormState(catalog), 'model_y', ''), 'model_x', '');
    expect(reconcileModelInputs(blank, ['in'], catalog)).toBe(blank);
  });

  it('applies to a template switched in while a list is loaded', () => {
    const switched = withTemplate(defaultFormState(catalog), 'two', catalog);
    expect(reconcileModelInputs(switched, ['x'], catalog).inputs.model_y).toBe('');
  });
});

function render(state: ReturnType<typeof defaultFormState>, models: string[]): string {
  return renderToStaticMarkup(
    createElement(NewWorkflowFields, {
      state,
      catalog,
      projects: [],
      repositories: [],
      models,
      note: undefined,
      onChange: () => {},
    }),
  );
}

describe('blank option label', () => {
  const tpl = buildCatalog(['t'], {
    t: [
      decl('model_y', 'string', 'foo'),
      decl('model_z', 'string', '{{ x }}'),
      decl('model_w', 'string'),
    ],
  });
  it('names a literal template default and leaves the others as —', () => {
    const markup = renderToStaticMarkup(
      createElement(NewWorkflowFields, {
        state: defaultFormState(tpl),
        catalog: tpl,
        projects: [],
        repositories: [],
        models: ['m1'],
        note: undefined,
        onChange: () => {},
      }),
    );
    expect(markup).toContain('<option value="">— (template default: foo)</option>');
    expect(markup).not.toContain('template default: {{');
    // project, repository, MODEL, model_z, model_w
    expect(markup.match(/<option value=""[^>]*>—<\/option>/g)).toHaveLength(5);
  });
});

describe('NewWorkflowFields model inputs', () => {
  it('renders a select over the list for a model input', () => {
    const markup = render(defaultFormState(catalog), ['m1', 'm2']);
    expect(markup).toMatch(/<select data-testid="newwf-input-model_x"/);
    expect(markup).toContain('<option value="m2">m2</option>');
  });

  it('renders free text when the list is empty', () => {
    const markup = render(defaultFormState(catalog), []);
    expect(markup).toMatch(/<input[^>]*data-testid="newwf-input-model_x"/);
  });

  it('never turns a non-model input into a select', () => {
    const state = withTemplate(defaultFormState(catalog), 'two', catalog);
    expect(render(state, ['m1'])).toMatch(/<input[^>]*data-testid="newwf-input-notes"/);
  });

  it('keeps the form-owned model field out of the derived fields', () => {
    expect(fieldsFor(catalog, 'plain').map((f) => f.key)).toEqual(['notes']);
  });

  it('carries a chosen value in the URL as in_model_x', () => {
    const state = withInput(defaultFormState(catalog), 'model_x', 'm1');
    expect(formStateToQuery(state, catalog).get('in_model_x')).toBe('m1');
  });
});
