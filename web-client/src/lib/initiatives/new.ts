/**
 * The pure formatting and selection behind the New initiative page. Nothing here is stored or
 * sent: `slugOf` mirrors `backend-api/.../domain/entities/project.py::slugify` for display
 * only (the backend's slug is the one kept), and the status word comes from `statusToken`.
 */
import type { components } from '../../api/schema';
import { statusToken, type InitiativeRow } from './format';

export type PackageOut = components['schemas']['PackageOut'];
export type ProjectRead = components['schemas']['ProjectRead'];
type Entry = components['schemas']['SequenceEntryOut'];

export const NO_PACKAGE_LINE =
  "no package installed · install one in the project's Package section";

export function slugOf(name: string): string {
  const slug = name
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
    .replace(/-+$/, '');
  return slug || 'project';
}

export function liveLine(slug: string, folder: string): string {
  return `slug ${slug} · folder ${folder}/${slug} · spec branch spec/${slug}`;
}

export function hubHint(pkg: PackageOut): string {
  return `hub repository ${pkg.repository.slug} · base ${pkg.repository.default_branch}`;
}

const workflows = (pkg: PackageOut): Entry[] =>
  pkg.sequence.filter((e) => e.shown_as === 'workflow');

export function packageLine(pkg: PackageOut): string {
  return `package ${pkg.name} · installed ${pkg.installed_at.slice(0, 10)} · ${workflows(pkg).length} workflows`;
}

export function folderLine(pkg: PackageOut): string {
  return `initiative folder ${pkg.repository.initiative_folder} (repository setting)`;
}

export function firstWorkflow(pkg: PackageOut): string {
  return workflows(pkg)[0]?.workflow ?? '';
}

export function createLabel(pkg: PackageOut | null): string {
  return pkg ? `Create and start ${firstWorkflow(pkg)}` : 'Create and start';
}

export function firstAgent(pkg: PackageOut): string {
  const first = workflows(pkg)[0]?.steps[0];
  return first ? (first.persona ?? first.id) : '';
}

export function messageHint(agent: string): string {
  return `Sent to the ${agent} agent as turn 1. The conversation is saved; leave and come back to it from the initiative page.`;
}

export interface BandRow {
  n: string;
  name: string;
  kind: string;
  agent: string;
}

export interface Band {
  n: number;
  workflow: string;
  templateRef: string;
  typeWord: 'INTERACTIVE' | 'AUTO';
  rows: BandRow[];
  defaultsLine: string | null;
}

function defaultsText(project: ProjectRead | null): string {
  const budget = project?.default_budget_usd;
  if (budget === null || budget === undefined) {
    return 'no default budget — the build will stop and ask';
  }
  return `project defaults: autonomy ${project?.default_autonomy ?? '—'}, ${project?.default_model ?? '—'}, budget $${Number(budget).toFixed(2)}`;
}

export function sequenceBands(pkg: PackageOut, project: ProjectRead | null): Band[] {
  const bands: Band[] = [];
  pkg.sequence.forEach((entry, i) => {
    if (entry.shown_as !== 'workflow') return;
    const n = bands.length + 1;
    const interactive = entry.type === 'interactive';
    const rows: BandRow[] = [];
    if (interactive) {
      entry.steps.forEach((s, k) => {
        rows.push({
          n: `${n}.${k + 1}`,
          name: s.id,
          kind:
            s.kind === 'conversation'
              ? `conversation · writes ${s.writes.join(', ')}`
              : 'automatic',
          agent: s.persona ?? '',
        });
      });
      for (let j = i + 1; j < pkg.sequence.length && pkg.sequence[j].shown_as === 'step'; j++) {
        rows.push({
          n: `${n}.${rows.length + 1}`,
          name: pkg.sequence[j].workflow,
          kind: 'automatic',
          agent: pkg.sequence[j].steps[0]?.persona ?? '',
        });
      }
    }
    const lead =
      bands.length > 0
        ? `starts by itself when ${bands[bands.length - 1].workflow} is done · `
        : '';
    bands.push({
      n,
      workflow: entry.workflow,
      templateRef: entry.version === null ? entry.template : `${entry.template}@${entry.version}`,
      typeWord: interactive ? 'INTERACTIVE' : 'AUTO',
      rows,
      defaultsLine: interactive ? null : lead + defaultsText(project),
    });
  });
  return bands;
}

export function openHolder(items: InitiativeRow[], slug: string): InitiativeRow | null {
  return items.find((i) => i.slug === slug && i.status !== 'cancelled') ?? null;
}

export function slugTakenParts(holder: InitiativeRow): {
  lead: string;
  linkText: string;
  href: string;
  tail: string;
} {
  return {
    lead: `slug ${holder.slug} is used by an open initiative: `,
    linkText: holder.slug,
    href: `/initiatives/${holder.id}`,
    tail: ` (${holder.step}, ${statusToken(holder.status).word}). A cancelled initiative's slug is free.`,
  };
}

export function canCreate(s: {
  name: string;
  message: string;
  hasPackage: boolean;
  refused: boolean;
  submitting: boolean;
}): boolean {
  return (
    s.hasPackage && !s.refused && !s.submitting && s.name.trim() !== '' && s.message.trim() !== ''
  );
}
