# Run evidence

Baseline: Run `01a18ceb-7954-74b8-9517-a934d8e7250d`, `staged-initiative-hub`, 30 stories, 50h06, $150.29. One Run: evidence, not a rate.

## Where the time went

38h57 parked (78%), about 10h48 in agent attempts.

| Class | Stops | Wait | Who can end it after this work |
| --- | --- | --- | --- |
| Test-edit approval (1-7, 1-8, 2-4, 3-3) | 4 | 19h43 | Senior |
| Provider credit failure (1-6) | 1 | 13h08 | Human only; alert names the cause |
| Real decisions (1-3 twice) | 2 | 6h03 | Human, reached through chat |
| Delegated to Claude (5-1, 5-3 twice, 5-4, 5-5) | 5 | 3 min | Senior |

Overnight stops 1-6 and 3-3 cost 25h34, 66% of parked time.

## Replay estimates

Assumes 10-minute consults, unchanged work, and human stops answered within 30 minutes.

| Scenario | Run time |
| --- | --- |
| Actual | 50h |
| Senior only | About 32h |
| Senior and chat alerts | About 14h |

The 14-hour figure depends on human stops landing in waking hours.

## Risks seen in this Run

- 5-1's delegated answer falsely said `stories.yaml` was updated.
- 5-1's answer was sent to 5-3 by mistake; the agent caught it.
- 5-4 edited a security test, and the recap flags it for checking.
- Epic 4's retro found a `Breaks:` edit that weakened one assertion and parked three e2e tests.
- Three of five retros ended `rejected`, and the Run carried on past a live cross-association write.
- `repository.test_globs` was empty, so 105 attempts froze no test file and zero `protected_path` stops says nothing.

Sources: the Run recap and parks report (2026-11-01), and `gate_record` and `attempt` rows read from the instance.
