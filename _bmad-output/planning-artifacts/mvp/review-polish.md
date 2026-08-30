# Polish review — `prd.md` and `addendum.md`

Lenses: `structure` then `prose` (bmad-review, editorial lenses). Reader type: humans (operator-builder, architect, story writer); style baseline: Microsoft Writing Style Guide (American English, serial comma, sentence-case headings). Content is sacrosanct — every row below changes organization or wording only; nothing adds, removes, or re-scopes a requirement. Fixes are quoted as `original` → `replacement` so they can be applied by search-and-replace. Rows marked *Consider:* are judgement calls for the author.

**Read:** these documents exist to let one operator-builder, `bmad-architecture`, and `bmad-create-epics-and-stories` build the one-week MVP from an unambiguous contract. **Structure model:** Strategic/Context (pyramid) for the PRD; Reference/Database for the addendum.

**Word metrics** (exact, `word_metrics.py`): `prd.md` 7,169 words; `addendum.md` 1,478 words.

**Counts:** structure 21 · prose 27 · total 48.

---

## Structure (21)

1. **[structure]** prd.md §10 Cross-cutting NFRs — NFR-8 is listed before NFR-7; numbering out of order in a numbered list. — *Fix:* MOVE the `- **NFR-7 Build size:** …` bullet above the `- **NFR-8 Voice:** …` bullet (swap the last two bullets). Word impact: 0.

2. **[structure]** addendum.md headings — sections run A, B, C, D, E, F, **H**, **G**; §G (Day-1 verification queue) sits after §H. — *Fix:* MOVE §G above §H, or re-letter `## H. Corrections surfaced at Finalize (for bmad-architecture)` → `## G. Corrections surfaced at Finalize (for bmad-architecture)` and `## G. Day-1 verification queue` → `## H. Day-1 verification queue`. Word impact: 0.

3. **[structure]** prd.md §9 Assumptions index — entries are not in document order (FR-21 precedes FR-18; the two §4.4 description-level assumptions come last, after §4.9), so a reader cannot walk the index against §4. — *Fix:* MOVE to document order: `§4.1 FR-1`, `§4.2 FR-4`, `§4.4` (Spec folder), `§4.4` (one Repository per Run), `§4.4 FR-9`, `§4.4 FR-10`, `§4.6 FR-18`, `§4.6 FR-21`, `§4.7 FR-22`, `§4.9 FR-27`. Word impact: 0.

4. **[structure]** prd.md §3 Glossary "Question" vs §4.5 FR-16 consequence 3 vs addendum.md §D "Story-file evaluation" — three definitions of what is shown as the Question, and they differ: Glossary says `the \`Blocking condition\` line(s) of the Story file's \`## Auto Run Result\``; FR-16 says `the whole \`## Auto Run Result\` section (status, blocking condition, and any listed questions and evidence) shown as the Question`; addendum §D says `the \`## Auto Run Result\` block yields \`Status:\` and \`Blocking condition:\` lines shown as the Question`. An engineer building FR-16 from the Glossary or the addendum ships less than FR-16 specifies. — *Fix:* QUESTION — confirm FR-16 is the intended contract, then MERGE the other two to it: Glossary → `- **Question** — the text shown to the Operator for a \`blocked\` Story: the Story file's whole \`## Auto Run Result\` section (FR-16), attributed to Harness, model, and time.`; addendum §D → `…parse YAML frontmatter; route on \`status\`; the whole \`## Auto Run Result\` block is shown as the Question (FR-16).` Word impact: −6.

5. **[structure]** prd.md §3 Glossary "Needs you" vs §4.6 description — the list of stops is duplicated and has drifted: Glossary lists `agent \`blocked\`, Checkpoint, verify failed twice, budget halt, Step timeout.`; §4.6 adds `push rejected, and the configuration failures listed in FR-16`. — *Fix:* MERGE to one source of truth; Glossary entry → `- **Needs you** — the Run Status column and rail count grouping every Run whose next action is the Operator's (the stops listed in §4.6).` Word impact: −8.

