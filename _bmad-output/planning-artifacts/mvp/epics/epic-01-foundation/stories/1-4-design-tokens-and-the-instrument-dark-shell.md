---
title: 'Design tokens and the instrument-dark shell'
type: 'feature'
created: '2026-09-03'
status: 'done'
baseline_commit: '76b0a851eb83e5f02d33ce389e5b2591c404b20d'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-4-design-tokens-and-shell.md'
  - '{project-root}/_bmad-output/implementation-artifacts/epic-1-context.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** web-client serves one placeholder page with no stylesheet, no shell, and no
components. Every screen from 1.5 on would invent its own colours, type sizes, and grid, and the
signal rule (one coloured element per row; no amber or red when nothing needs the Operator) would
be prose nobody can check.

**Approach:** Put the whole visual system in `src/styles/tokens.css` as CSS custom properties with
the exact values `DESIGN.md` fixes, a reset and focus ring in `base.css`, one `Shell.astro` layout
(rail · surface bar · footer readout), and twelve static `.astro` components built only from those
tokens. Render the five routes the MVP declares as empty readouts inside that shell. Prove it with
Vitest — token values, WCAG contrast, stylesheet shape, and `astro/container`-rendered components —
and with a Playwright spec per route that finds no amber or red pixel and a visible focus ring.

## Boundaries & Constraints

**Always:**
- Token values are exactly the brief's: fourteen `--color-*`, fourteen `--type-*` roles (size, plus
  `-line` / `-tracking` / `-transform` only where the brief states one), `--space-1..16` on a 2px
  base, `--rail-width: 172px`, `--page-max: 1180px`, `--detail-max: 940px`, `--section-gap: 34px`,
  and the fixed record grid `52px 128px 210px 1fr 74px`. One monospace stack, `font-weight: 400`
  everywhere.
- Shape: `border-radius` is `0` and nothing else, anywhere in the stylesheet set; the only
  `box-shadow` is `inset 2px 0 0 var(--color-accent)` on the active rail item.
- Signal rule (UX-DR2, NFR-6): a signal colour appears only on the 7px chip and its three-letter
  token, a column head, the rail's `n need you` count, a 2px `AlertBanner` left rule, an aged wait,
  and a single failure line. An empty screen has no amber or red pixel. Status is always a word
  token from `QUE RUN BLK CHK DON ERR CAN SKP`; `skipped` and `unvalidated` are words, never green.
- Accessibility (UX-DR19): `--color-text` and `--color-text-secondary` ≥ 4.5:1 on `bg`, `surface`,
  `surface-raised`, `surface-rail`; `--color-text-tertiary` ≥ 3:1 on `bg` and `surface`; focus ring
  `1px solid var(--color-accent)` at 1px offset, never removed. No breakpoints.
- Voice (NFR-8): empty states are readouts — an uppercase headline, then what is happening instead.
  No congratulation, no apology, no illustration, no call-to-action as the only content.
- AD-1: everything this story adds is static `.astro`; no `fetch`, no import of `src/api/server`,
  no `astro:env`. eslint already enforces this on `src/components/**`.
- Tests first (AD-18): every test module lands red before the module it covers exists.
- No new environment variable; the contract stays at 25 settings fields / 31 `.env.example`
  variables. No new runtime dependency.
- Existing files are revised in place, never moved, renamed, or replaced. `SPEC.md`,
  `stories.yaml`, both `AGENTS.md`, `GUIDELINES.md`, `README.md`'s BMAD section and every
  `backend-api/tests/**` file are untouched; `backend-api/tests/unit/test_makefile.py` comes out
  byte-identical.
- No `.env` and no real secret is committed.

**Ask First:**
- Any dependency, top-level directory, or environment variable the brief does not name.
- Any change that makes a gate pass by weakening it — an eslint or ts ignore, a skipped test, a
  widened contract, a lowered threshold.
- Deleting or overwriting any existing file.

