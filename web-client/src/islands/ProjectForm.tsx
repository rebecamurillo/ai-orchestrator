/**
 * The Project + Repositories form (2.5): one React island, `client:load`, that submits as a
 * native form post to `actions.projects.save` — no `fetch` inside this file at all, and
 * every row's edits live in the DOM until submit (`defaultValue`), so re-rendering to add a
 * row never disturbs what the Operator already typed elsewhere.
 *
 * Three props only (`initial`, `errors`, `mode`), all serialisable: the page builds
 * `initial` either from a freshly read `ProjectRead` or from the kept draft `actions/projects.ts`
 * hands back on a failed save (`draftToInitial`) — this component does not know or care which.
 *
 * Row management (add, mask/replace, field naming, error lookup) is `./project-form-logic`,
 * imported rather than reimplemented here, so it can be unit-tested with no DOM.
 */
import { useState } from 'react';
import { actions } from 'astro:actions';

import {
  addRow,
  emptyEnvVarRow,
  emptyRepositoryRow,
  envVarFieldName,
  findError,
  initialEnvVarRows,
  initialRepositoryRows,
  repositoryFieldName,
  startReplacingEnvVar,
  type EnvVarRowState,
  type FieldError,
  type ProjectFormInitial,
  type RepositoryRowState,
} from './project-form-logic';

type Mode = 'create' | 'edit';

interface Props {
  initial: ProjectFormInitial;
  errors: FieldError[];
  mode: Mode;
}

const PACKAGE_MANAGERS = ['uv', 'pnpm', 'npm', 'yarn', 'pip', 'cargo', 'go', 'other'] as const;

const LOG_PROMPT_CONTENT_ON =
  'on: prompt and tool content, including source code, is sent to Langfuse for this project';

const NO_CREDENTIAL_FIELD_LINE = 'credentials are instance settings (.env)';

