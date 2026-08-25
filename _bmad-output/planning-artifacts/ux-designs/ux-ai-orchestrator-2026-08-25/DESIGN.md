---
title: AI Orchestrator — Design
status: draft
created: 2026-08-25
updated: 2026-08-25
name: AI Orchestrator
description: Single-operator control surface for an autonomous development pipeline. Instrument-dark — a severe all-monospace readout on a fixed column grid, where colour is signal and never decoration. Dark-first, from scratch, no inherited UI system.
colors:
  # ground: four tonal planes, near-black and slightly green-cool
  bg: '#0B0D0E'
  surface: '#111416'
  surface-raised: '#171B1D'
  surface-rail: '#0E1113'
  surface-inset: '#08090A'
  surface-input: '#0A0C0D'
  # hairlines: the only structural device
  line: '#21272A'
  line-strong: '#2C3438'
  # text: three weights of legibility, never colour-coded
  text: '#DDE3E5'
  text-secondary: '#8B979B'
  text-tertiary: '#5C686C'
  # signal: one per escalation type, used on the chip and its token only
  signal-blocked: '#E4B33C'
  signal-qa: '#4FB477'
  signal-budget: '#D9663D'
  signal-rework: '#C25C86'
  signal-infra: '#E05252'
  signal-criterion: '#6C8CD5'
  # interaction: the single non-signal accent
  accent: '#7FD4C1'
typography:
  # Every role is monospace. There is no second family and no weight above 400.
  font-family-mono: 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, "Liberation Mono", monospace'
  detail-title:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 19px
    fontWeight: '400'
    lineHeight: '1.3'
    letterSpacing: -0.01em
  question:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 14px
    fontWeight: '400'
    lineHeight: '1.7'
  command:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.7'
  body:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.45'
  surface-title:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 13px
    fontWeight: '400'
    lineHeight: '1.45'
    letterSpacing: 0.18em
  row-title:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 12.5px
    fontWeight: '400'
    lineHeight: '1.4'
  row-body:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 12.5px
    fontWeight: '400'
    lineHeight: '1.55'
  meta:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 11.5px
    fontWeight: '400'
    lineHeight: '1.45'
  micro:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 11px
    fontWeight: '400'
    lineHeight: '1.6'
  status-token:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 11px
    fontWeight: '400'
    lineHeight: '1'
    letterSpacing: 0.10em
  control:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 11px
    fontWeight: '400'
    lineHeight: '1'
    letterSpacing: 0.12em
  eyebrow:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 10.5px
    fontWeight: '400'
    lineHeight: '1'
    letterSpacing: 0.16em
  column-head:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 10px
    fontWeight: '400'
    lineHeight: '1'
    letterSpacing: 0.18em
  section-head:
    fontFamily: '{typography.font-family-mono}'
    fontSize: 10px
    fontWeight: '400'
    lineHeight: '1'
    letterSpacing: 0.22em
rounded:
  DEFAULT: 0
  sm: 0
  md: 0
  lg: 0
  xl: 0
  full: 9999px   # reserved, unused in product chrome — see Shapes
spacing:
  '0': 0
  '1': 2px
  '2': 4px
  '3': 6px
  '4': 8px
  '5': 10px
  '6': 12px
  '7': 14px
  '8': 16px
  '9': 18px
  '10': 20px
  '12': 24px
  '14': 28px
  '16': 32px
  '20': 40px
  '32': 64px
  row-padding-y: 7px
  row-padding-x: 10px
  cell-gutter: 10px
  detail-padding-x: 28px
  detail-padding-y: 26px
  section-gap: 34px
  rail-width: 172px
  page-max: 1180px
  detail-max: 940px
  board-column-width: 232px
  chip-size: 7px
  hairline: 1px