**Never:** login, `src/middleware.ts`, the session cookie, Actions (1.5); Dockerfiles and compose
(1.6); CI and coverage (1.7); React islands, nanostores, polling, CodeMirror, dagre, and any data
fetching (later epics); `runs/[id]`, the board columns, the LIST toggle, filters with behaviour, a
`refresh` control; a second font family, a font weight above 400, a light theme, a breakpoint.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Token parse | `tokens.css` | every colour, type role, space step and layout token exists with the brief's exact value | a missing or altered value fails the token test naming it |
| Stylesheet shape | every `.css` and every `.astro` `<style>` | no `border-radius` but `0`; no `box-shadow` but the accent inset; no hex colour outside `tokens.css`; every `var(--…)` referenced is defined in `tokens.css` | the offending file and declaration are named |
| Contrast | the ground and text tokens | text and text-secondary ≥ 4.5:1 on the four grounds; text-tertiary ≥ 3:1 on bg and surface | the failing pair and its ratio are printed |
| `StatusToken` | each of `QUE RUN BLK CHK DON ERR CAN SKP` | `data-token` set, a 7px square chip and the token in one colour: `RUN` green, `BLK`/`CHK` amber, `ERR` red, the rest tertiary grey | an unmapped token renders neutral, never green |
| `AppRail` needs-you | `needsYou: 3` | a `nav-needs-you` count reading `3 need you` on the amber signal | `needsYou: 0` renders no such element at all |
| Empty route | `GET /`, `/runs`, `/projects`, `/templates`, `/workflows/new` on the preview server | 200; rail with the active item carrying `aria-current="page"`; surface bar title; the route's `EmptyState` readout; `0 running · 0 queued / 0 need you / updated —` | N/A |
| Signal-free screen | any of those five rendered | no element's computed colour, background, visible border, outline, or shadow equals the amber or red token | the failing selector and property are printed |
| Focus | `Tab` on any page | the focused element's `outline-color` is the accent and `outline-style` is `solid` | N/A |

</frozen-after-approval>

## Code Map

Read-only / must not change:
- `AGENTS.md`, `web-client/AGENTS.md`, `SPEC.md`, `stories.yaml`, `GUIDELINES.md` — anchors.
- Every file under `backend-api/`. This story lands no gate, so hard rule 1's pending-gate
  exception does not apply and `backend-api/tests/unit/test_makefile.py` is untouched.
- `web-client/src/api/schema.d.ts` (generated, AD-3), `src/api/server.ts`, `src/api/client.ts`,
  `src/pages/api/[...path].ts`, `eslint.config.js`, `astro.config.mjs`, `playwright.config.ts`,
  `Makefile`, `.env.example` — nothing this story adds touches them.
- `web-client/tests/e2e/no-credential.spec.ts` — it greps `dist/client` for the token and asserts
  `GET /` is 200; new CSS in the bundle does not affect it.

