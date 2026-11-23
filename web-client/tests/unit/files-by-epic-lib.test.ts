/** `src/lib/run/files-by-epic.ts` — the pure view of `GET /runs/{id}/files-by-epic` (epic 2 story 1). */
import { describe, expect, it } from 'vitest';

import {
  belowFolder,
  buildFilesView,
  diffLines,
  epicAnchor,
  filesByEpicRequestPath,
  focusAnchor,
  storyAnchor,
} from '../../src/lib/run/files-by-epic';
import { twoEpicFiles } from '../fixtures/files-by-epic';

const VIEW = buildFilesView(twoEpicFiles());

describe('buildFilesView', () => {
  it('labels an epic, its folder and its files in order', () => {
    const epic = VIEW[0]!;
    expect(epic.label).toBe('epic 1 · models');
    expect(epic.folder).toBe('specs/epic-1-models/');
    expect(epic.anchor).toBe('files-epic-0');
    expect(epic.files.map((f) => f.name)).toEqual([
      'SPEC.md',
      'stories.yaml',
      'spec-gate-result.md',
    ]);
    expect(epic.files[0]!.path).toBe('specs/epic-1-models/SPEC.md');
  });

  it('labels a story, its file below the folder and its changed count', () => {
    const story = VIEW[0]!.stories[0]!;
    expect(story.label).toBe('story 1 · model list');
    expect(story.anchor).toBe('files-story-0-1');
    expect(story.file).toEqual({
      path: 'specs/epic-1-models/stories/1-model-list.md',
      name: 'stories/1-model-list.md',
    });
    expect(story.changedLabel).toBe('changed: 2 files');
    expect(story.noFile).toBe(false);
  });

  it('has no changed label when nothing changed, and says no file yet when not started', () => {
    expect(VIEW[0]!.stories[1]!.changedLabel).toBeNull();
    const third = VIEW[0]!.stories[2]!;
    expect(third.noFile).toBe(true);
    expect(third.file).toBeNull();
  });
});

describe('anchors and paths', () => {
  it('builds the anchors and the request path', () => {
    expect(epicAnchor(2)).toBe('files-epic-2');
    expect(storyAnchor(0, '1')).toBe('files-story-0-1');
    expect(filesByEpicRequestPath('r1')).toBe('/runs/r1/files-by-epic');
  });

  it('belowFolder strips the folder, or leaves a path outside it', () => {
    expect(belowFolder('a/b', 'a/b/c.md')).toBe('c.md');
    expect(belowFolder('a/b', 'x/c.md')).toBe('x/c.md');
  });
});

describe('focusAnchor', () => {
  it('maps an epic and a story node path', () => {
    expect(focusAnchor(VIEW, 'epics[1]')).toBe('files-epic-1');
    expect(focusAnchor(VIEW, 'epics[0].stories[1]')).toBe('files-story-0-2');
  });

  it('accepts a group-prefixed path ending in the epic', () => {
    expect(focusAnchor(VIEW, 'plan.epics[0]')).toBe('files-epic-0');
  });

  it('maps stories[j] to epic 0 (one-folder Run)', () => {
    expect(focusAnchor(VIEW, 'stories[1]')).toBe('files-story-0-2');
  });

  it('matches the epic by index, not position', () => {
    const skipped = [{ ...VIEW[1]! }];
    expect(focusAnchor(skipped, 'epics[1]')).toBe('files-epic-1');
    expect(focusAnchor(skipped, 'epics[0]')).toBeNull();
  });

  it('is null for null, an unknown epic, an out-of-range story and junk', () => {
    expect(focusAnchor(VIEW, null)).toBeNull();
    expect(focusAnchor(VIEW, 'epics[9]')).toBeNull();
    expect(focusAnchor(VIEW, 'epics[0].stories[9]')).toBeNull();
    expect(focusAnchor(VIEW, 'stories[9]')).toBeNull();
    expect(focusAnchor(VIEW, 'root')).toBeNull();
    expect(focusAnchor([], 'stories[0]')).toBeNull();
  });
});

describe('diffLines', () => {
  it('classes add, del and context, headers as context', () => {
    expect(diffLines('--- a/x\n+++ b/x\n@@ -1 +1 @@\n-old\n+new\n same')).toEqual([
      { text: '--- a/x', kind: 'ctx' },
      { text: '+++ b/x', kind: 'ctx' },
      { text: '@@ -1 +1 @@', kind: 'ctx' },
      { text: '-old', kind: 'del' },
      { text: '+new', kind: 'add' },
      { text: ' same', kind: 'ctx' },
    ]);
  });
});