components:
  app-rail:
    width: '{spacing.rail-width}'
    background: '{colors.surface-rail}'
    borderRight: '{spacing.hairline} solid {colors.line}'
    itemColor: '{colors.text-secondary}'
    itemColorActive: '{colors.text}'
    itemBackgroundActive: '{colors.surface-raised}'
    itemMarkerActive: 'inset 2px 0 0 {colors.accent}'
    groupLabel: '{typography.column-head}'
  surface-bar:
    padding: '{spacing.6} {spacing.8}'
    borderBottom: '{spacing.hairline} solid {colors.line}'
    title: '{typography.surface-title}'
    count: '{colors.text-tertiary}'
  filter-group:
    border: '{spacing.hairline} solid {colors.line}'
    radius: '{rounded.DEFAULT}'
    itemTypography: '{typography.control}'
    itemColor: '{colors.text-tertiary}'
    itemColorActive: '{colors.text}'
    itemBackgroundActive: '{colors.surface-raised}'
  text-input:
    background: '{colors.surface-input}'
    border: '{spacing.hairline} solid {colors.line}'
    radius: '{rounded.DEFAULT}'
    color: '{colors.text-secondary}'
    typography: '{typography.meta}'
    padding: '{spacing.2} {spacing.4}'
  status-chip:
    size: '{spacing.chip-size}'
    radius: '{rounded.DEFAULT}'
    marginRight: '{spacing.3}'
    background: 'one of {colors.signal-blocked} | {colors.signal-qa} | {colors.signal-budget} | {colors.signal-rework} | {colors.signal-infra} | {colors.signal-criterion}'
  status-token:
    typography: '{typography.status-token}'
    color: 'same signal colour as the paired {components.status-chip}'
    width: '3 characters, fixed column'
  record-row:
    grid: '52px 128px 210px 1fr 74px'
    padding: '{spacing.row-padding-y} {spacing.row-padding-x}'
    borderBottom: '{spacing.hairline} solid {colors.line}'
    backgroundHover: '{colors.surface-raised}'
  board-column:
    width: '{spacing.board-column-width}'
    borderRight: '{spacing.hairline} solid {colors.line}'
    header: '{typography.column-head}'
    background: 'transparent'
  board-card:
    background: '{colors.surface}'
    border: '{spacing.hairline} solid {colors.line}'
    radius: '{rounded.DEFAULT}'
    padding: '{spacing.5}'
    borderHover: '{colors.line-strong}'
    title: '{typography.row-title}'
    step: '{typography.meta}'
    statusChip: '{components.status-chip}'
  alert-banner:
    background: '{colors.surface-raised}'
    borderLeft: '2px solid <signal colour of the alert type>'
    padding: '{spacing.8} {spacing.9}'
    typography: '{typography.row-body}'
  detail-header:
    padding: '{spacing.9} {spacing.detail-padding-x} {spacing.8}'
    borderBottom: '{spacing.hairline} solid {colors.line}'
    title: '{typography.detail-title}'
    meta: '{typography.meta}'
    metaColor: '{colors.text-tertiary}'
  section-head:
    typography: '{typography.section-head}'
    color: '{colors.text-tertiary}'
    borderBottom: '{spacing.hairline} solid {colors.line}'
    marginBottom: '{spacing.6}'
  question-block:
    background: '{colors.surface-raised}'
    borderLeft: '2px solid {colors.signal-blocked}'
    padding: '{spacing.8} {spacing.9}'
    typography: '{typography.question}'
    attribution: '{typography.eyebrow}'
  criterion-block:
    border: '{spacing.hairline} solid {colors.line}'
    headerBackground: '{colors.surface-rail}'
    headerTypography: '{typography.status-token}'
    grid: '58px 1fr'
    termTypography: '{typography.micro}'
    valueTypography: '{typography.row-body}'
    testidColor: '{colors.accent}'
  activity-timeline:
    grid: '62px 12px 1fr'
    timestampColor: '{colors.text-tertiary}'
    glyphColor: '{colors.text-tertiary}'
    glyphColorCurrent: 'signal colour of the current state'
    rowColor: '{colors.text-secondary}'
    rowColorCurrent: '{colors.text}'
  command-block:
    background: '{colors.surface-inset}'
    border: '{spacing.hairline} solid {colors.line-strong}'
    barTypography: '{typography.eyebrow}'
    codeTypography: '{typography.command}'
    flagColor: '{colors.accent}'
    prefixColor: '{colors.text-tertiary}'
  button:
    background: 'transparent'
    border: '{spacing.hairline} solid {colors.line-strong}'
    radius: '{rounded.DEFAULT}'
    color: '{colors.text-secondary}'
    typography: '{typography.control}'
    padding: '{spacing.2} {spacing.5}'
    colorHover: '{colors.text}'
    borderHover: '{colors.text-tertiary}'
  button-primary:
    border: '{spacing.hairline} solid {colors.accent}'
    color: '{colors.accent}'
    background: 'transparent'
    radius: '{rounded.DEFAULT}'
    typography: '{typography.control}'
  button-destructive:
    border: '{spacing.hairline} solid {colors.signal-infra}'
    color: '{colors.signal-infra}'
    background: 'transparent'
    radius: '{rounded.DEFAULT}'
    typography: '{typography.control}'
  kv-table:
    rowBorderBottom: '{spacing.hairline} solid {colors.line}'
    keyColor: '{colors.text-tertiary}'
    keyWidth: '44%'
    valueColor: '{colors.text}'
    valueAlign: 'right'
    typography: '{typography.row-body}'
  artifact-tree:
    indentStep: '{spacing.7}'
    guideColor: '{colors.line}'
    nodeTypography: '{typography.row-body}'
    nodeColor: '{colors.text-secondary}'
    nodeColorChanged: '{colors.text}'
    timestampColor: '{colors.text-tertiary}'
    changedMarker: 'a single {colors.accent} chip at {spacing.chip-size}, left of the filename'
  empty-state:
    padding: '{spacing.32} {spacing.12}'
    headline: '{typography.surface-title}'
    body: '{typography.meta}'
    bodyColor: '{colors.text-tertiary}'
    bodyLineHeight: '1.9'
  focus-ring:
    outline: '1px solid {colors.accent}'
    outlineOffset: '1px'