6. **[structure]** prd.md §3 Glossary "Answer" vs §4.6 FR-18 (intro and consequence 2) — the archive-and-redispatch mechanism is stated three times in near-identical words. The Glossary should define, FR-18 should specify. — *Fix:* CONDENSE Glossary → `- **Answer** — Operator text resolving a \`blocked\` Story; the mechanism (archive the blocked Story file, re-dispatch with the Answer as planning context) is FR-18.` Word impact: −22.

7. **[structure]** prd.md §4.4 FR-13 consequence 1 vs addendum.md §D "Repository lock" — the rationale `because a parked workflow still occupies its queue partition and because two Runs must never share a Repository's worktrees.` mixes the DBOS mechanism (which the addendum owns, per its own preamble) into the PRD, and §D repeats it. — *Fix:* CONDENSE the PRD clause → `because two Runs must never share a Repository's worktrees (mechanism: addendum §D).` Word impact: −6.

8. **[structure]** prd.md §4.7 description vs §10 NFR-6 — `Colour is signal only: green running, amber needs you, red failed; nothing else is coloured.` restates NFR-6's colour rule. — *Fix:* CONDENSE → `Colour rules: NFR-6.` Word impact: −12.

9. **[structure]** prd.md §4.5 FR-14 consequence 5, §4.9 FR-26 consequence 1, §10 NFR-3 — "no direct provider key" is stated three times. NFR-3 is the cross-cutting home; FR-14 owns the credential rule. — *Fix:* CONDENSE FR-26 consequence 1 → `- A Harness process with the Gateway unreachable fails its Step with \`error\` (credential rule: FR-14, NFR-3).` Word impact: −6.

10. **[structure]** prd.md §11 Constraints "Privacy" vs §4.2 FR-2 consequence 4 — same switch stated twice; unlike the Safety and Cost bullets, Privacy does not cite its FR. — *Fix:* `enabling content logging is a per-Project switch that puts source code in Langfuse.` → `enabling content logging is a per-Project switch (\`log_prompt_content\`, FR-2) that puts source code in Langfuse.` Word impact: +2.

11. **[structure]** prd.md §6.1 "Slips first" vs addendum.md §F "Slips first" — the same ordered list appears in both files with different names for the same items (`the \`local\` adapter` / `OpenCode adapter`; `in-browser Template editing` / `Templates editing`; `Runs history pagination` / `Runs pagination`). — *Fix:* MERGE — addendum §F: `Slips first: OpenCode adapter, Templates editing, Runs pagination, cancel rollback.` → `Slips first: as PRD §6.1.` Word impact: −6.

12. **[structure]** addendum.md §H "Worktree retention" and "PR link" — both items restate PRD FR-9 consequence 5 and FR-11 consequence 4 verbatim and add no correction for the architect; every other §H item adds a mechanism or a delta. — *Fix:* CUT both bullets, or CONDENSE to one pointer bullet: `- **Worktree retention, PR link:** as PRD FR-9 and FR-11; no change to architecture-v1.` Word impact: −20.

13. **[structure]** prd.md §6.1 In scope, second paragraph — a 201-word paragraph carries three bolded topics (`**Definition of done for the MVP.**`, `**Tiers.**`, `**Slips first, in order:**`). — *Fix:* CONDENSE by format only: break into three paragraphs (or three bullets) at each bold lead-in. Word impact: 0.

14. **[structure]** prd.md §6.1 Tiers, MUST list — `FR-26..FR-28, FR-1 without lockout.` puts FR-1 last, out of numeric order with the rest of the list. — *Fix:* MOVE: `MUST: FR-2, FR-3, FR-4 (on save),` → `MUST: FR-1 (without lockout), FR-2, FR-3, FR-4 (on save),` and delete `, FR-1 without lockout` at the end. Word impact: 0.

15. **[structure]** prd.md §4.5 FR-14 consequences — the per-Harness bullets (`For \`claude\``, `For \`codex\``, `For \`local\``) are interrupted by the readiness-check bullet (`Every shipped Harness completes one trivial Story…`). — *Fix:* MOVE that bullet below the `For \`local\`:` bullet so the three adapter bullets are contiguous. Word impact: 0.