Existing, edited in place:
- `web-client/src/pages/index.astro` — the placeholder 1.3 wrote for 1.4 to replace ("Placeholder.
  Story 1.4 replaces this with the Board inside the instrument-dark shell"). Becomes the Board
  route rendering `NOTHING REGISTERED` inside `Shell`.
- `web-client/vitest.config.ts` — wrapped in `getViteConfig` from `astro/config` so a unit test can
  import an `.astro` component. Verified during planning: the existing `astro:env/server` alias and
  all 39 existing tests still pass under the wrapped config.
- `web-client/tests/e2e/smoke.spec.ts` — see the Spec Change Log entry. Its single assertion
  (`main` reads `web-client up`) is unsatisfiable once `/` is the Board, which the file's own
  comment says 1.4 makes it.

Reuse pointers:
- `_bmad-output/planning-artifacts/mvp/epics/epic-01-foundation/briefs/1-4-design-tokens-and-shell.md`
  — the token table, the shell layout, the test-ids, and the five acceptance criteria, verbatim.
- `DESIGN.md` §Components (`ux-designs/ux-ai-orchestrator-2026-08-25/`) — the per-component detail:
  rail item states, surface bar, record row, alert banner rule, empty state, command block, buttons.
- `EXPERIENCE-v1.md` §Attention model / §Information architecture — the three-hue signal set, the
  rail items and footer format, the `newwf` test-id prefix.
- `web-client/tests/unit/lint.test.ts:60` `lints the real sources with no error` — already lints
  `src/`, so every new `.astro` file is covered by the existing eslint gate.
- `web-client/tests/e2e/config.ts` — `PREVIEW_URL`; the new spec imports nothing else.

Verified during planning (do not re-verify):
- Contrast holds with the brief's values: text 13.37–15.02, text-secondary 5.78–6.49,
  text-tertiary 3.02–3.47 across the four grounds. No token needs adjusting.
- `astro/container` + `getViteConfig` renders `.astro` components under Vitest 4.1.11 here.
- `tsc --noEmit` cannot resolve `import X from '…​.astro'` from a `.ts` file; a
  `declare module '*.astro'` shim in `tests/types/` fixes it and does **not** weaken `astro check`
  — it still reports the missing-prop error on a component used wrongly.
- eslint raises nothing on an `.astro` file that declares `interface Props`.
- A 2px base already yields the brief's odd intermediates (`--space-5` 10px, `-7` 14px, `-9` 18px).

## Tasks & Acceptance

**Execution:** (tests first — each `*.test.ts` lands red before the files it names exist)

- [x] `web-client/tests/unit/tokens.test.ts` + `src/styles/tokens.css` — parse the custom properties
      and assert every colour, type role, space step, layout and grid token against the brief's
      table — the token set is a checked contract, not a stylesheet convention.
- [x] `web-client/tests/unit/contrast.test.ts` — compute WCAG 2.2 ratios from the parsed tokens for
      the pairs UX-DR19 names — AA is proven from the values, not asserted in prose.
- [x] `web-client/tests/unit/stylesheets.test.ts` — over `src/styles/*.css` and every `<style>` in
      `src/**/*.astro`: radius only `0`, shadow only the accent inset, no hex outside `tokens.css`,
      every referenced `var(--…)` defined — the shape rules hold for files this story never sees.
- [x] `web-client/tests/types/astro-modules.d.ts` + `vitest.config.ts` — `declare module '*.astro'`
      and `getViteConfig` — what lets a unit test render a component at all.
- [x] `web-client/src/styles/base.css` — reset (including `border-radius: 0` and `font-weight: 400`
      globally), body ground, monospace stack, `:focus-visible` ring, link colour — the ground every
      component sits on; no `outline: none` anywhere.
- [x] `web-client/src/components/StatusToken.astro` — `data-token`, `data-signal`, a 7px chip on
      `background: currentColor` — chip and token share one colour by construction.
- [x] `web-client/src/components/{AppRail,SurfaceBar,FooterReadout,EmptyState}.astro` — the shell
      parts: rail (brand, `MVP · single operator`, Workflows + amber `n need you` when n > 0, Runs,
      `CONFIGURE` group with Projects and Templates, `aria-current` + accent inset on the active
      item), surface bar (title, count, right-aligned filters slot, hairline bottom, no hero),
      footer readout, empty readout with `headline` and `lines[]`.
- [x] `web-client/src/components/{SectionHead,Button,KvTable,RecordRow,DenseTable,AlertBanner,CommandBlock}.astro`
      — the remaining base components on the same tokens: outline-only buttons, the fixed
      five-column record grid, a dense table with the same hairlines, the 2px signal left rule, the
      `surface-inset` command block — later screens are assembled, not re-invented.
- [x] `web-client/tests/unit/components.test.ts` — render each with `astro/container`: the
      `StatusToken` matrix, `AppRail` with and without a needs-you count and its active marker,
      `EmptyState`, `FooterReadout`, `RecordRow`'s grid — the component acceptance criteria.
- [x] `web-client/src/layouts/Shell.astro` — imports both stylesheets once, composes rail, surface
      bar, `<slot />` capped at `--page-max`, footer readout; props `active`, `title`, `count`, and
      the four figures defaulting to `0 / 0 / 0 / —` — one shell wraps every route.
- [x] `web-client/src/pages/index.astro` (edited), `runs/index.astro`, `projects/index.astro`,
      `templates/index.astro`, `workflows/new.astro` — each an empty readout inside `Shell` with the
      brief's test-ids — every route is reachable before its data exists.
- [x] `web-client/tests/e2e/shell.spec.ts` — per route: 200, active rail item, surface title, the
      empty readout, the footer text, and a `page.evaluate` scan of every element's computed colour,
      background, visible border, outline and shadow for the amber and red tokens; plus the focus
      ring after `Tab` — the signal rule and UX-DR19 as gates.
- [x] `web-client/tests/e2e/smoke.spec.ts` — its one assertion is retargeted from the retired
      placeholder to the Board readout now served at `/`; the file, its name and its purpose stay.

**Acceptance Criteria:**

- Given a clean checkout, when `make lint` runs, then it exits 0 — eslint, prettier, `tsc --noEmit`
  and `astro check` all pass over the new `.astro`, `.css` and `.d.ts` files, and the env-contract
  line still reports 25 settings fields and 31 `.env.example` variables.
- Given a clean checkout, when `make test` runs, then it exits 0 and the four new Vitest modules
  ran alongside the six that already existed.
- Given `make openapi` is run twice, then `git status --porcelain` is empty — this story changes
  neither the contract nor the generated types.
- Given the built preview server, when `make e2e-ui` runs, then Playwright reports the five route
  smokes, the two signal-colour scans, the focus-ring test, the retargeted smoke and the five
  credential specs passed.
- Given the stack from 1.2 running, when `make e2e-api` runs, then it still exits 0.
- Given a token value in `tokens.css` is changed by one digit, when `make test` runs, then the
  token test fails naming that token — the contract is not vacuous.
- Given the finished story, when the diff is inspected, then no file is deleted or renamed, nothing
  under `backend-api/` changed, `GUIDELINES.md` and `README.md`'s BMAD section are untouched, and no
  `.env` or real secret is staged.

## Spec Change Log

**`tests/e2e/smoke.spec.ts` is revised, and hard rule 1 says an existing test file is frozen.**
The conflict is unavoidable and was found in planning, not invented to pass a gate. The brief's
third acceptance criterion requires `/` to render `NOTHING REGISTERED` inside the shell; that makes
`expect(page.locator('main')).toHaveText('web-client up')` unsatisfiable by any implementation.
Story 1.3 wrote both the page and the assertion as an explicit hand-off — `src/pages/index.astro`
reads "Placeholder. Story 1.4 replaces this with the Board", and the spec file reads "`/` is a
placeholder until 1.4 replaces it with the Board". The options were: leave it and ship `make e2e-ui`
red, which would strand every later story since AD-18 judges them by that gate; delete the file; or
revise its one assertion. The narrowest of the three is taken — the file, its name, its docstring's
purpose and its single test survive; only the expected text changes, from the retired placeholder
to what `/` now serves. Coverage strictly increases in the same commit: `tests/e2e/shell.spec.ts`
adds a full smoke for `/` plus four more routes. This is a deviation to be ratified, not a
precedent: no other existing test file is touched, and `backend-api/tests/unit/test_makefile.py`
comes out byte-identical.

**Ratified by the operator on 2026-09-04, commit `055e228`.** Hard rule 1 now carries a second
named exception covering exactly this case: a test that names a later story as the thing that
replaces what it asserts may have that assertion revised by that story, and only if the same
commit adds coverage that strictly exceeds it. The same amendment says not to write such an
assertion in the first place — a test covering a placeholder asserts that the route is served,
not the placeholder's copy. The verification that made the conflict undeniable: restoring 1.3's
file and running the gate gives `1 failed, 22 passed`, `make e2e-ui` exit 2, with
`Expected: "web-client up"` against a `main` that reads `NOTHING REGISTERED…`.

## Design Notes

`data-signal` is what makes the signal rule checkable from both ends. `StatusToken` maps the eight
word tokens onto four values — `run`, `needs-you`, `failed`, `neutral` — the unit test asserts the
mapping on rendered HTML, and one CSS rule per value assigns the colour, with the chip on
`background: currentColor` so chip and token cannot drift apart:

```css
.status[data-signal='needs-you'] { color: var(--color-signal-needs-you); }
.chip { width: 7px; height: 7px; background: currentColor; }
```

The rail's needs-you count is not rendered at all when the figure is zero, rather than rendered
grey. "No amber pixel on an empty screen" then holds by construction, and the Playwright scan is a
check on that construction rather than the thing keeping it true.

## Verification

**Commands:**
- `make lint` — exits 0.
- `make test` — exits 0; ten Vitest modules and the backend unit suite ran.
- `make openapi` twice — `git status --porcelain` empty afterwards.
- `make e2e-ui` — exits 0.
- `make e2e-api` — exits 0 against the running stack (README "Running it").
- `git diff --stat backend-api` — empty.

## Suggested Review Order

**The token contract**

- Fourteen colours, fourteen type roles, a 2px scale — every value the product uses.
  [`tokens.css:1`](../../../../../../web-client/src/styles/tokens.css#L1)

- The record grid as a token: five fixed columns, the same on every surface.
  [`tokens.css:129`](../../../../../../web-client/src/styles/tokens.css#L129)

- The reset makes square corners and weight 400 absolute rather than per component.
  [`base.css:1`](../../../../../../web-client/src/styles/base.css#L1)

- Dark-first stated to the browser, so its own chrome sits on the same ground.
  [`base.css:15`](../../../../../../web-client/src/styles/base.css#L15)

- The focus ring, declared once and removed nowhere.
  [`base.css:85`](../../../../../../web-client/src/styles/base.css#L85)

**The signal rule**

- Eight word tokens mapped onto three hues; `data-signal` is the whole mapping.
  [`StatusToken.astro:14`](../../../../../../web-client/src/components/StatusToken.astro#L14)

- The chip takes `currentColor`, so chip and token cannot drift apart.
  [`StatusToken.astro:54`](../../../../../../web-client/src/components/StatusToken.astro#L54)

- A zero needs-you count renders nothing: no amber pixel, by construction.
  [`AppRail.astro:52`](../../../../../../web-client/src/components/AppRail.astro#L52)

- The one box-shadow in the system, on the active rail item.
  [`AppRail.astro:138`](../../../../../../web-client/src/components/AppRail.astro#L138)

**The shell and its routes**

- One layout imports both stylesheets and composes rail, bar, body, readout.
  [`Shell.astro:14`](../../../../../../web-client/src/layouts/Shell.astro#L14)

- The Board route, replacing 1.3's placeholder with the empty readout.
  [`index.astro:15`](../../../../../../web-client/src/pages/index.astro#L15)

- The fixed five-column grid, read from the token rather than restated.
  [`RecordRow.astro:41`](../../../../../../web-client/src/components/RecordRow.astro#L41)

**How it is checked**

- Computed styles in a real browser: the only honest test of "no amber pixel".
  [`shell.spec.ts:55`](../../../../../../web-client/tests/e2e/shell.spec.ts#L55)

- prettier owns the file's spelling; both sides compare through one normaliser.
  [`tokens.test.ts:35`](../../../../../../web-client/tests/unit/tokens.test.ts#L35)

- Astro's Vite pipeline under Vitest is what lets a test render a component.
  [`vitest.config.ts:6`](../../../../../../web-client/vitest.config.ts#L6)
