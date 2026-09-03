
  You are driving Epic 1 of ai-orchestrator to completion, one story at a time, under my supervision.
  Project root: /Users/rebecam/Documents/projects/OptimAI/ai-orchestrator.
  Epic folder: _bmad-output/planning-artifacts/mvp/epics/epic-01-foundation.
  Start at story <START_ID> and work forward in numeric order: 1-1, 1-2, 1-3, 1-4, 1-5, 1-6, 1-7.

  How to run a story. For each story, in order:
  1. Read the entry with that exact id in <epic>/stories.yaml. If the id is absent, HALT and tell me.
  2. Invoke the bmad-build skill with that entry's invoke_dev_with text verbatim, plus spec_folder = 
     _bmad-output/planning-artifacts/mvp/epics/epic-01-foundation and story_id = <the id>. Follow the rendered workflow exactly —
     do not shortcut step-02 planning, step-04 review, or the spec CHECKPOINT. Never run a workflow source file directly.
  3. Read only that story's brief. Do not read the other briefs — they are other stories' contracts and reading them causes scope
     bleed.
  4. When the story reaches status: done and sprint-status shows review, stop and give me the end-of-story report. Do not start
     the next story until I say go.

  Binding authority when documents disagree: ARCHITECTURE-SPINE.md (AD-1..AD-20) → the story's brief → SPEC.md capability lines →
  existing code. The brief is the story's complete requirements. Story scope is what its In list names; anything in Out belongs
  to a later story even if it looks trivial to add now.

  Standing repository rules. Never move, rename, or wholesale replace an existing file — README.md and .gitignore are edited in
  place keeping every existing section (the README's "Setting up the BMAD method on a new machine" section is the only record of
  that procedure); GUIDELINES.md is reference documentation, not to be touched or folded into AGENTS.md. Never commit a real
  secret or .env. Tests first (AD-18). Never auto-push, never open a PR — local commits only. uv 0.12.9 is at
  /opt/homebrew/bin/uv; if a BMad script fails on uv, report the exact output and HALT rather than falling back silently.

  When to interrupt me — ask as a numbered list with your recommendation for each, then wait:
  - a brief instruction conflicts with the spine, with SPEC.md, or with code from an earlier story
  - a brief is ambiguous in a way that changes the artifact — two readings produce different files, schemas, or public interfaces
  - following it literally would delete, overwrite, or relocate an existing file
  - a pinned Stack version is unavailable, yanked, or incompatible with another pin
  - a gate (make lint/test/e2e-api/e2e-ui) cannot go green without weakening the gate itself — loosening a rule, lowering
    coverage, adding an ignore, skipping a test, widening an import-linter contract. Never weaken a gate to get green.
  - the work needs a dependency, top-level directory, or env var the brief does not name
  - bmad-build's review produces an intent_gap, or the review loop iterates more than twice
  - anything needs network credentials, an external account, or a paid service

  Do not interrupt for naming inside a module, test-case choice, formatting, refactors within the story's own new files, or
  anything the brief already answers — decide those and list them under Judgment calls.

  End-of-story report — facts and mechanisms only, no congratulation:
  1. What was built — artifacts by path, grouped by concern, what each does
  2. Acceptance criteria — every AC from the brief, met / not met / not verifiable, each with the evidence that settles it. Never
     mark an AC met on inspection alone when a command could settle it. 
  3. Gate output — the actual tail of make lint, make test, and any e2e target touched. Real output. Never report green without
     it.
  4. Judgment calls — decided without asking, and why
  5. Deviations — with reason and authority (spine AD-n, earlier code, a broken pin)
  6. Carried forward — interfaces, ports, fakes, conventions, config keys the next story inherits
  7. State — commit hash, spec file path, sprint-status line
  
  Then stop, one line on which story is next, and wait for my go-ahead.

  Before you start, confirm in under ten lines: which story you're starting at, the current epic-1 development_status from
  sprint-status.yaml, and whether the tree is clean.