---

## Brand & Style

AI Orchestrator is a readout, not a dashboard. One person watches an autonomous pipeline that runs for hours without her, and comes back cold. The surface has exactly one job: let her reconstruct, in seconds, where everything is and what stopped. Every design decision is downstream of that.

The register is **instrumental and severe** — the reference space is `kubectl get`, Temporal's event history, an oscilloscope readout. Not consumer web, not a "productivity app." Everything is monospace on a fixed column grid, because a fixed grid is scannable top-to-bottom the way an event log is, and monospace makes ids, paths, hashes, commands, and timestamps align without effort. The product is largely made of those things.

The single strongest rule: **colour is signal and nothing else.** A row or a card carries exactly one saturated pixel — a 7px chip — and the rest of the surface is four tones of near-black plus three weights of grey text. Status is encoded three times over, in descending reliance on colour: a fixed three-letter token in a fixed leftmost column, that token's position in the column, and the chip beside it. Read on a bad monitor, in sunlight, or by someone colour-blind, the token still carries the state on its own.

Density is deliberately two-speed: **dense list, spacious detail.** The board and the notification list are compact and scannable, because triage is a scanning job. Opening an item breaks the grid on purpose — full width, larger type, air between sections — because reloading cold context is a reading job, and cramming it is how the async premise dies.

Dark-first. There is no light theme in M1.

## Colors

**Ground — four tonal planes.** `{colors.bg}` `#0B0D0E` is the page; `{colors.surface}` `#111416` is a panel; `{colors.surface-raised}` `#171B1D` is a hovered row, a quoted question, or a raised block; `{colors.surface-rail}` `#0E1113` is the navigation rail and table header bands. `{colors.surface-inset}` `#08090A` is darker than the page and is reserved for the terminal command block — the one element that is deliberately *not* part of the app, but a quotation from the operator's shell. `{colors.surface-input}` `#0A0C0D` is the inside of a text field. The planes are near-black and very slightly green-cool; they must never be warmed or tinted per-surface.

**Hairlines.** `{colors.line}` `#21272A` is the default 1px rule — it draws every row boundary, section head underline, and panel edge. `{colors.line-strong}` `#2C3438` frames a whole screen, a button, or a command block. Structure comes from these two values, not from shadow and not from fill.

