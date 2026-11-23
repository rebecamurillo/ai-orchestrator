/**
 * The Run detail's own files column (6.3, SPEC CAP-2, FR-19, FR-23; epic 2 story 1: grouped
 * by epic and story). `FilesByEpic` owns the fetch, the diff and the `ArtifactModal`; this
 * panel keeps the section and its `wf-artifacts` test id.
 *
 * Three props (`runId`, `run`, `folder`), the same three facts `RunDetail.tsx`'s own
 * `plannedFile` effect already reads off `detail`.
 */
import type { RunDetailOut } from '../../lib/run/detail';
import FilesByEpic from './FilesByEpic';

type RunSummary = RunDetailOut['run'];

interface Props {
  runId: string;
  run: RunSummary;
  folder: string;
}

export default function ArtifactsPanel({ runId, run, folder }: Props) {
  return (
    <section className="wf-artifacts" data-testid="wf-artifacts">
      <FilesByEpic runId={runId} run={run} folder={folder} />
    </section>
  );
}
