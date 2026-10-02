/**
 * What saving this Template as a new version does to the Templates that call it
 * (AD-15, unpinned callees, 2026-10-02). A caller whose `uses: template` step omits
 * `version` resolves to the latest stored version when a Run is planned, so it follows the
 * save without being edited; a caller that wrote an integer stays on that version. Either
 * way a Run already planned keeps the tree it was planned from — hence the last line.
 */
import type { CalledByRef } from '../../components/templates/version-row';

export const APPLIES_LINE = 'applies to Runs planned after this save';

const ref = (caller: CalledByRef): string => `${caller.name}@${caller.version}`;

export function saveImpactLines(calledBy: CalledByRef[], version: number): string[] {
  const follows = calledBy.filter((caller) => !caller.pinned).map(ref);
  const pinned = calledBy.filter((caller) => caller.pinned).map(ref);
  const lines: string[] = [];
  if (follows.length > 0) lines.push(`followed on save by ${follows.join(', ')}`);
  if (pinned.length > 0) lines.push(`pinned to v${version}, will not follow: ${pinned.join(', ')}`);
  lines.push(APPLIES_LINE);
  return lines;
}
