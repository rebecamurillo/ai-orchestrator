# templates/ — the shipped workflow families

Every `*.yaml` directly in this directory is seeded into the instance at start-up as the next
version of its name (`seed_shipped`, by content hash); `drafts/` is never seeded. Two families
ship, told apart by the first segment of the name, by the fixed header block under each file's
`description:` (`# family … # called by … # sibling …`), and by the family word the
description opens with. `tests/unit/application/templates/test_shipped_families.py` checks
that this table names every shipped file and that every staged file carries the header — names
and headers only, never steps, ordering or counts (hard rule 6).

| file | family | role | calls | on the menu | sibling in the other family |
| --- | --- | --- | --- | --- | --- |
| `staged-initiative-hub.yaml` | staged | root, hub scope | `staged-hub-epic` | yes | `initiative-hub` |
| `staged-hub-epic.yaml` | staged | epic, hub | `staged-hub-story` | — | `initiative-hub-epic` |
| `staged-hub-story.yaml` | staged | story, hub | — | — | `initiative-hub-story` |
| `staged-initiative-repo.yaml` | staged | root, single repository | `staged-epic` | yes | — (the auto family has no single-repository initiative root) |
| `staged-epic.yaml` | staged | epic, single repository | `staged-story` | — | `epic` |
| `staged-story.yaml` | staged | story, single repository | — | — | `story` |
| `initiative-hub.yaml` | auto | root, hub scope | `initiative-hub-epic` | yes | `staged-initiative-hub` |
| `initiative-hub-epic.yaml` | auto | epic, hub | `initiative-hub-story` | — | `staged-hub-epic` |
| `initiative-hub-story.yaml` | auto | story, hub | — | — | `staged-hub-story` |
| `epic.yaml` | auto | root, one epic on its own branch (harness readiness fixture) | `story` | no | `staged-epic` |
| `story.yaml` | auto | story, single repository | — | — | `staged-story` |
| `repo-init.yaml` | — | root, bootstrap the BMAD method into a repository | — | yes | — |
| `agent-smoke.yaml` | — | root, one-dispatch check of an install | — | yes | — |

**auto** — one `bmad-build-auto` session per story (plan, implement, review in one context).
Maintained, not evolved: fixes only. **staged** — three sessions per story, `plan` →
`implement` → deterministic `verify` → `review`, each on its own model (`plan_model`, the
Run's `model`, `review_model`) and its own limit, each routed on a marker under
`{spec_folder}/stories/.auto/`; the method lives in `ia-agents-skills/staged-*`. New workflow
behaviour lands in the staged family.

Editing one family: read the sibling's `# sibling … differs in` line first; a change to a
shared row (the git rows, the epic tail) usually belongs in both. The menu is
`ROOT_TEMPLATES` in the instance `.env`.
