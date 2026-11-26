/**
 * Pure formatting for the Initiative page's right column. State words, `draft` and `changed`
 * are the API's and pass through verbatim; only times, short ids, headings and the
 * folder-relative path are formatted here.
 */
import type { components } from '../../api/schema';
import { turnTime } from './conversation';

type StepFile = components['schemas']['StepFileOut'];
type SessionEntry = components['schemas']['SessionEntryOut'];

export const AUTO_FILES_LINK = 'all files per epic and story → workflow page';

export function shortId(id: string): string {
  return `${id.slice(0, 4)}…${id.slice(-4)}`;
}

export function workflowHeading(position: number, name: string): string {
  return `${position} · ${name.toUpperCase()}`;
}

export function stepGroupHeading(stepId: string): string {
  return stepId.toUpperCase();
}

export function filePath(path: string, folder: string): string {
  const prefix = `${folder}/`;
  return path.startsWith(prefix) ? path.slice(prefix.length) : path;
}

export function fileMeta(file: Pick<StepFile, 'time' | 'draft'>): string {
  return [turnTime(file.time), file.draft ? 'draft' : ''].filter(Boolean).join(' · ');
}

export function sessionLine(entry: SessionEntry): string {
  return [entry.step, `${entry.kind} ${shortId(entry.id)}`, entry.state]
    .filter((p): p is string => !!p)
    .join(' · ');
}
