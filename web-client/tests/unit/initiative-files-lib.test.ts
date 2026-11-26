/** Story 11.3 AC8: the pure helpers of `lib/initiative/files.ts`. */
import { describe, expect, it } from 'vitest';

import {
  AUTO_FILES_LINK,
  fileMeta,
  filePath,
  sessionLine,
  shortId,
  stepGroupHeading,
  workflowHeading,
} from '../../src/lib/initiative/files';

type Entry = Parameters<typeof sessionLine>[0];
const entry = (over: Partial<Entry>): Entry =>
  ({
    id: '0193a1b2-0000-7000-8000-0000000011ab',
    kind: 'session',
    round: 1,
    state: 'closed',
    step: 'tech',
    workflow: 'spec',
    ...over,
  }) as Entry;

describe('files helpers', () => {
  it('shortId joins the first and last 4 characters', () => {
    expect(shortId('0193a1b2c3d411ab')).toBe('0193…11ab');
  });
  it('headings', () => {
    expect(workflowHeading(1, 'spec')).toBe('1 · SPEC');
    expect(stepGroupHeading('ux')).toBe('UX');
  });
  it('filePath strips the folder, else returns the path unchanged', () => {
    expect(filePath('initiatives/x/DESIGN.md', 'initiatives/x')).toBe('DESIGN.md');
    expect(filePath('other/DESIGN.md', 'initiatives/x')).toBe('other/DESIGN.md');
  });
  it('fileMeta joins time and draft, dropping empty parts', () => {
    expect(fileMeta({ time: '2026-11-22T21:30:00Z', draft: true })).toBe('21:30 · draft');
    expect(fileMeta({ time: '2026-11-22T21:30:00Z', draft: false })).toBe('21:30');
    expect(fileMeta({ time: null, draft: true })).toBe('draft');
    expect(fileMeta({ time: null, draft: false })).toBe('');
  });
  it('sessionLine gives session and run lines, step absent for a run with null step', () => {
    expect(sessionLine(entry({}))).toBe('tech · session 0193…11ab · closed');
    expect(sessionLine(entry({ id: '0193c3d4-0000-7000-8000-000000007f21', state: 'open' }))).toBe(
      'tech · session 0193…7f21 · open',
    );
    expect(
      sessionLine(
        entry({
          kind: 'run',
          step: null,
          id: '0193e5f6-0000-7000-8000-000000008c02',
          state: 'running',
        }),
      ),
    ).toBe('run 0193…8c02 · running');
  });
  it('exports the auto-workflow link text', () => {
    expect(AUTO_FILES_LINK).toBe('all files per epic and story → workflow page');
  });
});
