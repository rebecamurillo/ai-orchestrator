/**
 * The Action registry Astro looks for. It searches `src/actions.*` and `src/actions/index.*`
 * for a `server` export and builds `astro:actions` from it, so an Action that is not named
 * here does not exist as far as a form is concerned.
 */
import { login } from './login';
import { save } from './projects';
import { recheck } from './repositories';

export const server = { login, repositories: { recheck }, projects: { save } };
