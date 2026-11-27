import type { components } from '../../api/schema';

type LogPageOut = components['schemas']['LogPageOut'];

export function logWords(
  page: Pick<LogPageOut, 'state' | 'reason' | 'removed_at' | 'lines'>,
  exitCode: number | null,
  seconds: number | null,
): string | null {
  if (page.state === 'no_output') {
    return `no output · ${page.reason ?? 'the command ran and printed nothing'}`;
  }
  if (page.state === 'removed') {
    if (!page.removed_at) return page.lines[0] ?? 'log no longer on disk';
    const code = exitCode === null ? '—' : String(exitCode);
    const duration = seconds === null ? '—' : `${Math.round(seconds)}s`;
    return `log removed by the retention sweep on ${page.removed_at.slice(0, 10)} · exit ${code} · ${duration} were recorded`;
  }
  return null;
}

export function showsDownload(page: Pick<LogPageOut, 'state' | 'reason'>): boolean {
  if (page.state === undefined || page.state === 'text') return true;
  return page.state === 'no_output' && !page.reason;
}

export function notRunLine(reason: string | null): string {
  return reason ? `not run · ${reason}` : 'not run';
}