16. **[structure]** prd.md §4.4 FR-8 consequence 1 — one 100-word bullet enumerates ten pre-flight checks in running prose; a story writer will mine it for acceptance criteria. — *Fix:* CONDENSE by format: keep the lead `Pre-flight reports:` and turn each check into a nested sub-bullet (origin reachable · base branch exists · Working branch exists/will create · `stories.yaml` parses with N Stories and prefix-free ids · declared Checkpoints (warning) · `SPEC.md` found · epics file found if given · Harness available with a Gateway key · `render_skill.py` and the skill directory present on the Working branch · existing `stories/*.md` listed with statuses). Word impact: 0.

17. **[structure]** prd.md §4.5 FR-16 consequence 3 — four routing rules chained with `→` and periods in one bullet. — *Fix:* CONDENSE by format: one nested sub-bullet per frontmatter status (`done`, `blocked`, `ready-for-dev` with `spec_checkpoint`, any other status / exit ≠ 0 with a `done` file). Word impact: 0.

18. **[structure]** prd.md §4.4 FR-10 consequence 5 (Step timeouts) — the rule applies to every Step type (`shell`, `git.*`, Story steps) but lives under "Story loop"; §6.1 and addendum §H cite it as FR-10. — *Fix:* QUESTION — either leave it (and keep the FR-10 citations) or MOVE it to the §4.4 description as a Run-wide rule and update the two citations. Word impact: 0.

19. **[structure]** prd.md section order §7–§12 — requirements-bearing sections (§10 NFRs, §11 Constraints, §12 Platform) come after the two appendix-like sections (§8 Open questions, §9 Assumptions index), so the build contract's last requirements sit behind its index. — *Fix:* QUESTION — the pyramid order would be §7 Success metrics → NFRs → Constraints → Platform → Open questions → Assumptions index. Renumbering touches four cross-references (`§9` in §0; `Open questions 2 and 4` in §6.1; `PRD §8` in addendum §G; the `§4.x` prefixes in the index are unaffected). Only worth doing before downstream documents cite section numbers. Word impact: 0.

20. **[structure]** addendum.md §E FR lineage — 91 words of `a..b → c..d` mappings in a single paragraph, while §A and §C use tables. — *Fix:* CONDENSE by format: a two-column table (`2026-08-24 PRD` | `this PRD`) with one row per mapping and a final "Dropped for MVP" row. Word impact: 0.

21. **[structure]** prd.md §3 Glossary — PRESERVE the dependency order (Operator → Project → Repository → … → Worktree) rather than alphabetizing; every entry uses only terms defined above it, which serves first-time readers of a contract better than random access. No change.

---

## Prose (27)

22. **[prose]** prd.md §4.4 FR-10 intro — `a Story step (FR-14), a verify Step, a commit Step.` — "commit Step" reads as the Template's `git.commit` Step type; everywhere else (§4.4 description, FR-10 consequence 4, FR-15, FR-19, FR-20, Glossary "Checkpoint") the Step is `commit-guard`. — *Fix:* `a verify Step, a commit Step.` → `a verify Step, a commit-guard Step.`

23. **[prose]** prd.md §10 NFR-8 — the voice example `("appended to …, status reset to draft, story re-dispatched")` describes a mechanism FR-18 does not use (the file is archived, not reset to draft; addendum §D explicitly rejects the reset). As an example of product copy it teaches the wrong mechanism. — *Fix:* `("appended to …, status reset to draft, story re-dispatched")` → `("archived to stories/.answers/…, story re-dispatched")`.

24. **[prose]** prd.md §4.2 FR-2 consequence 2 — `is never returned by any API response after save (masked to its last four characters)` — "never returned" and "masked" contradict on first read. — *Fix:* → `is returned by API responses after save only masked to its last four characters`.

25. **[prose]** prd.md §4.7 FR-23 intro — `an alert banner when the Run needs them or failed` — "them" has no antecedent (the Operator is singular; the subject is "The Operator"). — *Fix:* → `an alert banner when the Run is \`needs-you\` or \`failed\``.

