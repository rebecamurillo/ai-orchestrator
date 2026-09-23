/**
 * The New Initiative form's own fields (S7), in the brief's own order: project → hub
 * repository → initiative folder → base branch → model → budget per epic. The harness list
 * sits below these, `NewInitiative.tsx`'s own `HarnessList.tsx` reuse — the one control with
 * a live probe of its own, same split `NewWorkflowFields.tsx` documents for 4.13.
 *
 * Every field is controlled from the one `FormState` the island owns; this component holds
 * no state and decides nothing — it renders what it is given and reports each edit back
 * through `onChange` (`NewWorkflowFields.tsx`'s own precedent, reusing its `.newwf-field`
 * styling wholesale rather than a second stylesheet for the same look).
 */
import type { components } from '../../api/schema';
import { repositoryById, type FormState } from '../../lib/initiative/form';

type ProjectRead = components['schemas']['ProjectRead'];
type RepositoryOut = components['schemas']['RepositoryOut'];

interface Props {
  state: FormState;
  projects: ProjectRead[];
  repositories: RepositoryOut[];
  models: string[];
  onChange: (next: FormState) => void;
}

export default function InitiativeFields({
  state,
  projects,
  repositories,
  models,
  onChange,
}: Props) {
  return (
    <>
      <label
        className="newwf-field"
        title="Billing and authorisation scope for the initiative. Limits the hub repository list."
      >
        <span className="newwf-field-label">PROJECT *</span>
        <select
          data-testid="newin-project"
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
        title="The hub repository: where {initiative_folder}/epics.yaml lives. It need not hold any of the epics itself."
      >
        <span className="newwf-field-label">HUB REPOSITORY *</span>
        <select
          data-testid="newin-repository"
          value={state.repositoryId}
          onChange={(event) => {
            const repository = repositoryById(repositories, event.target.value);
            onChange({
              ...state,
              repositoryId: event.target.value,
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
      </label>

      <label
        className="newwf-field"
        title="Path in the hub repository holding epics.yaml, one folder per epic."
      >
        <span className="newwf-field-label">INITIATIVE FOLDER *</span>
        <input
          type="text"
          data-testid="newin-folder"
          value={state.initiativeFolder}
          onChange={(event) => onChange({ ...state, initiativeFolder: event.target.value })}
        />
      </label>

      <label className="newwf-field" title="The branch each repository's epics merge into.">
        <span className="newwf-field-label">BASE BRANCH *</span>
        <input
          type="text"
          data-testid="newin-base"
          value={state.baseBranch}
          onChange={(event) => onChange({ ...state, baseBranch: event.target.value })}
        />
      </label>

      <label
        className="newwf-field"
        title="LLM model the harness calls for every epic Run. Blank uses the harness default; the list shows only what the live probe returned."
      >
        <span className="newwf-field-label">MODEL (optional)</span>
        {models.length > 0 ? (
          <select
            data-testid="newin-model"
            value={state.model}
            onChange={(event) => onChange({ ...state, model: event.target.value })}
          >
            <option value="">—</option>
            {models.map((model) => (
              <option key={model} value={model}>
                {model}
              </option>
            ))}
          </select>
        ) : (
          <input
            type="text"
            data-testid="newin-model"
            placeholder="harness default"
            value={state.model}
            onChange={(event) => onChange({ ...state, model: event.target.value })}
          />
        )}
      </label>

      <label
        className="newwf-field"
        title="Maximum LLM spend in USD per epic Run. Blank runs without a cap; spend is still tracked."
      >
        <span className="newwf-field-label">BUDGET PER EPIC (USD) (optional)</span>
        <input
          type="text"
          inputMode="decimal"
          data-testid="newin-budget"
          value={state.budgetUsdPerEpic}
          onChange={(event) => onChange({ ...state, budgetUsdPerEpic: event.target.value })}
        />
      </label>
    </>
  );
}
