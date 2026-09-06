/**
 * The *re-run check* Action behind a failed Repository's clone check (2.4).
 *
 * The form posts here with no island and no client JavaScript at all: Astro re-renders the
 * referring page afterward, and `src/pages/projects/index.astro` always re-fetches
 * `GET /api/v1/projects/{id}` fresh on every render, so the new result reaches the screen
 * without this Action's own return value being threaded anywhere. `backend()` is used
 * directly here — the eslint restriction on `src/api/server.ts` covers only
 * `src/islands|stores|components`, not an Action, which already runs on the server.
 */
import { ActionError, defineAction } from 'astro:actions';

import { backend } from '../api/server';

export const recheck = defineAction({
  accept: 'form',
  handler: async (form: FormData) => {
    const repositoryId = form.get('repositoryId');
    // mirrors `login.ts`'s missing-field handling: one answer for absent and for the wrong type
    if (typeof repositoryId !== 'string' || repositoryId.length === 0) {
      throw new ActionError({ code: 'BAD_REQUEST', message: 'repositoryId is required' });
    }

    const { data, error } = await backend().POST(
      '/api/v1/repositories/{repository_id}/clone-check',
      {
        params: { path: { repository_id: repositoryId } },
      },
    );

    if (error) {
      throw new ActionError({
        code: error.status === 404 ? 'NOT_FOUND' : 'INTERNAL_SERVER_ERROR',
        message: error.detail ?? 'clone check failed',
      });
    }

    return data;
  },
});

/**
 * *Initialise repository* (4.10, UX-DR12): starts a `repo-init@1` Run on the Repository's
 * `default_branch`. The same no-island, no-client-JS shape as `recheck` above — the row's
 * next render reads the new Run off `GET /projects/{id}`'s own embedded list.
 */
export const init = defineAction({
  accept: 'form',
  handler: async (form: FormData) => {
    const repositoryId = form.get('repositoryId');
    if (typeof repositoryId !== 'string' || repositoryId.length === 0) {
      throw new ActionError({ code: 'BAD_REQUEST', message: 'repositoryId is required' });
    }

    const { data, error } = await backend().POST('/api/v1/repositories/{repository_id}/init', {
      params: { path: { repository_id: repositoryId } },
    });

    if (error) {
      const code =
        error.status === 404
          ? 'NOT_FOUND'
          : error.status === 409
            ? 'CONFLICT'
            : 'INTERNAL_SERVER_ERROR';
      throw new ActionError({ code, message: error.detail ?? 'initialisation failed' });
    }

    return data;
  },
});
