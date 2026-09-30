/**
 * `src/lib/projects/runs.ts` (4.10): the pure reads `index.astro` and `RepositoriesTable`
 * build a Repository row's `Initialise repository` control and the Runs list from.
 */
import { describe, expect, it } from 'vitest';

import { ageText, latestInitRun, type ProjectRunOut } from '../../src/lib/projects/runs';

const NOW = new Date('2026-09-06T12:00:00Z');

function run(overrides: Partial<ProjectRunOut>): ProjectRunOut {
  return {
    id: 'run-id',
    token: 'RUN',
    template: 'house-init@3',
    is_init: true,
    branch: 'main',
    repository_id: 'repo-id',
    current_step_label: 'install',
    reason: '',
    compare_urls: [],
    created_at: '2026-09-06T11:00:00Z',
    ...overrides,
  };
}

describe('ageText', () => {
  it('reads minutes under an hour', () => {
    expect(ageText('2026-09-06T11:45:00Z', NOW)).toBe('15m');
  });

  it('reads hours and minutes under a day', () => {
    expect(ageText('2026-09-06T09:07:00Z', NOW)).toBe('2h 53m');
  });

  it('reads days and hours at a day or more', () => {
    expect(ageText('2026-09-04T04:00:00Z', NOW)).toBe('2d 08h');
  });

  it('never reads negative for a clock a moment ahead', () => {
    expect(ageText('2026-09-06T12:00:05Z', NOW)).toBe('0m');
  });
});

describe('latestInitRun', () => {
  it('finds the first init run for the repository, newest first', () => {
    const runs = [
      run({ id: 'newer', repository_id: 'repo-1' }),
      run({ id: 'older', repository_id: 'repo-1' }),
    ];

    expect(latestInitRun(runs, 'repo-1')?.id).toBe('newer');
  });

  it('ignores a run of another repository', () => {
    const runs = [run({ repository_id: 'repo-2' })];

    expect(latestInitRun(runs, 'repo-1')).toBeNull();
  });

  /**
   * Operator decision 2026-09-30: no template name hardcoded in product code. The template
   * name is no longer what says "this Run initialised the Repository" — the server's own
   * `is_init` is (`INIT_TEMPLATE`, AD-20). Both replacements are stronger than the name
   * test they replace: a Run of another template *whose server says it is the init Run* is
   * now found, and a Run of the configured template whose server says it is not is ignored.
   */
  it('ignores a run the server did not mark as the init run', () => {
    const runs = [run({ template: 'house-init@3', is_init: false })];

    expect(latestInitRun(runs, 'repo-id')).toBeNull();
  });

  it('finds a run of any template the server marked as the init run', () => {
    const runs = [run({ id: 'marked', template: 'anything-at-all@7', is_init: true })];

    expect(latestInitRun(runs, 'repo-id')?.id).toBe('marked');
  });

  it('answers null when there is no run at all', () => {
    expect(latestInitRun([], 'repo-id')).toBeNull();
  });
});
