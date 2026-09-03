---
story: "1-4"
epic: 1
title: Design tokens and the instrument-dark shell
requirements: [NFR-6, NFR-8, UX-DR1, UX-DR2, UX-DR3, UX-DR5, UX-DR19]
binds: [AD-1, conventions "UI signal & voice"]
---

# Story 1.4 — Design tokens and the instrument-dark shell

As the Operator,
I want every screen to render inside one severe, monospace, dark shell built from a single set of tokens and a small set of base components,
So that later screens are assembled from proven parts and the signal rule (one coloured element per row, none when nothing needs me) holds by construction.

## Scope

**In:** `src/styles/tokens.css` + `base.css`, `src/layouts/Shell.astro`, static Astro components (`AppRail`, `SurfaceBar`, `FooterReadout`, `StatusToken`, `Button`, `KvTable`, `SectionHead`, `EmptyState`, `RecordRow`, `DenseTable`, `AlertBanner`, `CommandBlock` static part), route pages `/`, `/runs`, `/projects`, `/templates`, `/workflows/new` each rendering an empty readout inside the shell, token and contrast unit tests, Playwright smoke per page.
**Out:** login and auth guard (1.5); any data fetching; React islands.

## Binding rules (inlined)

- **Tokens (UX-DR1, `DESIGN.md`).** CSS custom properties, exact values: `--color-bg #0B0D0E`, `--color-surface #111416`, `--color-surface-raised #171B1D`, `--color-surface-rail #0E1113`, `--color-surface-inset #08090A`, `--color-line #21272A`, `--color-line-strong #2C3438`, `--color-text #DDE3E5`, `--color-text-secondary #8B979B`, `--color-text-tertiary #5C686C`, `--color-signal-run #4FB477` (green), `--color-signal-needs-you #E4B33C` (amber), `--color-signal-failed #E05252` (red), `--color-accent #7FD4C1`. Typography roles as `--type-<role>` (size/line-height/letter-spacing): detail-title 19/1.3/-0.01em; question 14/1.7; command 13/1.7; body 13/1.45; surface-title 13 uppercase 0.18em; row-title 12.5/1.4; row-body 12.5/1.55; meta 11.5/1.45; micro 11/1.6; status-token 11/0.10em; control 11 uppercase 0.12em; eyebrow 10.5 uppercase 0.16em; column-head 10 uppercase 0.18em; section-head 10 uppercase 0.22em. One monospace stack, `font-weight: 400` everywhere. Spacing scale `--space-1..16` on a 2px base with the odd intermediates (5 = 10px, 7 = 14px, 9 = 18px); `--rail-width: 172px`, `--page-max: 1180px`, `--detail-max: 940px`, `--section-gap: 34px`. `border-radius: 0` and no `box-shadow` anywhere except `inset 2px 0 0 var(--color-accent)` on the active rail item.
- **Signal rule (UX-DR2, NFR-6).** Colour appears only on the 7px status chip and its token, a column header, the rail's "n need you" count, a 2px alert-banner left rule, an aged wait, a single failure line in a readout, and the login rejection line. Status is always a word token from `QUE RUN BLK CHK DON ERR CAN SKP`. An empty screen has no amber or red pixel.
- **Shell (UX-DR3).** Rail 172px on `surface-rail`, brand block with the subtitle `MVP · single operator`, items *Workflows* (count + `n need you` amber when n > 0), *Runs*, group `CONFIGURE`: *Projects*, *Templates*; footer readout `{n} running · {m} queued / {k} need you / updated hh:mm:ss · refresh`. Surface bar: surface title, count, filters right, hairline bottom. No page hero.
- **Record grid (UX-DR5).** Five fixed columns `52px 128px 210px 1fr 74px`; dense tables are a separate component with as many columns as the data has and the same hairlines.
- **Voice (NFR-8).** Empty states are readouts: uppercase headline then what is happening instead; never an illustration or congratulation.
- **Accessibility (UX-DR19).** WCAG 2.2 AA contrast for `--color-text` and `--color-text-secondary` on every ground token; focus ring `1px solid var(--color-accent)` at 1px offset on every focusable element, never removed; desktop ≥ 1280px, no breakpoints (horizontal scroll below ~1024px).
- **Islands only where the page cannot work without them**; everything in this story is static `.astro`.

## Acceptance criteria

**Given** `tokens.css`
**When** the Vitest token test parses it
**Then** every colour, type role, spacing, and layout token above exists with the exact value, and the stylesheet set contains no `border-radius` other than `0` and no `box-shadow` other than the accent inset.

**Given** the contrast test
**When** it computes WCAG contrast for `--color-text` and `--color-text-secondary` against `bg`, `surface`, `surface-raised`, `surface-rail`
**Then** every pair is ≥ 4.5:1 and `--color-text-tertiary` ≥ 3:1 against `bg` and `surface`.

**Given** any of `/`, `/runs`, `/projects`, `/templates`, `/workflows/new`
**When** rendered
**Then** it shows the rail with the active item marked, a surface bar with the surface title, an `EmptyState` readout in the body (`NOTHING REGISTERED` on `/`, `NO RUNS` on `/runs`, `NO PROJECTS` on `/projects`, `NO TEMPLATES` on `/templates`), the footer readout `0 running · 0 queued / 0 need you / updated —`, and a Playwright assertion finds no element whose computed colour equals the amber or red token.

**Given** the `StatusToken` component
**When** rendered with each of `QUE RUN BLK CHK DON ERR CAN SKP`
**Then** it outputs a 7px square chip and the three-letter token in the same colour, green for `RUN`, amber for `BLK`/`CHK`, red for `ERR`, tertiary grey otherwise, with `data-token` set.

**Given** keyboard navigation on any page
**When** an element receives focus
**Then** the accent focus ring is visible (Playwright `toHaveCSS('outline-color', …)`).

## Implementation notes

- `src/styles/tokens.css`, `src/styles/base.css` (reset, body ground, focus ring, `font-family` stack), imported once in `src/layouts/Shell.astro`.
- Components in `src/components/`: props are plain strings/numbers; `StatusToken.astro` maps token → colour class; `EmptyState.astro` takes `headline` and `lines[]`; `FooterReadout.astro` takes the four figures; `AppRail.astro` takes `active` and the counts.
- Test-ids (UX-DR18): `nav-workflows`, `nav-runs`, `nav-projects`, `nav-templates`, `nav-needs-you`, `board-empty`, `runs-empty`, `projects-empty`, `templates-empty`, `footer-readout`.
- Pages are `.astro` files under `src/pages/` (`index.astro`, `runs/index.astro`, `projects/index.astro`, `templates/index.astro`, `workflows/new.astro`); `runs/[id].astro` waits for Epic 4.
- Playwright: `tests/e2e/shell.spec.ts` (one test per route + the no-signal-colour assertion via `page.evaluate` scanning computed styles).

## Verification

```bash
make lint && make test && make e2e-ui
```

## Sources for detail only

`DESIGN.md` §Colors, §Typography, §Layout & Spacing, §Elevation, §Shapes, §Components, §Do's and Don'ts. `EXPERIENCE-v1.md` §Attention model, §Information architecture (Shell), §Voice. PRD NFR-6, NFR-8.
