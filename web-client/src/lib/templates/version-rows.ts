/**
 * The VERSIONS column's row-merge logic (3.5), extracted from `[name]/[version].astro` so a
 * unit test can drive it directly with non-empty cross-Template data. The live page can only
 * ever pass an empty `summaryItems` — `GET /api/v1/templates` is forced empty in the shared
 * e2e stub (the story's Design Notes) — so this function's "own versions" pass winning over
 * the "cross-Template summary" pass for the same `name::version` key was otherwise
 * unexercised by anything but the always-empty case (Review Triage Log, story 3.5, finding 7).
 */
import type { components } from '../../api/schema';
import type { CalledByRef, TemplateType, VersionRow } from '../../components/templates/version-row';

type TemplateSummary = components['schemas']['TemplateSummaryOut'];
type TemplateCaller = components['schemas']['TemplateCallerOut'];

export interface BuildVersionRowsArgs {
  name: string;
  versionNumber: number;
  summaryItems: TemplateSummary[];
  ownVersions: number[];
  calledByLoaded: TemplateCaller[];
  ownTypes: ReadonlyMap<number, TemplateType>;
}

/**
 * Every row this Template's or another Template's version can contribute, merged by
 * `name::version` — a later assignment (this Template's own `versions` read) wins over an
 * earlier one (the cross-Template summary), since it is the more specific source.
 *
 * `versionNumber` (the version actually loaded) is unioned into `ownVersions` rather than
 * trusted to already be a member of it: if `GET /templates/{name}/versions` ever answered a
 * list that somehow omitted it, the row for the version rendering on screen would otherwise
 * vanish from its own VERSIONS column (Review Triage Log, story 3.5, finding 5).
 */
export function buildVersionRows({
  name,
  versionNumber,
  summaryItems,
  ownVersions,
  calledByLoaded,
  ownTypes,
}: BuildVersionRowsArgs): VersionRow[] {
  const byKey = new Map<string, VersionRow>();
  const key = (rowName: string, rowVersion: number) => `${rowName}::${rowVersion}`;
  const href = (rowName: string, rowVersion: number) =>
    `/templates/${encodeURIComponent(rowName)}/${rowVersion}`;

  for (const item of summaryItems) {
    for (const v of item.versions) {
      byKey.set(key(item.name, v), {
        name: item.name,
        version: v,
        calledBy: [],
        href: href(item.name, v),
        active: false,
        type: null,
      });
    }
  }

  const everyOwnVersion = new Set([...ownVersions, versionNumber]);
  for (const v of everyOwnVersion) {
    byKey.set(key(name, v), {
      name,
      version: v,
      calledBy: v === versionNumber ? calledByLoaded.map((ref): CalledByRef => ({ ...ref })) : [],
      href: href(name, v),
      active: v === versionNumber,
      type: ownTypes.get(v) ?? null,
    });
  }

  return [...byKey.values()].sort((a, b) => a.name.localeCompare(b.name) || a.version - b.version);
}

/** Each own version's type: the loaded version from the payload the page holds, the rest read
 * in parallel through the injected `read`; a rejected or null read leaves that version absent. */
export async function readVersionTypes({
  versions,
  loaded,
  read,
}: {
  versions: number[];
  loaded: { version: number; type: TemplateType };
  read: (version: number) => Promise<TemplateType | null>;
}): Promise<Map<number, TemplateType>> {
  const types = new Map<number, TemplateType>([[loaded.version, loaded.type]]);
  const others = [...new Set(versions)].filter((v) => v !== loaded.version);
  await Promise.all(
    others.map(async (v) => {
      try {
        const type = await read(v);
        if (type) types.set(v, type);
      } catch {
        // best effort: the row prints no type word
      }
    }),
  );
  return types;
}
