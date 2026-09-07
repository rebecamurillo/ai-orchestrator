/**
 * `src/lib/projects/runs.ts` (4.10): the pure reads `index.astro` and `RepositoriesTable`
 * build a Repository row's `Initialise repository` control and the Runs list from.
 */
import { describe, expect, it } from 'vitest';

import { ageText, latestRepoInitRun, type ProjectRunOut } from '../../src/lib/projects/runs';

const NOW = new Date('2026-09-06T12:00:00Z');

function run(overrides: Partial<ProjectRunOut>): ProjectRunOut {
  return {
    id: 'run-id',
    token: 'RUN',
    template: 'repo-init@1',
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

describe('latestRepoInitRun', () => {
  it('finds the first repo-init run for the repository, newest first', () => {
    const runs = [
      run({ id: 'newer', repository_id: 'repo-1' }),
      run({ id: 'older', repository_id: 'repo-1' }),
    ];

    expect(latestRepoInitRun(runs, 'repo-1')?.id).toBe('newer');
  });

  it('ignores a run of another repository', () => {
    const runs = [run({ repository_id: 'repo-2' })];

    expect(latestRepoInitRun(runs, 'repo-1')).toBeNull();
  });

  it('ignores a run of a different template', () => {
    const runs = [run({ template: 'epic@1' })];

    expect(latestRepoInitRun(runs, 'repo-id')).toBeNull();
  });

  it('answers null when there is no run at all', () => {
    expect(latestRepoInitRun([], 'repo-id')).toBeNull();
  });
});
