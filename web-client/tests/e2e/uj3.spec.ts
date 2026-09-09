import { expect, test } from '@playwright/test';

import { BACKEND_API_URL, ORCHESTRATOR_TOKEN, USE_REAL_BACKEND } from './config';
import { cancelRun, putFile, startParkedRun, waitFor } from './uj3-fixture';

/**
 * UJ-3 in a real browser against a real stack (6.8, SPEC CAP-8, UJ-3, SM-2).
 *
 * Every other spec in this suite mocks `page.route()` — there is no engine behind them and
 * their subject is what the screen does with a given response. This one is the opposite: the
 * screen is driven by a Run that is actually walking a plan, on the scripted `fake` harness,
 * so what is proven is the thing no mock can show — that the Operator's clicks reach the
 * engine and that the next thing she sees is the state the engine really moved to.
 *
 * It needs `E2E_BACKEND=real` and a stack in test mode (`ORCH_TEST_MODE=1`), which the
 * disposable `aio-e2e` stack is; the default `make e2e-ui` runs against the stub backend and
 * skips this file rather than failing it, because there is no Run there to drive.
 *
 * **What is asserted after the Answer.** Not the literal `RUN` token: the scripted harness is
 * fast enough that the Run can be parked again at story 2's own checkpoint before the poll
 * that follows the click lands, and a spec that raced that would be flaky rather than
 * strict. The browser asserts what is stable and is the Operator's own reading — the blocked
 * stop is gone and the Run is no longer `BLK` — while the timing itself ("`running` on the
 * very next API read, inside five seconds") is measured in
 * `backend-api/tests/e2e/test_uj3.py::test_a_the_answer_puts_the_run_back_to_running_within_one_poll`.
 *
 * **Why the gate-file repair is an API call and not a click.** The ARTIFACTS panel edits a
 * file the tree lists; the file this journey puts back was deleted by the scripted agent, so
 * it is not in the tree to select and the panel offers no way to create one. `PUT
 * /runs/{id}/files` does, which is the endpoint the panel itself saves through.
 */

const ANSWER = "Post to the project's channel only";
const QUESTION = 'Where should the notification be posted?';
const GATE_FILE = 'specs/gates/GATE_OK';

/** Long by design: a real Run walks a real plan through a durable engine (brief: under 5 min). */
const JOURNEY_TIMEOUT_MS = 300_000;
/** One stop is at most one 30 s poll away once the Run has settled into `needs_you`. */
const STOP_TIMEOUT_MS = 90_000;

test.describe('UJ-3: come back cold and unblock', () => {
  test.skip(!USE_REAL_BACKEND, 'the journey drives a real Run; E2E_BACKEND=real is required');
  test.describe.configure({ mode: 'serial' });

  test('answer, continue, skip — and the Run ends DON naming what was skipped', async ({
    page,
  }) => {
    test.setTimeout(JOURNEY_TIMEOUT_MS);
    const { runId, projectId } = await startParkedRun(BACKEND_API_URL, ORCHESTRATOR_TOKEN);

    try {
      // ── the Board: the card that needs her ────────────────────────────────────────────
      await page.goto(`/?project=${projectId}`);
      const card = page.getByTestId(`board-card-${runId}`);
      await expect(card).toBeVisible({ timeout: STOP_TIMEOUT_MS });
      await expect(page.getByTestId('board-column-needs_you')).toContainText('BLK');

      // ── the stop: the agent's own question, and the answer ────────────────────────────
      await card.click();
      await expect(page).toHaveURL(new RegExp(`/workflows/${runId}$`));
      await expect(page.getByTestId('wf-header')).toBeVisible();
      await expect(page.getByTestId('wf-token')).toHaveText('BLK');
      await expect(page.getByTestId('wf-question')).toContainText(QUESTION);

      await page.getByTestId('wf-answer').fill(ANSWER);
      await page.getByTestId('wf-signal-answer').click();

      await expect(page.getByTestId('wf-stop-blocked')).toHaveCount(0);
      await expect(page.getByTestId('wf-token')).not.toHaveText('BLK');

      // ── the spec checkpoint: read the plan, continue ──────────────────────────────────
      await expect(page.getByTestId('wf-stop-checkpoint')).toBeVisible({
        timeout: STOP_TIMEOUT_MS,
      });
      await expect(page.getByTestId('wf-token')).toHaveText('CHK');
      await page.getByTestId('wf-signal-continue').click();
      await expect(page.getByTestId('wf-stop-checkpoint')).toHaveCount(0);

      // ── the failed gate: repair the file the agent deleted, then give up on the Story ──
      await expect(page.getByTestId('wf-stop-verify_failed')).toBeVisible({
        timeout: STOP_TIMEOUT_MS,
      });
      await expect(page.getByTestId('wf-alert')).toContainText('verify failed 2/2');
      await putFile(BACKEND_API_URL, ORCHESTRATOR_TOKEN, runId, GATE_FILE, '1\n');

      await page.getByTestId('wf-signal-skip_story').click();
      await expect(page.getByTestId('wf-confirm-skip_story-line')).toContainText(
        'skipped by operator',
      );
      await page.getByTestId('wf-confirm-skip_story-yes').click();

      // ── the end: DON, the skipped id, and no active-time figure (Epic 8) ──────────────
      await waitFor(
        BACKEND_API_URL,
        ORCHESTRATOR_TOKEN,
        runId,
        (detail) => detail.run.status === 'done',
        'the Run finishing after the skip',
        JOURNEY_TIMEOUT_MS,
      );
      await page.reload();
      await expect(page.getByTestId('wf-token')).toHaveText('DON', { timeout: STOP_TIMEOUT_MS });
      await expect(page.getByTestId('wf-summary')).toContainText('skipped: 3');
      // The fixture's origin is a `file://` URL, and `pr_link.py` records no compare URL for
      // a host it cannot build one for ("no compare link for this host") — so the links list
      // is correctly empty here, and the skipped id is read off the summary line instead.
      await expect(page.getByTestId('wf-cost')).toContainText('your active time');
      await expect(page.getByTestId('wf-cost')).toContainText('—');
    } finally {
      await cancelRun(BACKEND_API_URL, ORCHESTRATOR_TOKEN, runId);
    }
  });
});
