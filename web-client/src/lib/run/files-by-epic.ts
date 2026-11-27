/** The view of `GET /runs/{run_id}/files-by-epic`: rows, anchors and diff lines, no I/O. */
import type { components } from '../../api/schema';

export type RunFilesByEpicOut = components['schemas']['RunFilesByEpicOut'];

export interface FileRef {
  path: string;
  name: string;
}

export interface StoryView {
  id: string;
  anchor: string;
  label: string;
  file: FileRef | null;
  changed: string[];
  changedLabel: string | null;
  noFile: boolean;
}

export interface EpicView {
  index: number;
  anchor: string;
  label: string;
  folder: string;
  files: FileRef[];
  stories: StoryView[];
}

export interface DiffLine {
  text: string;
  kind: 'add' | 'del' | 'ctx';
}

export function filesByEpicRequestPath(runId: string): string {
  return `/runs/${runId}/files-by-epic`;
}

export function epicAnchor(index: number): string {
  return `files-epic-${index}`;
}

export function storyAnchor(index: number, id: string): string {
  return `files-story-${index}-${id}`;
}

export function belowFolder(folder: string, path: string): string {
  const prefix = `${folder}/`;
  return path.startsWith(prefix) ? path.slice(prefix.length) : path;
}

export function buildFilesView(out: RunFilesByEpicOut): EpicView[] {
  return out.epics.map((epic) => ({
    index: epic.index,
    anchor: epicAnchor(epic.index),
    label: `epic ${epic.index + 1} · ${epic.title}`,
    folder: `${epic.folder}/`,
    files: epic.files.map((path) => ({ path, name: belowFolder(epic.folder, path) })),
    stories: epic.stories.map((story) => ({
      id: story.id,
      anchor: storyAnchor(epic.index, story.id),
      label: `story ${story.id} · ${story.title}`,
      file:
        story.story_file === null
          ? null
          : { path: story.story_file, name: belowFolder(epic.folder, story.story_file) },
      changed: story.changed,
      changedLabel: story.changed.length > 0 ? `changed: ${story.changed.length} files` : null,
      noFile: !story.started && story.story_file === null,
    })),
  }));
}

const EPIC_PATH = /(?:^|\.)epics\[(\d+)\](?:\.stories\[(\d+)\])?$/;
const STORY_PATH = /^stories\[(\d+)\]$/;

/** The anchor of the row a diagram node path (bracket form) names, or null. */
export function focusAnchor(view: EpicView[], focus: string | null): string | null {
  if (focus === null) return null;
  let epicIndex: number;
  let storyPos: string | undefined;
  const epicMatch = EPIC_PATH.exec(focus);
  const storyMatch = STORY_PATH.exec(focus);
  if (epicMatch) {
    epicIndex = Number(epicMatch[1]);
    storyPos = epicMatch[2];
  } else if (storyMatch) {
    epicIndex = 0;
    storyPos = storyMatch[1];
  } else {
    return null;
  }
  const epic = view.find((entry) => entry.index === epicIndex);
  if (!epic) return null;
  if (storyPos === undefined) return epic.anchor;
  return epic.stories[Number(storyPos)]?.anchor ?? null;
}

export function diffLines(text: string): DiffLine[] {
  return text.split('\n').map((line) => {
    if (line.startsWith('+++') || line.startsWith('---')) return { text: line, kind: 'ctx' };
    if (line.startsWith('+')) return { text: line, kind: 'add' };
    if (line.startsWith('-')) return { text: line, kind: 'del' };
    return { text: line, kind: 'ctx' };
  });
}