export default function ProjectForm({ initial, errors, mode }: Props) {
  const [envVars, setEnvVars] = useState<EnvVarRowState[]>(() => initialEnvVarRows(initial));
  const [repositories, setRepositories] = useState<RepositoryRowState[]>(() =>
    initialRepositoryRows(initial),
  );
  const [logPromptContent, setLogPromptContent] = useState(initial.logPromptContent);

  function reasonFor(path: string): string | undefined {
    return findError(errors, path)?.reason;
  }

  return (
    <form
      className="project-form"
      method="POST"
      action={actions.projects.save.toString()}
      data-testid="project-form"
    >
      <input type="hidden" name="mode" value={mode} />
      {initial.projectId ? (
        <input type="hidden" name="project_id" value={initial.projectId} />
      ) : null}

      <div className="field">
        <label className="field-label" htmlFor="project-form-name-input">
          NAME
        </label>
        <input
          id="project-form-name-input"
          className="field-input"
          type="text"
          name="name"
          defaultValue={initial.name}
          data-testid="project-form-name"
        />
        {reasonFor('name') ? (
          <p className="field-error" data-testid="project-form-name-error">
            {reasonFor('name')}
          </p>
        ) : null}
      </div>

      <div className="field">
        <label className="field-label" htmlFor="project-form-context-input">
          CONTEXT
        </label>
        <textarea
          id="project-form-context-input"
          className="field-input"
          name="context_text"
          defaultValue={initial.contextText}
          data-testid="project-form-context"
        />
      </div>

      <div className="field">
        <label className="field-label" htmlFor="project-form-context-paths-input">
          CONTEXT FILE PATHS (one per line)
        </label>
        <textarea
          id="project-form-context-paths-input"
          className="field-input"
          name="context_paths"
          defaultValue={initial.contextPaths}
          data-testid="project-form-context-paths"
        />
      </div>

      <div className="field switch">
        <label className="switch-label">
          <input
            type="checkbox"
            name="log_prompt_content"
            value="on"
            checked={logPromptContent}
            onChange={(event) => setLogPromptContent(event.target.checked)}
            data-testid="project-form-log-prompt-content"
          />
          <span>log prompt content</span>
        </label>
        {logPromptContent ? <p className="secondary-line">{LOG_PROMPT_CONTENT_ON}</p> : null}
      </div>

      <section className="rows">
        <h3 className="rows-title">ENV VARS</h3>
        {envVars.map((row, index) => {
          const revealed = row.masked === undefined || row.replacing;
          return (
            <div className="row" key={index} data-testid={`project-form-env-${index}`}>
              <input
                type="text"
                name={envVarFieldName(index, 'name')}
                placeholder="NAME"
                defaultValue={row.name}
                data-testid={`project-form-env-${index}-name`}
              />
              {reasonFor(envVarFieldName(index, 'name')) ? (
                <p className="field-error" data-testid={`project-form-env-${index}-name-error`}>
                  {reasonFor(envVarFieldName(index, 'name'))}
                </p>
              ) : null}

              {revealed ? (
                <>
                  <input
                    type="text"
                    name={envVarFieldName(index, 'value')}
                    placeholder="value"
                    defaultValue={row.value}
                    data-testid={`project-form-env-${index}-value`}
                  />
                  {reasonFor(envVarFieldName(index, 'value')) ? (
                    <p
                      className="field-error"
                      data-testid={`project-form-env-${index}-value-error`}
                    >
                      {reasonFor(envVarFieldName(index, 'value'))}
                    </p>
                  ) : null}
                </>
              ) : (
                <span className="masked-value" data-testid={`project-form-env-${index}-masked`}>
                  {row.masked}
                  <input type="hidden" name={envVarFieldName(index, 'masked')} value={row.masked} />
                  <button
                    type="button"
                    className="link-button"
                    data-testid={`project-form-env-${index}-replace`}
                    onClick={() => setEnvVars((current) => startReplacingEnvVar(current, index))}
                  >
                    replace
                  </button>
                </span>
              )}
            </div>
          );
        })}
        <button
          type="button"
          className="add-row"
          data-testid="project-form-env-add"
          onClick={() => setEnvVars((current) => addRow(current, emptyEnvVarRow()))}
        >
          + add env var
        </button>
      </section>

      <p className="secondary-line">{NO_CREDENTIAL_FIELD_LINE}</p>

      <section className="rows">
        <h3 className="rows-title">REPOSITORIES</h3>
        {repositories.map((row, index) => (
          <div className="row repo-row" key={index} data-testid={`project-form-repo-${index}`}>
            {row.id ? (
              <input type="hidden" name={repositoryFieldName(index, 'id')} value={row.id} />
            ) : null}

            <label className="field">
              <span className="field-label">URL</span>
              <input
                type="text"
                name={repositoryFieldName(index, 'url')}
                defaultValue={row.url}
                data-testid={`repo-form-${index}-url`}
              />
              {reasonFor(repositoryFieldName(index, 'url')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-url-error`}>
                  {reasonFor(repositoryFieldName(index, 'url'))}
                </p>
              ) : null}
            </label>

            <label className="field">
              <span className="field-label">DEFAULT BRANCH</span>
              <input
                type="text"
                name={repositoryFieldName(index, 'default_branch')}
                defaultValue={row.defaultBranch}
                data-testid={`repo-form-${index}-default-branch`}
              />
              {reasonFor(repositoryFieldName(index, 'default_branch')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-default-branch-error`}>
                  {reasonFor(repositoryFieldName(index, 'default_branch'))}
                </p>
              ) : null}
            </label>

            <label className="field">
              <span className="field-label">PACKAGE MANAGER</span>
              <select
                name={repositoryFieldName(index, 'package_manager')}
                defaultValue={row.packageManager}
                data-testid={`repo-form-${index}-package-manager`}
              >
                {PACKAGE_MANAGERS.map((manager) => (
                  <option key={manager} value={manager}>
                    {manager}
                  </option>
                ))}
              </select>
              {reasonFor(repositoryFieldName(index, 'package_manager')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-package-manager-error`}>
                  {reasonFor(repositoryFieldName(index, 'package_manager'))}
                </p>
              ) : null}
            </label>

            <label className="field">
              <span className="field-label">TEST GLOBS (one per line)</span>
              <textarea
                name={repositoryFieldName(index, 'test_globs')}
                defaultValue={row.testGlobs}
                data-testid={`repo-form-${index}-test-globs`}
              />
              {reasonFor(repositoryFieldName(index, 'test_globs')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-test-globs-error`}>
                  {reasonFor(repositoryFieldName(index, 'test_globs'))}
                </p>
              ) : null}
            </label>

            <label className="field">
              <span className="field-label">INSTALL COMMAND</span>
              <input
                type="text"
                name={repositoryFieldName(index, 'install_command')}
                defaultValue={row.installCommand}
                data-testid={`repo-form-${index}-install`}
              />
              {reasonFor(repositoryFieldName(index, 'install_command')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-install-error`}>
                  {reasonFor(repositoryFieldName(index, 'install_command'))}
                </p>
              ) : null}
            </label>

            <label className="field">
              <span className="field-label">QUALITY GATE COMMAND</span>
              <input
                type="text"
                name={repositoryFieldName(index, 'quality_gate_command')}
                defaultValue={row.qualityGateCommand}
                data-testid={`repo-form-${index}-quality`}
              />
              {reasonFor(repositoryFieldName(index, 'quality_gate_command')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-quality-error`}>
                  {reasonFor(repositoryFieldName(index, 'quality_gate_command'))}
                </p>
              ) : null}
            </label>

            <label className="field">
              <span className="field-label">UNIT TEST COMMAND</span>
              <input
                type="text"
                name={repositoryFieldName(index, 'unit_test_command')}
                defaultValue={row.unitTestCommand}
                data-testid={`repo-form-${index}-unit-test`}
              />
              {reasonFor(repositoryFieldName(index, 'unit_test_command')) ? (
                <p className="field-error" data-testid={`repo-form-${index}-unit-test-error`}>
                  {reasonFor(repositoryFieldName(index, 'unit_test_command'))}
                </p>
              ) : null}
            </label>
          </div>
        ))}
        <button
          type="button"
          className="add-row"
          data-testid="project-form-repo-add"
          onClick={() => setRepositories((current) => addRow(current, emptyRepositoryRow()))}
        >
          + add repository
        </button>
      </section>

      <button type="submit" className="save-button" data-testid="project-form-save">
        save
      </button>
    </form>
  );
}
