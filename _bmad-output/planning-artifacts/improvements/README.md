---
title: Improvements backlog
status: living
created: 2026-09-08
purpose: raw candidate changes, written as they are found, to be fed into the next version-planning cycle
---

# Improvements

Candidate changes found while building or operating the orchestrator, recorded at the moment
they are found so the next planning cycle starts from evidence rather than memory. Nothing
here is committed work: a note is a proposal with its reasoning attached, not a decision.

## What belongs here

A note belongs here when all three hold:

- it changes what the product does or what the DSL accepts — not how a module is written
  (that is a code review comment) and not a defect in shipped behaviour (that is a bug);
- it is out of scope for the epic that surfaced it, so it would otherwise be lost;
- it can be stated as a problem with evidence, so a later reader does not have to re-derive it.

Anything that only concerns the current sprint goes through `bmad-correct-course` instead.

## Shape of a note

One file per candidate, named `IMP-{nnn}-{slug}.md`, numbered in discovery order. Frontmatter:

```yaml
---
id: IMP-001
title: <one line>
status: candidate | accepted | rejected | shipped
raised: YYYY-MM-DD
raised-by: <who, and what they were doing>
area: template-dsl | web-client | backend-api | operations | docs
prd-deltas: <FR/NFR ids this would change, or none>
spine-deltas: <AD ids this would change, or none>
effort: S | M | L
---
```

Body sections, in this order: **Problem** (what the operator cannot do today), **Evidence**
(file and line, so the claim is checkable), **Options** (each with what it costs), **Recommendation**
(one option, with why the others lose), **Scope of change** (the files a build would touch),
**Open questions** (what a planning pass still has to decide).

## Lifecycle

`candidate` → picked up by a planning cycle → `accepted` (folded into a PRD update via
`bmad-prd`, or distilled straight to a spec via `bmad-spec` when it is small and self-contained)
→ `shipped` once the epic that carries it lands. A note that a planning cycle turns down is
marked `rejected` with the reason, and stays: the reasoning is worth more than the file is
worth deleting.

## Index

| Id | Title | Status | Area | Effort |
| --- | --- | --- | --- | --- |
| [IMP-001](IMP-001-single-story-run.md) | Start a Run for one Story | candidate | template-dsl | M |
| [IMP-002](IMP-002-issue-sized-change.md) | Run an issue-sized change through the BMAD plan gate | candidate | template-dsl | S–M |
