/**
 * The plain row shape `VersionsList.astro` renders (3.5), in its own module for the same
 * reason `src/components/repository-row.ts` is: `tests/types/astro-modules.d.ts` gives a
 * `.ts` file importing a `.astro` component only its default export, and
 * `templates-components.test.ts` needs the real type to build fixture rows.
 *
 * `pinned_by` is deliberately absent — `TemplateVersionOut.pinned_by` is always `0` this
 * release, so the component states "pinned by 0 runs" outright rather than reading a field
 * that can only ever hold that one value.
 */
export interface CalledByRef {
  name: string;
  version: number;
}

export interface VersionRow {
  name: string;
  version: number;
  calledBy: CalledByRef[];
  href: string;
  active: boolean;
}
