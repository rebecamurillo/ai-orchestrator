/**
 * The New initiative island (story 10.3): the form, and for the selected project the package
 * and the workflows it will run. The POST body carries no slug — the backend derives it; the
 * slug shown here is display only (`lib/initiatives/new.ts`). `requestSeqRef` drops a late
 * package answer for a project that is no longer selected.
 */
import { useEffect, useRef, useState } from 'react';

import { api } from '../api/client';
import FailedFetch from '../components/FailedFetch';
import NewInitiativeForm, {
  type FormState,
  type Problem,
} from '../components/initiatives/NewInitiativeForm';
import PackageSequence from '../components/initiatives/PackageSequence';
import {
  NO_PACKAGE_LINE,
  openHolder,
  slugOf,
  type PackageOut,
  type ProjectRead,
} from '../lib/initiatives/new';
import '../styles/initiatives.css';

interface Props {
  projects: { id: string; name: string }[];
  initialProjectId: string | null;
}

type PackageState =
  | { kind: 'loading' }
  | { kind: 'ready'; pkg: PackageOut }
  | { kind: 'missing' }
  | { kind: 'error'; status: number | null };

function asProblem(error: unknown, fallbackTitle: string): Problem {
  const e = (error ?? {}) as { title?: string; detail?: string | null };
  return { title: e.title ?? fallbackTitle, detail: e.detail ?? null };
}

export default function NewInitiative({ projects, initialProjectId }: Props) {
  const [form, setForm] = useState<FormState>({
    projectId: initialProjectId ?? projects[0]?.id ?? '',
    name: '',
    message: '',
    refusal: null,
    otherProblem: null,
    submitting: false,
  });
  const [pkgState, setPkgState] = useState<PackageState>({ kind: 'loading' });
  const [project, setProject] = useState<ProjectRead | null>(null);
  const [postFailed, setPostFailed] = useState(false);
  const requestSeqRef = useRef(0);

  async function load(projectId: string): Promise<void> {
    const seq = ++requestSeqRef.current;
    setPkgState({ kind: 'loading' });
    setProject(null);
    const [pkgRes, projectRes] = await Promise.allSettled([
      api.GET('/projects/{project_id}/package', { params: { path: { project_id: projectId } } }),
      api.GET('/projects/{project_id}', { params: { path: { project_id: projectId } } }),
    ]);
    if (seq !== requestSeqRef.current) return;
    if (projectRes.status === 'fulfilled' && projectRes.value.data) {
      setProject(projectRes.value.data);
    }
    if (pkgRes.status === 'rejected') {
      setPkgState({ kind: 'error', status: null });
    } else if (pkgRes.value.data) {
      setPkgState({ kind: 'ready', pkg: pkgRes.value.data });
    } else if (pkgRes.value.response.status === 404) {
      setPkgState({ kind: 'missing' });
    } else {
      setPkgState({ kind: 'error', status: pkgRes.value.response.status });
    }
  }

  useEffect(() => {
    if (form.projectId) void load(form.projectId);
    // refetches only when the selected project changes
  }, [form.projectId]);

  function change(patch: Partial<Pick<FormState, 'projectId' | 'name' | 'message'>>): void {
    setForm((f) => ({ ...f, ...patch, ...(patch.name !== undefined ? { refusal: null } : {}) }));
  }

  async function create(): Promise<void> {
    setForm((f) => ({ ...f, submitting: true, otherProblem: null }));
    setPostFailed(false);
    try {
      const { data, error, response } = await api.POST('/initiatives', {
        body: { project_id: form.projectId, name: form.name, first_message: form.message },
      });
      if (data) {
        window.location.assign(`/initiatives/${data.id}`);
        return;
      }
      const problem = asProblem(error, 'Request failed');
      if (response.status === 409) {
        let refusal: FormState['refusal'] = problem;
        try {
          const list = await api.GET('/initiatives', {
            params: { query: { project_id: form.projectId, filter: 'all' } },
          });
          const holder = list.data ? openHolder(list.data.items, slugOf(form.name)) : null;
          if (holder) refusal = { holder };
        } catch {
          // the problem's own title and detail stand in for the holder line
        }
        setForm((f) => ({ ...f, submitting: false, refusal }));
        return;
      }
      setForm((f) => ({ ...f, submitting: false, otherProblem: problem }));
    } catch {
      setPostFailed(true);
      setForm((f) => ({ ...f, submitting: false }));
    }
  }

  const pkg = pkgState.kind === 'ready' ? pkgState.pkg : null;

  return (
    <div className="newini" data-testid="new-initiative">
      <div className="newini-left">
        <NewInitiativeForm
          state={form}
          projects={projects}
          pkg={pkg}
          onChange={change}
          onCreate={() => void create()}
        />
        {postFailed ? (
          <FailedFetch
            method="POST"
            path="/api/initiatives"
            status={null}
            onRetry={() => void create()}
          />
        ) : null}
      </div>
      <aside className="newini-right">
        {pkgState.kind === 'ready' ? (
          <PackageSequence pkg={pkgState.pkg} project={project} />
        ) : null}
        {pkgState.kind === 'missing' ? <p className="newini-hint">{NO_PACKAGE_LINE}</p> : null}
        {pkgState.kind === 'error' ? (
          <FailedFetch
            method="GET"
            path={`/api/projects/${form.projectId}/package`}
            status={pkgState.status}
            onRetry={() => void load(form.projectId)}
          />
        ) : null}
      </aside>
    </div>
  );
}
