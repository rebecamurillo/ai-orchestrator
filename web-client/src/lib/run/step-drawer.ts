/** The lines of a `StepDrawerOut` (EXPERIENCE § 6.2); pure, no status is derived here. */
import type { components } from '../../api/schema';
import { ageText } from '../board/format';

type StepDrawerOut = components['schemas']['StepDrawerOut'];
type DrawerHeaderOut = components['schemas']['DrawerHeaderOut'];
type FilesReadOut = components['schemas']['FilesReadOut'];
type FilesWrittenOut = components['schemas']['FilesWrittenOut'];

export interface HeaderLines {
  label: string;
  path: string;
  token: string;
  kindGate: string;
  figure: string;
}

export interface RunOrderRowView {
  seq: number;
  phase: string;
  label: string;
  kind: string;
  token: string;
  current: boolean;
}

export function drawerRequestPath(runId: string, seq: number, n: number): string {
  return `/runs/${runId}/steps/${seq}/attempts/${n}/drawer`;
}

export function isAgentStep(header: DrawerHeaderOut): boolean {
  return header.kind === 'agent';
}

export function headerSeconds(header: DrawerHeaderOut): number | null {
  if (header.started_at === null || header.ended_at === null) return null;
  return (Date.parse(header.ended_at) - Date.parse(header.started_at)) / 1000;
}

function durationText(header: DrawerHeaderOut): string {
  const seconds = headerSeconds(header);
  return seconds === null ? '—' : ageText(Math.floor(seconds));
}

export function headerLines(out: StepDrawerOut): HeaderLines {
  const { header } = out;
  const figure = isAgentStep(header)
    ? `${out.attempts.length} attempts · $${header.cost_usd ?? '0'}`
    : `${durationText(header)} · exit ${header.exit_code ?? '—'}`;
  return {
    label: header.label,
    path: header.path,
    token: header.token,
    kindGate: `${header.kind} · ${header.gate}`,
    figure,
  };
}

export function runOrderView(
  out: StepDrawerOut,
): { heading: string; rows: RunOrderRowView[] } | null {
  if (out.run_order === null) return null;
  return {
    heading: `RUN ORDER · ${out.run_order.frame}`,
    rows: out.run_order.rows.map((row) => ({
      seq: row.seq,
      phase: row.phase,
      label: row.label,
      kind: row.kind,
      token: row.token,
      current: row.seq === out.header.seq,
    })),
  };
}

export function filesReadLines(read: FilesReadOut): string[] {
  if (read.state === 'listed') return read.paths;
  if (read.state === 'none') return ['this step read no file'];
  return ['deterministic step · files read are not recorded; the command is in the log'];
}

export function filesWrittenLines(written: FilesWrittenOut): string[] {
  const files = written.files.map((file) =>
    file.added === null || file.removed === null
      ? `${file.path} binary`
      : `${file.path} +${file.added} −${file.removed}`,
  );
  if (written.state === 'files') return files;
  if (written.state === 'commit') {
    if (written.commit === null) return files;
    const sha = written.commit.sha.slice(0, 7);
    const head =
      written.commit.message === null
        ? `commit ${sha}`
        : `commit ${sha} · ${written.commit.message}`;
    return [head, ...files];
  }
  if (written.state === 'refs') return written.refs.map((ref) => `no file · refs updated: ${ref}`);
  return ['no file'];
}

export function logHeading(n: number): string {
  return `LOG · ATTEMPT ${n}`;
}
