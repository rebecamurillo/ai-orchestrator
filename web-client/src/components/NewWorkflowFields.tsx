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
 */
import type { components } from '../api/schema';
import {
  TEMPLATE_INPUT_FIELDS,
  TEMPLATE_ORDER,
  isTemplateName,
  repositoryById,
  withInput,
  withTemplate,
  type FormState,
  type TemplateName,
} from '../lib/newwf/state';

type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

interface Props {
  state: FormState;
  projects: ProjectRead[];
  repositories: RepositoryOut[];
  note: string | undefined;
  onChange: (next: FormState) => void;
}

export default function NewWorkflowFields({
  state,
  projects,
  repositories,
  note,
  onChange,
}: Props) {
  return (
    <>
      <label className="newwf-field">
        <span className="newwf-field-label">TEMPLATE</span>
        <select
          data-testid="newwf-template"
          value={state.template}
          onChange={(event) => {
            const value = event.target.value;
            if (isTemplateName(value)) onChange(withTemplate(state, value as TemplateName));
          }}
        >
          {TEMPLATE_ORDER.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>
      </label>

      <label className="newwf-field">
        <span className="newwf-field-label">PROJECT</span>
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

      <label className="newwf-field">
        <span className="newwf-field-label">REPOSITORY</span>
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

      <label className="newwf-field">
        <span className="newwf-field-label">BASE BRANCH</span>
        <input
          type="text"
          data-testid="newwf-base"
          value={state.baseBranch}
          onChange={(event) => onChange({ ...state, baseBranch: event.target.value })}
        />
      </label>

      {TEMPLATE_INPUT_FIELDS[state.template].map((field) => (
        <label className="newwf-field" key={field.key}>
          <span className="newwf-field-label">{field.label}</span>
          <input
            type="text"
            data-testid={`newwf-input-${field.key}`}
            value={state.inputs[field.key] ?? ''}
            onChange={(event) => onChange(withInput(state, field.key, event.target.value))}
          />
        </label>
      ))}

      <label className="newwf-field">
        <span className="newwf-field-label">MODEL</span>
        <input
          type="text"
          data-testid="newwf-model"
          placeholder="harness default"
          value={state.model}
          onChange={(event) => onChange({ ...state, model: event.target.value })}
        />
      </label>

      <label className="newwf-field">
        <span className="newwf-field-label">BUDGET (USD)</span>
        <input
          type="text"
          inputMode="decimal"
          required
          data-testid="newwf-budget"
          value={state.budgetUsd}
          onChange={(event) => onChange({ ...state, budgetUsd: event.target.value })}
        />
      </label>

      <label className="newwf-field newwf-switch">
        <input
          type="checkbox"
          data-testid="newwf-rereview"
          checked={state.reReviewDone}
          onChange={(event) => onChange({ ...state, reReviewDone: event.target.checked })}
        />
        <span>re-review done stories</span>
      </label>

      <label className="newwf-field">
        <span className="newwf-field-label">MANUAL ESTIMATE (H)</span>
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
