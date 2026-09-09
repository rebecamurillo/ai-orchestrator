/**
 * `lib/run/artifacts.ts` (6.3, FR-19, FR-23, UX-DR9): the ARTIFACTS column's own pure
 * facts — the two request-path builders, the list-file gate, the Markdown/plain-text split,
 * the two verbatim sentences (the editor's hint and a list file's read-only line), the
 * tree's own indent depth and `mtime` text, and the GET response's own tree/file guard.
 */
import { describe, expect, it } from 'vitest';

import {
  canEditFile,
  editHint,
  fileName,
  fileRequestPath,
  isListFile,
  isMarkdown,
  isTree,
  mtimeText,
  readOnlyLine,
  treeDepth,
  treeRequestPath,
  type RunFileEntryOut,
} from '../../../src/lib/run/artifacts';
import type { RunDetailOut } from '../../../src/lib/run/detail';

const FOLDER = 'specs/gates';

function aRun(overrides: Partial<RunDetailOut['run']> = {}): RunDetailOut['run'] {
  return {
    id: '1',
    status: 'needs_you',
    admitted_signals: [],
    branch: 'epics/gates',
    budget_usd: '15',
    compare_urls: [],
    created_at: '2026-09-09T09:00:00Z',
    inputs: {},
    manual_estimate_h: null,
    plan_ref: 'abc1234',
    project: 'p1',
    repository: 'r1',
    spend_usd: '0',
    template: 'epic',
    terminal_session: false,
    version: 1,
    worktree_path: '/work/acme/widgets/wt/gates',
    worktrees: [],
    accepted_paths: [],
    ...overrides,
  };
}

function aFile(path: string, kind: 'file' | 'dir', mtime = 0): RunFileEntryOut {
  return { path, kind, size: 0, mtime };
}

describe('treeRequestPath / fileRequestPath', () => {
  it('builds the tree path with no query', () => {
    expect(treeRequestPath('r1')).toBe('/api/runs/r1/files');
  });

  it('builds the file path with an encoded query', () => {
    expect(fileRequestPath('r1', `${FOLDER}/SPEC.md`)).toBe(
      '/api/runs/r1/files?path=specs%2Fgates%2FSPEC.md',
    );
  });
});

describe('isListFile', () => {
  it('is true for stories.yaml and epics.yaml under the folder', () => {
    expect(isListFile(FOLDER, `${FOLDER}/stories.yaml`)).toBe(true);
    expect(isListFile(FOLDER, `${FOLDER}/epics.yaml`)).toBe(true);
  });

  it('is false for every other path, including a similarly named one', () => {
    expect(isListFile(FOLDER, `${FOLDER}/SPEC.md`)).toBe(false);
    expect(isListFile(FOLDER, `${FOLDER}/stories/2-x.md`)).toBe(false);
    expect(isListFile(FOLDER, 'elsewhere/stories.yaml')).toBe(false);
  });
});

describe('isMarkdown', () => {
  it('is true only for a .md path', () => {
    expect(isMarkdown(`${FOLDER}/SPEC.md`)).toBe(true);
    expect(isMarkdown(`${FOLDER}/stories.yaml`)).toBe(false);
  });
});

describe('editHint', () => {
  it('names the exact commit message and the branch, verbatim', () => {
    expect(editHint('epics/gates')).toBe(
      'saved as commit "spec: operator edit (orchestrator)" on epics/gates',
    );
  });
});

describe('readOnlyLine', () => {
  it('names the plan sha, verbatim', () => {
    expect(readOnlyLine('abc1234')).toBe('planned at abc1234 — start a new run to change the list');
  });

  it('falls back to an em dash when no plan_ref is on the wire yet', () => {
    expect(readOnlyLine(null)).toBe('planned at — — start a new run to change the list');
  });
});

describe('treeDepth', () => {
  it('is 0 for a direct child of the root', () => {
    expect(treeDepth(`${FOLDER}/SPEC.md`, FOLDER)).toBe(0);
  });

  it('is 1 for a file one directory below the root', () => {
    expect(treeDepth(`${FOLDER}/stories/2-x.md`, FOLDER)).toBe(1);
  });

  it('is 0 for the root itself', () => {
    expect(treeDepth(FOLDER, FOLDER)).toBe(0);
  });

  it('falls back to 0 when root is empty', () => {
    expect(treeDepth('README.md', '')).toBe(0);
  });
});

describe('mtimeText', () => {
  it('is the ISO instant for a file', () => {
    expect(mtimeText(aFile(`${FOLDER}/SPEC.md`, 'file', 0))).toBe('1970-01-01T00:00:00.000Z');
  });

  it('is empty for a directory row', () => {
    expect(mtimeText(aFile(`${FOLDER}/stories`, 'dir'))).toBe('');
  });
});

describe('fileName', () => {
  it('is the path’s own last segment', () => {
    expect(fileName(`${FOLDER}/stories/2-x.md`)).toBe('2-x.md');
  });
});

describe('canEditFile', () => {
  it('is true for a parked run, no terminal session, not a list file', () => {
    expect(canEditFile(aRun(), `${FOLDER}/SPEC.md`, FOLDER)).toBe(true);
  });

  it('is false when the run is not parked', () => {
    expect(canEditFile(aRun({ status: 'running' }), `${FOLDER}/SPEC.md`, FOLDER)).toBe(false);
  });

  it('is false during a terminal session even though the run is parked', () => {
    expect(canEditFile(aRun({ terminal_session: true }), `${FOLDER}/SPEC.md`, FOLDER)).toBe(false);
  });

  it('is false for a list file even on a parked run', () => {
    expect(canEditFile(aRun(), `${FOLDER}/stories.yaml`, FOLDER)).toBe(false);
  });
});

describe('isTree', () => {
  it('tells a tree response from a file response', () => {
    expect(isTree({ root: FOLDER, entries: [] })).toBe(true);
    expect(isTree({ path: `${FOLDER}/SPEC.md`, content: '', size: 0, mtime: 0 })).toBe(false);
  });
});
