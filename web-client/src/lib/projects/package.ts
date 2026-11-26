/** The Package section's kv rows and defaults, derived from a `PackageOut`. Pure, no I/O. */
import type { components } from '../../api/schema';
import { statusToken, type InitiativeStatus } from '../initiatives/format';

export type PackageOut = components['schemas']['PackageOut'];

export const PACKAGE_HINT =
  'Initiatives already started keep their sequence; agent and skill edits apply from their next step.';

type Row = { label: string; value: string };

const STATUS_WORDS: readonly string[] = [
  'running',
  'waiting for her',
  'done',
  'failed',
  'cancelled',
];

export function mapToken(value: string): string {
  return STATUS_WORDS.includes(value) ? statusToken(value as InitiativeStatus).token : value;
}

export function packageKvRows(pkg: PackageOut): Row[] {
  const workflows = pkg.sequence.filter((e) => e.shown_as === 'workflow');
  const rows: Row[] = [
    { label: 'package', value: pkg.name },
    { label: 'installed', value: pkg.installed_at.slice(0, 10) },
    { label: 'workflows', value: workflows.map((e) => `${e.workflow} ${e.type}`).join(' ▸ ') },
  ];
  pkg.sequence.forEach((entry, i) => {
    if (entry.shown_as !== 'workflow' || entry.type !== 'interactive') return;
    const parts = entry.steps.map((s) => `${s.id} · ${s.persona ?? s.kind}`);
    for (let j = i + 1; j < pkg.sequence.length && pkg.sequence[j]!.shown_as === 'step'; j++) {
      parts.push(`${pkg.sequence[j]!.workflow} · automatic`);
    }
    rows.push({ label: `steps ${entry.workflow}`, value: parts.join(', ') });
  });
  const mapping = Object.entries(pkg.status_map);
  if (mapping.length === 0) rows.push({ label: 'status mapping', value: '—' });
  mapping.forEach(([word, value], k) =>
    rows.push({ label: k === 0 ? 'status mapping' : '', value: `${word} → ${mapToken(value)}` }),
  );
  return rows;
}

export function defaultRepositoryId(
  pkg: PackageOut | null,
  repositories: { id: string }[],
): string | null {
  if (pkg && repositories.some((r) => r.id === pkg.repository_id)) return pkg.repository_id;
  return repositories[0]?.id ?? null;
}