**Text — three weights of legibility.** `{colors.text}` `#DDE3E5` is primary content: titles, criteria bodies, the question, the command. `{colors.text-secondary}` `#8B979B` is supporting content: project names, timeline rows, inactive nav. `{colors.text-tertiary}` `#5C686C` is meta: timestamps, units, ages, column heads, notes. Nothing below tertiary exists; if content needs to be dimmer than tertiary, it should not be on the surface.

**Signal — six colours, one per escalation type.** These map one-to-one onto the six PRD notification types and are used *only* on a `{components.status-chip}` and the three-letter `{components.status-token}` that shares its colour:

| Token | Hex | Three-letter token | Means |
|---|---|---|---|
| `{colors.signal-blocked}` | `#E4B33C` | `BLK` | Blocked story — an agent asked a question and parked |
| `{colors.signal-qa}` | `#4FB477` | `QA` | Epic ready for QA / G3 |
| `{colors.signal-budget}` | `#D9663D` | `BGT` | Budget breach |
| `{colors.signal-rework}` | `#C25C86` | `RWK` | Rework cap reached |
| `{colors.signal-infra}` | `#E05252` | `INF` | Infrastructure failure |
| `{colors.signal-criterion}` | `#6C8CD5` | `CRT` | Unmatched criterion (blocks G2) |

`{colors.signal-blocked}` has one additional, tightly scoped use: an age that has crossed the staleness threshold turns amber, because "this has been waiting too long" is the same alarm as "this is blocked." No other signal colour extends beyond its chip and token.

**Accent.** `{colors.accent}` `#7FD4C1` is interaction and only interaction: links, the focus ring, the active-nav inset marker, the primary button outline, the copy-command affordance, and inline test-id / identifier literals inside prose. Pale teal is chosen precisely because it sits outside the six signal hues — it can never be mistaken for a status.

**Not used for:** backgrounds, washes, tints, gradients, hover fills, section banding, per-project colour-coding, or "brand moments." If a colour is filling an area larger than 7px square, something has gone wrong.

## Typography

One family: `{typography.font-family-mono}`, the platform monospace stack. There is no second family, no serif, no display face, and **no weight above 400** — emphasis is produced by colour weight (`{colors.text}` against `{colors.text-secondary}`) and by letter-spacing, never by bold.

The ramp is narrow on purpose — six sizes between 10px and 19px — because a wide type scale implies a hierarchy of importance that this product does not have. Everything on a detail page matters; the differences are of *kind*, not rank.

| Role | Size / spacing | Where |
|---|---|---|
| `{typography.detail-title}` | 19 / 1.3 / -0.01em | The one title on a detail, gate, or task page |
| `{typography.question}` | 14 / 1.7 | The agent's parked question — the largest body text in the product |
| `{typography.command}` | 13 / 1.7 | The `claude --resume` block |
| `{typography.body}` | 13 / 1.45 | Global default |
| `{typography.surface-title}` | 13 / 0.18em uppercase | Surface name in the top bar; empty-state headline |
| `{typography.row-title}` | 12.5 / 1.4 | Card and row titles |
| `{typography.row-body}` | 12.5 / 1.55 | Criteria values, timeline rows, tree nodes |
| `{typography.meta}` | 11.5 / 1.45 | Project, repository, hint, age, counts |
| `{typography.micro}` | 11 / 1.6 | Footnotes, breadcrumbs, FR references |
| `{typography.status-token}` | 11 / 0.10em | The three-letter status token |
| `{typography.control}` | 11 / 0.12em uppercase | Buttons and filters |
| `{typography.eyebrow}` | 10.5 / 0.16em uppercase | Block attributions ("Agent · claude-opus-4 · …") |
| `{typography.column-head}` | 10 / 0.18em uppercase | Table column heads, board column heads, nav groups |
| `{typography.section-head}` | 10 / 0.22em uppercase | Section headings inside a detail page |

**Uppercase + letter-spacing is the labelling device.** Anything uppercase is a label, never content. The tracking widens as the type gets smaller (0.10em → 0.22em), which is what keeps a 10px all-caps section head legible and stops it from reading as a word.

**Truncation over wrapping in dense contexts.** Row cells (project, repository, title, hint) are single-line with ellipsis; the fixed grid is worth more than the tail of a string. Detail contexts never truncate.

