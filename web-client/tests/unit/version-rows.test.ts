/**
 * `buildVersionRows` (3.5), extracted from `[name]/[version].astro` so it can be driven
 * directly with a non-empty cross-Template `summaryItems` — the live page can only ever pass
 * an empty one (`GET /api/v1/templates` is forced empty in the shared e2e stub), so the
 * "own versions pass wins over the cross-Template summary pass for the same key" precedence
 * rule was otherwise unexercised (Review Triage Log, story 3.5, finding 7).
 */
import { describe, expect, it } from 'vitest';

import { buildVersionRows } from '../../src/lib/templates/version-rows';

describe('buildVersionRows', () => {
  it('lets the own-versions pass win over the cross-Template summary for the same name::version', () => {
    const rows = buildVersionRows({
      name: 'demo',
      versionNumber: 1,
      // the cross-Template summary already knows about demo v1, but as a placeholder row —
      // no caller, not marked active — exactly what a real, populated `GET /api/v1/templates`
      // would answer for a Template this page did not fetch full detail for
      summaryItems: [
        { name: 'demo', description: null, latest_version: 1, versions: [1] },
        { name: 'helper', description: null, latest_version: 1, versions: [1] },
      ],
      ownVersions: [1],
      calledByLoaded: [{ name: 'helper', version: 1 }],
    });

    const demoRow = rows.find((row) => row.name === 'demo' && row.version === 1)!;
    expect(demoRow.active).toBe(true);
    expect(demoRow.calledBy).toEqual([{ name: 'helper', version: 1 }]);

    // the summary's own row for a Template this page never fetched detail for is untouched
    const helperRow = rows.find((row) => row.name === 'helper' && row.version === 1)!;
    expect(helperRow.active).toBe(false);
    expect(helperRow.calledBy).toEqual([]);
  });

  it('unions the loaded version into ownVersions, even if the versions fetch omitted it', () => {
    const rows = buildVersionRows({
      name: 'demo',
      versionNumber: 2,
      summaryItems: [],
      ownVersions: [1], // a versions-list read that somehow missed the version being rendered
      calledByLoaded: [],
    });

    const loadedRow = rows.find((row) => row.name === 'demo' && row.version === 2);
    expect(loadedRow).toBeDefined();
    expect(loadedRow!.active).toBe(true);
  });

  it('sorts by name, then by version ascending', () => {
    const rows = buildVersionRows({
      name: 'story',
      versionNumber: 2,
      summaryItems: [{ name: 'epic', description: null, latest_version: 1, versions: [1] }],
      ownVersions: [2, 1],
      calledByLoaded: [],
    });

    expect(rows.map((row) => `${row.name}@${row.version}`)).toEqual([
      'epic@1',
      'story@1',
      'story@2',
    ]);
  });

  it('encodes the Template name in every row href', () => {
    const rows = buildVersionRows({
      name: 'weird name',
      versionNumber: 1,
      summaryItems: [],
      ownVersions: [1],
      calledByLoaded: [],
    });

    expect(rows[0]!.href).toBe('/templates/weird%20name/1');
  });
});
