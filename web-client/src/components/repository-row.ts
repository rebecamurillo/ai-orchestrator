/**
 * The plain row shape `RepositoriesTable.astro` renders (2.4), in its own module rather than
 * exported from the component's frontmatter: `tests/types/astro-modules.d.ts` gives a `.ts`
 * file importing a `.astro` component only its default export, so a type a plain module
 * needs to share has to live in a plain module.
 *
 * `index.astro` computes one of these per Repository from `GET /api/v1/projects/{id}`'s
 * embedded `repositories[]` — `method` is `bmad_version ?? '—'` and `seconds` is the sum of
 * `clone_check_lines[].seconds`, both already resolved before this shape exists, so the
 * component itself does no further derivation from the API's own field names.
 */
/**
 * The Repository's own most recent `repo-init` Run (4.10, UX-DR12), as `index.astro` reads
 * it off `GET /api/v1/projects/{id}`'s embedded `runs[]`. `token` is `StatusToken`'s own
 * vocabulary (`QUE RUN BLK CHK DON ERR CAN`); a `repo-init` Run never reads `SKP`.
 */
export interface RepositoryRun {
  id: string;
  token: 'QUE' | 'RUN' | 'BLK' | 'CHK' | 'DON' | 'ERR' | 'CAN' | 'SKP';
  reason: string;
  compareUrl: string | null;
}

export interface RepositoryRow {
  id: string;
  slug: string;
  defaultBranch: string;
  method: string;
  qualityGateCommand: string;
  testGlobs: string[];
  status: 'pending' | 'ok' | 'failed';
  seconds: number;
  output: string;
  hint: string;
  verifySkipped: boolean;
  //: Optional (4.10): `tests/unit/projects-components.test.ts` (2.4) builds a `RepositoryRow`
  //: with neither field, and that frozen fixture must keep compiling.
  methodNeedsInit?: boolean;
  run?: RepositoryRun | null;
}
