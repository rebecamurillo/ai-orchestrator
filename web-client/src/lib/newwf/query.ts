/**
 * The form state, as the URL's own query string (UX-DR8: "a page, not a modal; the URL
 * carries the form state ... so a reload restores it"). No DOM, no fetch — pure `string` in,
 * `string` out, so a reload is provable without a browser (`web-client/AGENTS.md`).
 *
 * `template`, `project`, `repository` and `branch` are the brief's own four prefill keys
 * (the "start a new run" links' contract) — `branch` there names the *base* branch. A
 * template's own inputs (a dev-loop Template's own `branch`, for a working branch, is one)
 * would collide
 * with that key, so every template input is carried under `in_{key}` instead.
 */
import { fieldsFor, firstTemplate, offers, type TemplateCatalog } from './catalog';
import type { FormState } from './state';

const KEY_TEMPLATE = 'template';
const KEY_PROJECT = 'project';
const KEY_REPOSITORY = 'repository';
const KEY_BASE_BRANCH = 'branch';
const KEY_HARNESS = 'harness';
const KEY_MODEL = 'model';
const KEY_BUDGET = 'budget';
const KEY_RE_REVIEW = 're_review';
const KEY_ESTIMATE = 'estimate';
const INPUT_PREFIX = 'in_';

export function parseFormStateFromQuery(
  search: string | URLSearchParams,
  catalog: TemplateCatalog,
): FormState {
  const params = typeof search === 'string' ? new URLSearchParams(search) : search;
  const templateParam = params.get(KEY_TEMPLATE) ?? '';
  // a link may name a Template this instance no longer offers
  const template = offers(catalog, templateParam) ? templateParam : firstTemplate(catalog);

  const inputs: Record<string, string> = {};
  for (const field of fieldsFor(catalog, template)) {
    inputs[field.key] = params.get(`${INPUT_PREFIX}${field.key}`) ?? field.initial;
  }

  return {
    template,
    projectId: params.get(KEY_PROJECT) ?? '',
    repositoryId: params.get(KEY_REPOSITORY) ?? '',
    baseBranch: params.get(KEY_BASE_BRANCH) ?? '',
    inputs,
    harness: params.get(KEY_HARNESS) ?? '',
    model: params.get(KEY_MODEL) ?? '',
    budgetUsd: params.get(KEY_BUDGET) ?? '',
    reReviewDone: params.get(KEY_RE_REVIEW) === '1',
    manualEstimateH: params.get(KEY_ESTIMATE) ?? '',
  };
}

/** The inverse of `parseFormStateFromQuery`: every non-empty field, so a state built from an
 * empty query string round-trips to an empty one rather than one full of blank pairs. */
export function formStateToQuery(state: FormState, catalog: TemplateCatalog): URLSearchParams {
  const params = new URLSearchParams();
  // set even at the default: a reload must restore exactly what was open, not fall back to
  // whatever `parseFormStateFromQuery` would default an absent key to
  params.set(KEY_TEMPLATE, state.template);
  if (state.projectId) params.set(KEY_PROJECT, state.projectId);
  if (state.repositoryId) params.set(KEY_REPOSITORY, state.repositoryId);
  if (state.baseBranch) params.set(KEY_BASE_BRANCH, state.baseBranch);
  for (const field of fieldsFor(catalog, state.template)) {
    const value = state.inputs[field.key];
    if (value) params.set(`${INPUT_PREFIX}${field.key}`, value);
  }
  if (state.harness) params.set(KEY_HARNESS, state.harness);
  if (state.model) params.set(KEY_MODEL, state.model);
  if (state.budgetUsd) params.set(KEY_BUDGET, state.budgetUsd);
  if (state.reReviewDone) params.set(KEY_RE_REVIEW, '1');
  if (state.manualEstimateH) params.set(KEY_ESTIMATE, state.manualEstimateH);
  return params;
}
