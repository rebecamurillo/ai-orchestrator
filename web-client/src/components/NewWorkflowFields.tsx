/**
 * The New Workflow form's own fields (4.13, UX-DR8), in the brief's order: template →
 * project → repository → base branch → template inputs → model → budget → re-review → manual
 * estimate. The harness list sits between the inputs and the model field and is
 * `HarnessList.tsx`'s own component, because it is the one group with a control of its own.
 *
 * Split out of `NewWorkflow.tsx` so each file stays inside `web-client/AGENTS.md`'s "a
 * component file ≤ 300 lines". Every field is controlled from the one `FormState` the island
 * owns; this component holds no state and decides nothing — it renders what it is given and
 * reports each edit back through `onChange`.
 *
 * The MODEL field has two shapes and the `models` prop picks between them. The island passes
 * the selected harness's live probe list (`GET /harnesses/{name}/probe`): a non-empty list gives
 * a select over exactly those models, because a name the harness does not serve is a Run that
 * pre-flights clean, starts, and fails at its first model call. An empty or unretrievable list
 * gives the free-text field; this component only renders the answer.
 *
 * Every Template input named `model*` or `*model` renders the same control from the same list
 * (`ModelField`).
 */
import type { components } from '../api/schema';
import ModelField from './ModelField';
import { fieldsFor, type TemplateCatalog } from '../lib/newwf/catalog';
import {
  isTemplateName,
  repositoryById,
  withInput,
  withTemplate,
  type FormState,
} from '../lib/newwf/state';

type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

interface Props {
  state: FormState;
  catalog: TemplateCatalog;
  projects: ProjectRead[];
  repositories: RepositoryOut[];
  /**
   * The models the selected harness offers, or `[]` for one that takes a free-text name.
   *
   * Optional, and defaulted to `[]` below, on the same precedent `HarnessOut.models` follows
   * on the other side of the contract: `tests/unit/newwf-fields.test.ts` is frozen and
   * constructs this component without the prop, and the shape it asserts — the text field —
   * is exactly what an absent list still renders.
   */
  models?: string[];
  note: string | undefined;
  onChange: (next: FormState) => void;
}

/** The backend binds a literal declared default when an input is blank, so the blank option
 * names it; a templated default (`{{`) has no literal to show. */
function blankLabelFor(initial: string): string | undefined {
  return initial !== '' && !initial.includes('{{') ? `— (template default: ${initial})` : undefined;
}

export default function NewWorkflowFields({
  state,
  catalog,
  projects,
  repositories,
  models = [],
  note,
  onChange,
}: Props) {
  return (
    <>
      <label
        className="newwf-field"
        title="Selects which BMAD workflow the Run executes. Controls the step sequence and which inputs the form shows."
      >
        <span className="newwf-field-label">TEMPLATE *</span>
        <select
          data-testid="newwf-template"
          value={state.template}
          onChange={(event) => {
            const value = event.target.value;
            if (isTemplateName(value, catalog)) onChange(withTemplate(state, value, catalog));
          }}
        >
          {catalog.names.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      <label
        className="newwf-field"
        title="Billing and authorisation scope for the Run. Limits the repository list."
      >
        <span className="newwf-field-label">PROJECT *</span>
        <select
          data-testid="newwf-project"
          value={state.projectId}
          onChange={(event) =>
            onChange({ ...state, projectId: event.target.value, repositoryId: '' })
          }
        >
          <option value="">—</option>
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </label>

      <label
        className="newwf-field"
        title="Target repository. The harness checks it out for every Run."
      >
        <span className="newwf-field-label">REPOSITORY *</span>
        <select
          data-testid="newwf-repository"
          value={state.repositoryId}
          onChange={(event) => {
            const repository = repositoryById(repositories, event.target.value);
            onChange({
              ...state,
              repositoryId: event.target.value,
              // seeds an empty field only: a branch the Operator already typed is never
              // replaced by a later repository change
              baseBranch: state.baseBranch || repository?.default_branch || '',
            });
          }}
        >
          <option value="">—</option>
          {repositories.map((repository) => (
            <option key={repository.id} value={repository.id}>
              {repository.slug}
            </option>
          ))}
        </select>
        {note ? <span className="newwf-field-note">{note}</span> : null}
      </label>

      <label
        className="newwf-field"
        title="The branch the harness starts from when creating per-story working branches."
      >
        <span className="newwf-field-label">BASE BRANCH *</span>
        <input
          type="text"
          data-testid="newwf-base"
          value={state.baseBranch}
          onChange={(event) => onChange({ ...state, baseBranch: event.target.value })}
        />
      </label>

      {fieldsFor(catalog, state.template).map((field) => (
        <label className="newwf-field" key={field.key} title={field.tooltip}>
          <span className="newwf-field-label">
            {field.label} {field.required ? '*' : '(optional)'}
          </span>
          {field.modelChoice ? (
            <ModelField
              testId={`newwf-input-${field.key}`}
              value={state.inputs[field.key] ?? ''}
              models={models}
              blankLabel={blankLabelFor(field.initial)}
              onChange={(value) => onChange(withInput(state, field.key, value))}
            />
          ) : (
            <input
              type="text"
              data-testid={`newwf-input-${field.key}`}
              value={state.inputs[field.key] ?? ''}
              onChange={(event) => onChange(withInput(state, field.key, event.target.value))}
            />
          )}
        </label>
      ))}

      <label
        className="newwf-field"
        title="LLM model the harness calls. Blank uses the harness default; the list shows only what the live probe returned."
      >
        <span className="newwf-field-label">MODEL (optional)</span>
        <ModelField
          testId="newwf-model"
          value={state.model}
          models={models}
          placeholder="harness default"
          onChange={(value) => onChange({ ...state, model: value })}
        />
      </label>

      <label
        className="newwf-field"
        title="Maximum LLM spend in USD for this Run. The Run enters needs_you when this limit is reached. Blank runs without a cap; spend is still tracked."
      >
        <span className="newwf-field-label">BUDGET (USD) (optional)</span>
        <input
          type="text"
          inputMode="decimal"
          data-testid="newwf-budget"
          value={state.budgetUsd}
          onChange={(event) => onChange({ ...state, budgetUsd: event.target.value })}
        />
      </label>

      <label
        className="newwf-field newwf-switch"
        title="Adds a review pass after each story the harness marks done. Increases run time."
      >
        <input
          type="checkbox"
          data-testid="newwf-rereview"
          checked={state.reReviewDone}
          onChange={(event) => onChange({ ...state, reReviewDone: event.target.checked })}
        />
        <span>re-review done stories</span>
      </label>

      <label
        className="newwf-field"
        title="Hours estimate recorded in the run report. Has no effect on execution."
      >
        <span className="newwf-field-label">MANUAL ESTIMATE (H) (optional)</span>
        <input
          type="text"
          inputMode="decimal"
          data-testid="newwf-estimate"
          value={state.manualEstimateH}
          onChange={(event) => onChange({ ...state, manualEstimateH: event.target.value })}
        />
      </label>
    </>
  );
}