26. **[prose]** prd.md §4.6 FR-20 consequence 1 — `if that is red the Run stays \`needs-you\`` — "red" is colour-as-status, which NFR-2/NFR-6 forbid on screen and which no other consequence uses; FR-9/FR-10 say "non-zero" / "exit ≠ 0". — *Fix:* → `if that exits non-zero the Run stays \`needs-you\``.

27. **[prose]** prd.md §4.4 FR-11 consequence 1 — `Push uses the Project token per command` — "Project token" is not a Glossary term (FR-2, FR-14, NFR-3 say "GitHub token") and "per command" is ambiguous. — *Fix:* → `Push supplies the Project's GitHub token to each git command individually`. *Consider:* confirm "per command" means per-invocation injection rather than an exported variable; the second half of the bullet already says it never appears in an agent's environment.

28. **[prose]** prd.md §9 Assumptions index, FR-21 entry vs §4.6 FR-21 inline tag — index says `resume-by-terminal detection is by polling the Story file in the Worktree`; inline tag says `file-change detection by polling the Worktree`; the consequence itself polls both the Story file and `git status`. — *Fix:* align the index to the inline tag: `- §4.6 FR-21 — resume-by-terminal detection is by polling the Worktree (Story file and \`git status\`).` and the inline tag → `\`[ASSUMPTION: resume-by-terminal detection by polling the Worktree]\``.

29. **[prose]** prd.md §9 Assumptions index, FR-27 entry vs §4.9 FR-27 inline tag — index adds `session id is the guaranteed correlation`, which the inline tag `[ASSUMPTION: span parenting differs per Harness]` does not say. — *Fix:* *Consider:* either trim the index entry to `- §4.9 FR-27 — span parenting differs per Harness.` or extend the inline tag to match; the two should be identical.

30. **[prose]** prd.md — Glossary-term capitalization drift in §3–§11 (one row, all locations). — *Fix:* Glossary "Project": `Scopes secrets and the gateway key.` → `Scopes secrets and the Gateway key.`; Glossary "Trace": `harness/gateway generations` → `Harness/Gateway generations`; Glossary "Step": `inside the story loop` → `inside the Story loop`; FR-12 c2: `as a new attempt with a new Session id` → `as a new Attempt with a new Session id`; FR-17 c1: `After every Story step attempt` → `After every Story step Attempt`; FR-14 c5: `the harness's own configuration` → `the Harness's own configuration`; FR-27 c2: `harness spans are children` → `Harness spans are children`; FR-18 c4 / FR-19 c3 / FR-23 intro: `gate record` → `Gate record` (three occurrences); §6.1: `checkpoints, blocked-answer` → `Checkpoints, blocked-answer`; SM-C1: `**SM-C1: Verify steps \`skipped\`**` → `**SM-C1: Verify Steps \`skipped\`**`.

31. **[prose]** prd.md §4 headings — `### 4.2 Projects and repositories` and `### 4.5 Story steps and harnesses` leave Glossary terms lowercase while `### 4.7 Board and Run detail` capitalizes them. — *Fix:* → `### 4.2 Projects and Repositories`; → `### 4.5 Story steps and Harnesses`.

32. **[prose]** prd.md and addendum.md — mixed British/American spelling against an American baseline (`Realizes`, `optimize`, `serialization`, `Finalize` are American). — *Fix:* §4.4 description: `finalises` → `finalizes`; §4.7 description and NFR-6: `Colour` → `Color`, `coloured` → `colored`, `colour` → `color` (three occurrences); NFR-8: `apologises` → `apologizes`. Leave the status token `cancelled` unchanged (it is code).

33. **[prose]** prd.md §1 Vision, paragraph 1 — comma splice in a 60-word sentence: `the agent plans, implements, reviews and commits, the orchestrator verifies the committed result` — *Fix:* → `the agent plans, implements, reviews, and commits; the orchestrator verifies the committed result`.

