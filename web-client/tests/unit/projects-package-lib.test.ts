/** Story 10.5: src/lib/projects/package.ts. */
import { describe, expect, it } from 'vitest';

import {
  PACKAGE_HINT,
  defaultRepositoryId,
  mapToken,
  packageKvRows,
  type PackageOut,
} from '../../src/lib/projects/package';

type Entry = PackageOut['sequence'][number];
type Step = Entry['steps'][number];

const step = (id: string, persona: string | null, kind: Step['kind'] = 'conversation'): Step => ({
  id,
  persona,
  kind,
  file: null,
  skill: null,
  writes: [],
});
const entry = (
  workflow: string,
  type: Entry['type'],
  shown_as: Entry['shown_as'],
  steps: Step[] = [],
): Entry => ({ workflow, type, shown_as, steps, template: workflow, version: null });

function pkg(sequence: Entry[], status_map: Record<string, string> = {}): PackageOut {
  return {
    name: 'rebecamurillo-initiatives',
    installed_at: '2026-11-20T10:00:00Z',
    repository_id: 'hub-id',
    sequence,
    status_map,
  } as unknown as PackageOut;
}

describe('packageKvRows', () => {
  it('reads name, date, workflows and the status mapping', () => {
    const rows = packageKvRows(
      pkg([entry('spec', 'interactive', 'workflow'), entry('build', 'auto', 'workflow')], {
        final: 'done',
        blocked: 'waiting for her',
      }),
    );
    expect(rows).toEqual([
      { label: 'package', value: 'rebecamurillo-initiatives' },
      { label: 'installed', value: '2026-11-20' },
      { label: 'workflows', value: 'spec interactive ▸ build auto' },
      { label: 'steps spec', value: '' },
      { label: 'status mapping', value: 'final → DON' },
      { label: '', value: 'blocked → BLK' },
    ]);
  });

  it('lists steps with persona, kind fallback and trailing step entries; auto has none', () => {
    const rows = packageKvRows(
      pkg([
        entry('spec', 'interactive', 'workflow', [
          step('brief', 'analyst'),
          step('check', 'reviewer'),
          step('write', null, 'automatic'),
        ]),
        entry('merge', 'auto', 'step'),
        entry('build', 'auto', 'workflow'),
      ]),
    );
    expect(rows.filter((r) => r.label.startsWith('steps'))).toEqual([
      {
        label: 'steps spec',
        value: 'brief · analyst, check · reviewer, write · automatic, merge · automatic',
      },
    ]);
    expect(rows.find((r) => r.label === 'workflows')!.value).toBe('spec interactive ▸ build auto');
  });

  it('prints a dash for an empty status map', () => {
    const rows = packageKvRows(pkg([]));
    expect(rows[rows.length - 1]).toEqual({ label: 'status mapping', value: '—' });
  });
});

describe('mapToken', () => {
  it('maps the five initiative words and passes others as sent', () => {
    expect(mapToken('running')).toBe('RUN');
    expect(mapToken('failed')).toBe('ERR');
    expect(mapToken('mystery')).toBe('mystery');
  });
});

describe('defaultRepositoryId', () => {
  it('prefers the hub, then the first, then null', () => {
    const repos = [{ id: 'a' }, { id: 'hub-id' }];
    expect(defaultRepositoryId(pkg([]), repos)).toBe('hub-id');
    expect(defaultRepositoryId(null, repos)).toBe('a');
    expect(defaultRepositoryId(pkg([]), [{ id: 'z' }])).toBe('z');
    expect(defaultRepositoryId(null, [])).toBeNull();
  });
});

it('carries the hint verbatim', () => {
  expect(PACKAGE_HINT).toBe(
    'Initiatives already started keep their sequence; agent and skill edits apply from their next step.',
  );
});
