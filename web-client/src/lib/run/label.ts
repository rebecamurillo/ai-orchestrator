/**
 * The Run label's pure helpers. `defaultLabelPreview` mirrors
 * `backend-api/.../rules/run_label.py::default_label`; the server stays the authority and
 * the preview is only the placeholder text of the New workflow field.
 */
import type { components } from '../../api/schema';

type RunLabelIn = components['schemas']['RunLabelIn'];

export const EDIT_LABEL = 'edit label';
export const SAVE_LABEL = 'save label';
export const MAX_LABEL = 120;

export function runTitle(run: { label?: string; branch: string }): string {
  return run.label ?? run.branch;
}

/** Blank text restores the computed default. */
export function labelPayload(text: string): RunLabelIn {
  return { label: text.trim() || null };
}

export function labelState(byOperator: boolean): string {
  return byOperator ? 'your label · clear it to restore the default' : 'default label';
}

export function PLACEHOLDER(label: string): string {
  return `default: ${label}`;
}

function folderName(inputs: Record<string, string>): string {
  for (const key of ['initiative_folder', 'spec_folder']) {
    const raw = inputs[key];
    if (raw) return raw.replace(/\/+$/, '').split('/').pop() ?? '';
  }
  return '';
}

interface PreviewArgs {
  projectName: string;
  inputs: Record<string, string>;
  template: string;
  nowMs: number;
}

export function defaultLabelPreview({ projectName, inputs, template, nowMs }: PreviewArgs): string {
  const minute = new Date(nowMs).toISOString().slice(0, 16).replace('T', ' ');
  return [projectName, folderName(inputs), template, minute].filter(Boolean).join(' ');
}