34. **[prose]** prd.md and addendum.md — serial comma missing in lists of three or more (one row). — *Fix:* FR-3 intro: `\`install_command\`, \`quality_gate_command\` and \`unit_test_command\`` → `\`install_command\`, \`quality_gate_command\`, and \`unit_test_command\``; Glossary "Question": `Harness, model and time` → `Harness, model, and time`; FR-21 c3: `Answer, Continue, Skip and Retry are disabled` → `Answer, Continue, Skip, and Retry are disabled`.

35. **[prose]** prd.md §4.4 FR-10 consequence 3 — one 75-word sentence chains the verify command, the failure append, the status reset, the re-dispatch, and the second-failure outcome. — *Fix:* split at the semicolon and after "once": `verify runs \`quality_gate_command\` in the Worktree on the tree the agent committed. On exit ≠ 0 the orchestrator appends a \`## Verify Failure\` section (command, exit code, last 200 lines) to the Story file, sets its status to \`in-progress\` (which routes the agent straight to implementation), and re-dispatches once. A second failure sets the Run to \`needs-you\` with reason \`verify failed 2/2\`.`

36. **[prose]** prd.md §4.5 FR-16 consequence 1 — 70 words, uses `=` for "means", and the parenthetical `(Step \`done\` only if the status routes on)` is unclear. — *Fix:* `Exactly one matching file with parseable frontmatter = liveness satisfied (Step \`done\` only if the status routes on); zero or several files, or unparseable frontmatter = Step \`error\`,` → `Exactly one matching file with parseable frontmatter satisfies liveness; the Step is \`done\` only when its status routes forward (next bullet). Zero or several files, or unparseable frontmatter, is Step \`error\`,`. *Consider:* confirm "routes on" means "status is `done`".

37. **[prose]** prd.md §4.6 FR-18 consequence 2 — an 80-word bullet with three semicolon clauses and an inline assumption. — *Fix:* split into three sentences at the semicolons: `…(so no \`stories/{id}-*.md\` remains and the re-dispatch is a first dispatch). The re-dispatch prompt carries \`Answer from the operator to the blocking condition "{condition}": {answer}\` as planning context. The Story step re-runs on the same Harness.`

38. **[prose]** prd.md §4.6 FR-21 consequence 4 — nested parentheticals make the polling cadence and the resume condition hard to separate. — *Fix:* `If the Story file reads \`done\` and the Worktree is clean (\`git status --porcelain\` empty, no \`.git/index.lock\`) on two consecutive server-side polls (every 30 s while a terminal session is in progress) while the Run is \`needs-you\`, the Run resumes at verify without an Answer.` → `While a terminal session is in progress and the Run is \`needs-you\`, the server polls the Worktree every 30 s. When two consecutive polls find the Story file \`done\` and the Worktree clean (\`git status --porcelain\` empty, no \`.git/index.lock\`), the Run resumes at verify without an Answer.`

39. **[prose]** prd.md §4.6 description — `every stop offers the same small set of actions on the Run detail` names no actions; FR-18..FR-20 do. — *Fix:* → `every stop offers the same small set of actions on the Run detail (Answer, Continue, Skip, Retry, Cancel; FR-18..FR-20)`.

40. **[prose]** prd.md §4.2 FR-4 — intro `reports per check` and consequence 3 `a failure flips the Repository's status` are vague. — *Fix:* `and reports per check.` → `and reports the result of each check.`; *Consider:* name the status the failure sets (`sets the Repository's status to failed`?) — the target status is not stated anywhere.

41. **[prose]** prd.md §4.4 FR-8 consequence 1 — `prefix-free ids` is undefined jargon; an engineer may read it as "ids without a prefix". — *Fix:* *Consider:* → `ids of which none is a prefix of another (so \`{id}-*\` globs are unambiguous)`.

42. **[prose]** prd.md §4.4 FR-10 consequence 4 — `(Spec folder first)` is ambiguous about what "first" orders. — *Fix:* *Consider:* → `(the Spec folder staged before the rest of the tree)`.

43. **[prose]** prd.md — "wall-clock" used as a noun in three places. — *Fix:* FR-10 c5: `maximum wall-clock, declarable` → `maximum wall-clock time, declarable`; FR-14 c6: `exit code, wall-clock, tokens in/out, cost` → `exit code, wall-clock time, tokens in/out, cost`; FR-23 c4: `tokens in/out, wall-clock, active Operator time` → `tokens in/out, wall-clock time, active Operator time`.

