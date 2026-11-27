/**
 * `buildVersionRows` (3.5), extracted from `[name]/[version].astro` so it can be driven
 * directly with a non-empty cross-Template `summaryItems` — the live page can only ever pass
 * an empty one (`GET /api/v1/templates` is forced empty in the shared e2e stub), so the
 * "own versions pass wins over the cross-Template summary pass for the same key" precedence
 * rule was otherwise unexercised (Review Triage Log, story 3.5, finding 7).
 */
import { describe, expect, it, vi } from 'vitest';

import { buildVersionRows, readVersionTypes } from '../../src/lib/templates/version-rows';

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
      calledByLoaded: [{ name: 'helper', version: 1, pinned: true }],
      ownTypes: new Map(),
    });

    const demoRow = rows.find((row) => row.name === 'demo' && row.version === 1)!;
    expect(demoRow.active).toBe(true);
    expect(demoRow.calledBy).toEqual([{ name: 'helper', version: 1, pinned: true }]);

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
      ownTypes: new Map(),
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
      ownTypes: new Map(),
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
      ownTypes: new Map(),
    });

    expect(rows[0]!.href).toBe('/templates/weird%20name/1');
  });
});

// Story 10.4, Operator ruling 2026-11-26: VersionRow.type.
describe('version row type', () => {
  const base = {
    name: 'demo',
    versionNumber: 1,
    summaryItems: [{ name: 'helper', description: null, latest_version: 1, versions: [1] }],
    ownVersions: [1, 2, 3],
    calledByLoaded: [],
  };

  it('takes own types from ownTypes, null when absent or for another Template', () => {
    const rows = buildVersionRows({
      ...base,
      ownTypes: new Map<number, 'interactive' | 'auto'>([
        [1, 'interactive'],
        [3, 'auto'],
      ]),
    });
    const type = (n: string, v: number) => rows.find((r) => r.name === n && r.version === v)!.type;
    expect(type('demo', 1)).toBe('interactive');
    expect(type('demo', 2)).toBeNull();
    expect(type('demo', 3)).toBe('auto');
    expect(type('helper', 1)).toBeNull();
  });
});

describe('readVersionTypes', () => {
  it('leaves rejected and null reads absent and never reads the loaded version', async () => {
    const read = vi.fn(async (v: number) => {
      if (v === 2) throw new Error('boom');
      if (v === 3) return null;
      return v === 4 ? ('auto' as const) : ('interactive' as const);
    });
    const map = await readVersionTypes({
      versions: [1, 2, 3, 4],
      loaded: { version: 1, type: 'interactive' },
      read,
    });
    expect(map.get(1)).toBe('interactive');
    expect(map.has(2)).toBe(false);
    expect(map.has(3)).toBe(false);
    expect(map.get(4)).toBe('auto');
    expect(read).not.toHaveBeenCalledWith(1);
    expect(read).toHaveBeenCalledTimes(3);
  });

  it('returns the loaded version alone for an empty list', async () => {
    const read = vi.fn();
    const map = await readVersionTypes({
      versions: [],
      loaded: { version: 5, type: 'auto' },
      read,
    });
    expect([...map]).toEqual([[5, 'auto']]);
    expect(read).not.toHaveBeenCalled();
  });
});