## Layout & Spacing

**The shell.** A fixed `{spacing.rail-width}` 172px navigation rail on the left, `{colors.surface-rail}` ground, hairline right border; the main column takes the rest. The rail never collapses in M1 — this is a desktop product for one operator at a desk. Page content is capped at `{spacing.page-max}` 1180px; a detail body is capped at `{spacing.detail-max}` 940px, because a 19px/1.7 question set at 1180px is unreadable.

**The record grid.** Every list row is the same five-column grid — `52px 128px 210px 1fr 74px` (type · project · repository · what · age) — with `{spacing.row-padding-y}` / `{spacing.row-padding-x}` padding and a `{colors.line}` bottom hairline. The columns are fixed across the whole product so that the eye learns one horizontal position per field and never re-scans. This is the single most important layout rule: **the grid is a contract, not a suggestion.** A row that needs a sixth field does not get one.

**The board.** Five stage columns — Spec, Plan/G2, Build, Review/G3, Merged — at `{spacing.board-column-width}` 232px each, separated by hairlines, in a horizontally scrolling container. [ASSUMPTION] The 232px column width and horizontal-scroll behaviour are inferred; the memlog settles that columns are pipeline stages and that status is a chip, but not the column metrics. Columns are equal width and never resize to content: an empty column must stay visibly present, because under FR-47 serialization most columns are empty most of the time and a collapsing column would read as a rendering failure rather than as truth.

**Spacing scale.** A 2px-based scale with odd intermediate values (`5`=10px, `7`=14px, `9`=18px) inherited directly from the direction file. Dense contexts use `1`–`6` (2–12px); detail contexts use `8`–`16` (16–32px); the gap between detail sections is `{spacing.section-gap}` 34px, which is the largest vertical interval in the product and the thing that makes a detail page feel unhurried against the list's compression.

**Breakpoints.** None in M1. [ASSUMPTION] The memlog does not settle responsive behaviour; the product is a single-operator desktop surface and the fixed record grid does not survive a narrow viewport. Below roughly 1024px the app should scroll horizontally rather than reflow — a broken-looking wide layout is more honest than a reflowed one that silently drops columns.

## Elevation & Depth

**There are no shadows.** Not on cards, not on menus, not on hover, not on the active row. Depth is produced by two devices only:

1. **Tonal layering** — the four ground planes, in fixed order: `{colors.surface-inset}` < `{colors.bg}` < `{colors.surface-rail}` < `{colors.surface}` < `{colors.surface-raised}`. A raised element is *lighter*, and never by more than one step.
2. **Hairlines** — `{colors.line}` for internal division, `{colors.line-strong}` for the outer edge of a self-contained thing.

The one `box-shadow` in the entire system is `inset 2px 0 0 {colors.accent}` on the active navigation item — an inset marker, structurally a border, not elevation. Overlays, if ever needed, are full-plane panels with a `{colors.line-strong}` frame, not floating cards. A drop shadow anywhere in this product is a bug.

## Shapes

**Every corner is square.** `{rounded.DEFAULT}` is `0` and so is every step of the scale. Buttons, inputs, cards, panels, chips, filter segments, and the command block are all sharp-cornered. The `full` token exists in the scale only so that a component author who reaches for a pill discovers there is nothing to reach for.

The `{components.status-chip}` is a **7px square**, not a dot. This is deliberate and load-bearing: a circle reads as a bullet or an avatar; a square reads as an indicator lamp. It sits `{spacing.3}` 6px to the left of its three-letter token, sharing its colour, and it is the only filled shape in the row.

Rounded corners, pill badges, and circular indicators are the visual grammar of consumer software and of tools built around people. This product is built around a machine that is running unattended. Square is the whole point.

## Components

**App rail** — `{components.app-rail}`. Fixed 172px, `{colors.surface-rail}`. Brand block at top with a one-line subtitle ("M1 · single operator"). Items are single-line, `{typography.body}`, with an optional right-aligned count in `{colors.text-tertiary}`. Active item: `{colors.text}` on `{colors.surface-raised}` with the `{colors.accent}` inset marker. Group labels in `{typography.column-head}`.