44. **[prose]** prd.md §0 — `used from day eight` spells out a day number that everywhere else is a numeral (`day 4`, `day 3`, `Day 1`). — *Fix:* → `used from day 8`.

45. **[prose]** prd.md §7 — SM-3 comma splice `no target, this is the comparison` → `no target; this is the comparison`; SM-2 `Validates FR-23, FR-18.` → `Validates FR-18, FR-23.` (every other entry lists FRs ascending).

46. **[prose]** prd.md §4.6 FR-20 consequence 3 — `Cancel requires a confirm;` — "confirm" as a noun. — *Fix:* → `Cancel requires a confirmation;`.

47. **[prose]** prd.md §6.1 — `in the instrument-dark system` names the visual system without a pointer; it is defined only in `DESIGN.md`. — *Fix:* *Consider:* → `in the instrument-dark visual system (\`DESIGN.md\`)`.

48. **[prose]** addendum.md §H — bullet lead-ins mix four punctuation styles (`**The agent commits.**`, `**Worktree retention**:`, `**Verify failure re-dispatch:**`, `**PR link** is`). — *Fix:* normalize to bold label plus colon inside the bold, as §D does: `**The agent commits.**` → `**The agent commits:**`; `**Dirty-tree pre-dispatch rule.**` → `**Dirty-tree pre-dispatch rule:**`; `**Step timeouts.**` → `**Step timeouts:**`; `**Done checkpoint mechanism.**` → `**Done checkpoint mechanism:**`; `**Budget check timing.**` → `**Budget check timing:**`; `**Daily Clone check.**` → `**Daily Clone check:**`; `**Worktree retention**:` → `**Worktree retention:**`; `**PR link** is the compare URL only` → `**PR link:** the compare URL only`; `**Gate record** is a first-class entity` → `**Gate record:** a first-class entity`.

49. **[prose]** addendum.md §H — open-question references use two forms in the same section: `**Open questions 1 and 2**` and `(OQ5)`, `(OQ1)`; PRD §6.1 uses `Open questions 2 and 4`. — *Fix:* use one form; shortest consistent choice: `(OQ5)` → `(Open question 5)`, `(OQ1)` → `(Open question 1)`.

50. **[prose]** addendum.md §B — `since the 08-24 addendum` is an undefined reference (the PRD names only the 2026-08-24 PRD). — *Fix:* → `since the 2026-08-24 PRD's addendum`.

51. **[prose]** addendum.md §D "Answer (revised at Finalize)" and §H heading "Corrections surfaced at Finalize" — "Finalize" is a PRD-workflow step name that an architect reading the addendum cold will not recognize. — *Fix:* *Consider:* `(revised at Finalize)` → `(revised at PRD finalization)`; `## H. Corrections surfaced at Finalize (for bmad-architecture)` → `## H. Corrections surfaced at PRD finalization (for bmad-architecture)`.

*3 further minor items, not listed as rows:* "Mac Mini" → "Mac mini" (Apple's spelling; §10 NFR-7, §8 OQ4, §12); §4.9 description is the only §4.x description without a `Realizes …` line (it realizes the second job in §2.1, not a UJ); §12 Platform's last sentence repeats §0's pointer to `addendum.md` and `architecture-v1.md`.

---

## Summary

- 48 recommendations (21 structure, 27 prose). No content or scope changes proposed; no length target was provided.
- Estimated reduction if all structure rows are accepted: about −84 words on `prd.md` (−1.2% of 7,169) and −26 words on `addendum.md` (−1.8% of 1,478). Format-only splits (rows 13, 16, 17, 20) and the prose splits are word-neutral.
- Comprehension trade-offs: rows 5, 6, 7, 8, 9, 11, 12 replace restatements with cross-references; a reader of that section alone must follow one pointer. Row 21 explicitly preserves the Glossary's non-alphabetical order.
- Structural items that should be settled before downstream documents cite section numbers: rows 1, 2, 19.
