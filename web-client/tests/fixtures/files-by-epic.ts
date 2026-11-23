import type { components } from '../../src/api/schema';

export type RunFilesByEpicOut = components['schemas']['RunFilesByEpicOut'];

/** Two epics; epic 0 has story 1 (two changed paths), a story at position 1, and story 3 not started. */
export function twoEpicFiles(): RunFilesByEpicOut {
  return {
    epics: [
      {
        index: 0,
        title: 'models',
        folder: 'specs/epic-1-models',
        files: [
          'specs/epic-1-models/SPEC.md',
          'specs/epic-1-models/stories.yaml',
          'specs/epic-1-models/spec-gate-result.md',
        ],
        stories: [
          {
            id: '1',
            title: 'model list',
            started: true,
            story_file: 'specs/epic-1-models/stories/1-model-list.md',
            changed: ['src/models.py', 'tests/test_models.py'],
          },
          {
            id: '2',
            title: 'model detail',
            started: true,
            story_file: 'specs/epic-1-models/stories/2-model-detail.md',
            changed: [],
          },
          { id: '3', title: 'model delete', started: false, story_file: null, changed: [] },
        ],
      },
      {
        index: 1,
        title: 'views',
        folder: 'specs/epic-2-views',
        files: ['specs/epic-2-views/SPEC.md'],
        stories: [],
      },
    ],
  } satisfies RunFilesByEpicOut;
}
