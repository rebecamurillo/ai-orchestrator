/** The left column of the New initiative page: controlled fields, the refusal and the actions. */
import {
  canCreate,
  createLabel,
  firstAgent,
  hubHint,
  liveLine,
  messageHint,
  slugOf,
  slugTakenParts,
  type PackageOut,
} from '../../lib/initiatives/new';
import type { InitiativeRow } from '../../lib/initiatives/format';

export interface Problem {
  title: string;
  detail: string | null;
}

export interface FormState {
  projectId: string;
  name: string;
  message: string;
  refusal: { holder: InitiativeRow } | Problem | null;
  otherProblem: Problem | null;
  submitting: boolean;
}

interface Props {
  state: FormState;
  projects: { id: string; name: string }[];
  pkg: PackageOut | null;
  onChange: (patch: Partial<Pick<FormState, 'projectId' | 'name' | 'message'>>) => void;
  onCreate: () => void;
}

function Refusal({ refusal }: { refusal: NonNullable<FormState['refusal']> }) {
  if ('holder' in refusal) {
    const parts = slugTakenParts(refusal.holder);
    return (
      <p data-testid="newini-slug-taken" data-signal="needs-you">
        {parts.lead}
        <a href={parts.href}>{parts.linkText}</a>
        {parts.tail}
      </p>
    );
  }
  return (
    <p data-signal="needs-you">
      <span>{refusal.title}</span>
      {refusal.detail ? <span className="newini-detail">{refusal.detail}</span> : null}
    </p>
  );
}

export default function NewInitiativeForm({ state, projects, pkg, onChange, onCreate }: Props) {
  const enabled = canCreate({
    name: state.name,
    message: state.message,
    hasPackage: pkg !== null,
    refused: state.refusal !== null,
    submitting: state.submitting,
  });
  return (
    <form
      className="newini-form"
      onSubmit={(e) => {
        e.preventDefault();
        if (enabled) onCreate();
      }}
    >
      <label className="newini-field">
        <span className="newini-label">Project</span>
        <span>
          <select
            data-testid="newini-project"
            value={state.projectId}
            onChange={(e) => onChange({ projectId: e.target.value })}
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          {pkg ? <span className="newini-hint">{hubHint(pkg)}</span> : null}
        </span>
      </label>
      <label className="newini-field">
        <span className="newini-label">Name</span>
        <span>
          <input
            type="text"
            data-testid="newini-name"
            value={state.name}
            onChange={(e) => onChange({ name: e.target.value })}
          />
          {pkg && state.name.trim() !== '' ? (
            <span className="newini-hint">
              {liveLine(slugOf(state.name), pkg.repository.initiative_folder)}
            </span>
          ) : null}
          {state.refusal ? <Refusal refusal={state.refusal} /> : null}
        </span>
      </label>
      <label className="newini-field">
        <span className="newini-label">First message</span>
        <span>
          <textarea
            data-testid="newini-message"
            rows={8}
            value={state.message}
            onChange={(e) => onChange({ message: e.target.value })}
          />
          {pkg ? <span className="newini-hint">{messageHint(firstAgent(pkg))}</span> : null}
        </span>
      </label>
      <div className="newini-actions">
        <button type="submit" data-testid="newini-create" disabled={!enabled}>
          {createLabel(pkg)}
        </button>
        <a href="/initiatives">Cancel</a>
      </div>
      <p className="newini-hint">
        One workflow runs at a time; the next starts when this one is done.
      </p>
      {state.otherProblem ? (
        <p data-testid="newini-problem">
          <span>{state.otherProblem.title}</span>
          {state.otherProblem.detail ? (
            <span className="newini-detail">{state.otherProblem.detail}</span>
          ) : null}
        </p>
      ) : null}
    </form>
  );
}
