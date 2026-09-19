/**
 * Save-button behaviour for `NewWorkflow.tsx` (story 5-3).
 *
 * Full button interaction tests (render, disabled state, click → POST /runs) are
 * `tests/e2e/new-workflow.spec.ts`'s job — `vitest.config.ts` runs in
 * `environment: 'node'` with no DOM-mounting library, the same constraint
 * `newwf-island.test.ts` documents.
 *
 * What is provable here:
 * - `NewWorkflow` is still a function component (no regression from adding the Save button).
 * - `runBody` — the body the island spreads before adding `{ save: true }` — never includes
 *   `conflict_consent`, so a save call can never accidentally forward consent the Operator
 *   never gave.
 */
import { describe, expect, it } from 'vitest';

import NewWorkflow from '../../src/islands/NewWorkflow';
import { runBody } from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';

type TemplateSummary = components['schemas']['TemplateSummaryOut'];

function aTemplate(): TemplateSummary {
  return {
    name: 'repo-init',
    description: '',
    latest_version: 1,
    versions: [1],
  };
}

describe('NewWorkflow save button', () => {
  it('component is still a function after adding the Save button', () => {
    expect(typeof NewWorkflow).toBe('function');
  });

  it('runBody does not include conflict_consent — save call cannot accidentally forward it', () => {
    const templates = [aTemplate()];
    const state = {
      template: 'repo-init' as const,
      projectId: 'proj-1',
      repositoryId: 'repo-1',
      baseBranch: 'main',
      budgetUsd: '10',
      inputs: {},
      harness: '',
      model: '',
      manualEstimateH: '',
      reReviewDone: false,
    };

    const body = runBody(state, templates);

    expect(body).not.toBeNull();
    // conflict_consent must not appear in the save body spread — it is island-local state
    // that only startRun appends, never saveRun (story 5-3: no consent payload on start Signal)
    expect(Object.prototype.hasOwnProperty.call(body, 'conflict_consent')).toBe(false);
  });
});