**Surface bar** — `{components.surface-bar}`. Every surface opens with one: surface name in `{typography.surface-title}`, a count in `{colors.text-tertiary}`, a spacer, then filters and search right-aligned. Hairline bottom border. No page-level "hero," ever.

**Filter group** — `{components.filter-group}`. Segmented control: one hairline box, segments divided by internal hairlines, no radius, no gaps. Inactive segments are `{colors.text-tertiary}`; the active segment is `{colors.text}` on `{colors.surface-raised}`. On typed filters the segment label is the three-letter token itself (`ALL · BLK · QA · BGT · RWK · INF · CRT`), so the filter row teaches the vocabulary used in the leftmost column.

**Status chip + token** — `{components.status-chip}` and `{components.status-token}`. Always paired, always in that order, always in the leftmost fixed column of a row or the top-left of a card. Chip is 7px square, filled with the signal colour; the token is three characters in the same colour. Never one without the other.

**Record row** — `{components.record-row}`. The five-column grid described in Layout & Spacing. The whole row is one link target. Hover lifts the ground to `{colors.surface-raised}` — no border change, no transform, no shadow. Two lines in the "what" column: title in `{colors.text}`, one-line hint in `{colors.text-tertiary}` carrying *why this is here* (the question asked, the budget figure, the failing spec).

**Board column / board card** — `{components.board-column}`, `{components.board-card}`. [ASSUMPTION] The card is an extension of the record-row language into the board, which the direction file does not itself render. A card is a `{colors.surface}` rectangle with a `{colors.line}` border and `{spacing.5}` padding, carrying, in fixed order: chip + token, title, project · repository in `{typography.meta}`, current step ("epic 1, story 3"), and age. Hover changes the border to `{colors.line-strong}` and nothing else. Cards do not carry progress bars, percentages, or thumbnails.

**Alert banner** — `{components.alert-banner}`. Appears at the top of a feature detail when something is blocked. `{colors.surface-raised}` ground with a 2px left border in the signal colour of the alert type. This left border is the *only* place a signal colour extends beyond 7px, and it is a rule, not a fill.

**Detail header** — `{components.detail-header}`. Breadcrumb in `{typography.micro}` with an `{colors.accent}` back link, then the chip + token + full type name, then the title in `{typography.detail-title}`, then a single dense meta line: project · repository · epic · branch · worktree · run id · workflow version, with values in `{colors.text-secondary}` against `{colors.text-tertiary}` labels. That meta line is the cold-reload anchor; it is never truncated and never collapsed behind a disclosure.

**Section head** — `{components.section-head}`. `{typography.section-head}` in `{colors.text-tertiary}` with a hairline underneath. Sections are separated by `{spacing.section-gap}`.

**Question block** — `{components.question-block}`. The agent's parked question, set at `{typography.question}` — the largest body text in the product — on `{colors.surface-raised}` with a 2px `{colors.signal-blocked}` left rule. An `{typography.eyebrow}` attribution line above it names the agent, model, and timestamp.

**Criterion block** — `{components.criterion-block}`. One acceptance criterion: a header band on `{colors.surface-rail}` carrying `AC-n`, the spec file and line with its pass/fail word, and the route right-aligned; then a Given / When / Then definition grid. Test-ids and routes inside the values are rendered in `{colors.accent}`. Pass/fail is stated as the words `green` / `red` in the header — never as a coloured background, never as an icon.

**Activity timeline** — `{components.activity-timeline}`. Three columns: right-aligned timestamp, a single glyph, the event text. Past rows are `{colors.text-secondary}` with a `·` glyph; the current row is `{colors.text}` with a `■` glyph in the signal colour of the current state. No connecting line, no icons, no avatars.

**Command block** — `{components.command-block}`. The darkest element in the product, `{colors.surface-inset}` inside a `{colors.line-strong}` frame. An `{typography.eyebrow}` bar names it and carries the Copy button (`{components.button-primary}`); the body is the literal command at `{typography.command}`, with shell keywords in `{colors.text-tertiary}` and the harness invocation and flags in `{colors.accent}`. It is horizontally scrollable and never wrapped in a way that would break a paste.

