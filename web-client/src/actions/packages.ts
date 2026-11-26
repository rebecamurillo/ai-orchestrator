/**
 * *Install package* and *Remove package* on the project page. The problem's `detail` is
 * passed through untouched: the backend words every refusal and the page prints it as sent.
 */
import { ActionError, defineAction } from 'astro:actions';

import { backend } from '../api/server';

type Code = 'NOT_FOUND' | 'CONFLICT' | 'BAD_REQUEST' | 'INTERNAL_SERVER_ERROR';

function codeFor(status: number | undefined): Code {
  if (status === 404) return 'NOT_FOUND';
  if (status === 409) return 'CONFLICT';
  if (status === 422) return 'BAD_REQUEST';
  return 'INTERNAL_SERVER_ERROR';
}

function field(form: FormData, name: string): string {
  const value = form.get(name);
  if (typeof value !== 'string' || value.length === 0) {
    throw new ActionError({ code: 'BAD_REQUEST', message: `${name} is required` });
  }
  return value;
}

export const install = defineAction({
  accept: 'form',
  handler: async (form: FormData) => {
    const projectId = field(form, 'projectId');
    const repositoryId = field(form, 'repositoryId');
    const path = field(form, 'path');
    const ref = field(form, 'ref');

    const { data, error } = await backend().PUT('/api/v1/projects/{project_id}/package', {
      params: { path: { project_id: projectId } },
      body: { repository_id: repositoryId, path, ref },
    });
    if (error) {
      throw new ActionError({
        code: codeFor(error.status),
        message: error.detail ?? error.title ?? 'install failed',
      });
    }
    return data;
  },
});

export const remove = defineAction({
  accept: 'form',
  handler: async (form: FormData) => {
    const projectId = field(form, 'projectId');
    const { error } = await backend().DELETE('/api/v1/projects/{project_id}/package', {
      params: { path: { project_id: projectId } },
    });
    if (error) {
      throw new ActionError({
        code: codeFor(error.status),
        message: error.detail ?? 'remove failed',
      });
    }
    return null;
  },
});