**Buttons** — `{components.button}`, `{components.button-primary}`, `{components.button-destructive}`. Outline only: transparent ground, hairline border, uppercase `{typography.control}` label. There is no filled button anywhere. Primary is distinguished by an `{colors.accent}` border and label; destructive by `{colors.signal-infra}`. Buttons sit in a row above a hairline at the end of a section.

**Key/value table** — `{components.kv-table}`. Label left in `{colors.text-tertiary}`, value right-aligned in `{colors.text}`, hairline between rows. Used for structured output, cost, and gate results. Values that are ratios are printed as ratios (`$4.18 / $15.00`, `2/2`, `14/14`), never as bars or dials.

**Artifact tree** — `{components.artifact-tree}`. An indented file list, `{spacing.7}` 14px per level, guide rules in `{colors.line}`. Each node: filename in `{typography.row-body}`, right-aligned modified timestamp in `{colors.text-tertiary}`. A file changed since the operator's last view is promoted from `{colors.text-secondary}` to `{colors.text}` and carries a single `{colors.accent}` 7px chip to its left. [ASSUMPTION] The changed-since-last-viewed chip is inferred: the memlog settles that last-viewed timestamps are tracked from day one and that the diff-since-last-viewed *tab* is deferred, but does not specify how "changed" is signalled in the meantime. Using the accent rather than a signal colour keeps "new to you" distinct from "wrong."

**Empty state** — `{components.empty-state}`. Centred, generous vertical padding, uppercase `{typography.surface-title}` headline, then `{typography.meta}` body at 1.9 line-height listing *what is happening instead*. An empty state in this product is a readout too: "Nothing needs you" is followed by the three runs that are in flight and when the next return is expected. Never an illustration, never a call-to-action button as the only content.

**Focus ring** — `{components.focus-ring}`. A 1px `{colors.accent}` outline at 1px offset on every focusable element. Never removed, never replaced by a background change.

## Do's and Don'ts

| Do | Don't |
|---|---|
| Keep every glyph in `{typography.font-family-mono}` | Introduce a second family, a serif, or a display face for "warmth" |
| Encode status three times: token, column position, chip | Rely on colour alone to carry a state |
| Use a signal colour on a 7px `{components.status-chip}` and its three-letter token | Fill a row, card, cell, or banner background with a signal colour — no washes, no tints, no coloured stripes wider than a 2px rule |
| Build depth from four ground planes and two hairline weights | Add a drop shadow, a glow, a gradient, or a blur anywhere |
| Keep every corner at `{rounded.DEFAULT}` (0) | Round anything — no pill badges, no circular indicators, no soft consumer-app cards |
| Let the fixed five-column record grid govern every list | Add a sixth column, resize columns to content, or let one surface use a different grid |
| Draw emphasis with `{colors.text}` against `{colors.text-secondary}` | Use font-weight above 400 for emphasis |
| Say the state in words: `green`, `red`, `unvalidated`, `skipped`, `2/2` | Use a tick, a cross, an emoji, a traffic light, a progress bar, a gauge, or a percentage ring |
| Write empty states as readouts of what is running instead | Ship a decorative illustration, spot art, mascot, or "all caught up" graphic |
| Attribute agent output as `Agent · <model> · <timestamp>` in `{typography.eyebrow}` | Give an agent an avatar, a face, a name-circle, a presence dot, or a typing indicator — the pipeline is machinery, and dressing it as a colleague misrepresents what the operator is reviewing |
| Show pending work as a plain count in `{colors.text-tertiary}` next to a nav item | Use a red pill notification badge, an unread dot, or any social-inbox affordance implying someone is waiting on a reply |
| Reserve `{colors.accent}` for interaction and identifier literals | Use `{colors.accent}` as a seventh status colour, or as a brand fill |
| Print costs, budgets, and counts as literal ratios | Visualise a budget as a bar, ring, or dial |
| Let an empty board column stay visibly empty | Collapse or hide empty stage columns, or imply parallelism the M1 engine cannot deliver (FR-47) |
| Keep the command block a verbatim, copyable, unwrapped quotation of the shell | Prettify, syntax-theme, soft-wrap, or paraphrase the `claude --resume` command |
