/**
 * The pre-flight's per-epic list (S7), grouped by repository (`epicsByRepository`) and, in
 * turn, every group and epic in the response's own topological `order[]`. Each epic shows
 * its id, title, `depends_on`, checkpoint kind, working branch and its own `lines[]`.
 *
 * `PreflightLines.tsx` is not reused here even though the shape is the same `LineOut[]`: it
 * carries fixed test-ids (`newwf-preflight`, `newwf-preflight-{check}`) that this list would
 * repeat once per epic, which breaks Playwright's strict-mode uniqueness the first time two
 * epics share a check name. This renders the same three-part line in its own,
 * epic-qualified test-ids instead.
 *
 * Stateless (`renderToStaticMarkup`), `PlanTable.tsx`'s own precedent.
 */
import type { components } from '../../api/schema';
import { checkSlug, lineWord } from '../../lib/newwf/state';
import { epicsByRepository, listText, orDash } from '../../lib/initiative/preflight';

type EpicPreflightOut = components['schemas']['EpicPreflightOut'];
type LineOut = components['schemas']['LineOut'];

interface Props {
  epics: EpicPreflightOut[];
  order: string[];
}

function EpicLine({ epicId, line, index }: { epicId: string; line: LineOut; index: number }) {
  return (
    <p
      className="newin-epic-line"
      data-testid={`newin-epic-${epicId}-${checkSlug(line.check)}-${index}`}
    >
      <span
        className="newin-epic-line-word"
        data-signal={line.status === 'fail' ? 'failed' : undefined}
      >
        {lineWord(line.status)}
      </span>
      {` · ${line.check} · ${line.text}`}
    </p>
  );
}

export default function EpicList({ epics, order }: Props) {
  const groups = epicsByRepository(epics, order);

  if (groups.length === 0) {
    return (
      <p className="newin-empty" data-testid="newin-epics-empty">
        no epic resolved yet
      </p>
    );
  }

  return (
    <div className="newin-epics" data-testid="newin-epics">
      {groups.map((group) => (
        <div className="newin-epic-group" key={group.repositoryId ?? 'unassigned'}>
          <p className="newin-epic-group-head">{group.repository ?? 'unassigned repository'}</p>
          {group.epics.map((epic) => (
            <div
              className="newin-epic"
              key={epic.epic_id}
              data-testid={`newin-epic-${epic.epic_id}`}
            >
              <p className="newin-epic-head">
                <span className="newin-epic-id">{epic.epic_id}</span>
                <span className="newin-epic-title">{epic.title}</span>
              </p>
              <p className="newin-epic-meta">
                depends on {listText(epic.depends_on)} · checkpoint {orDash(epic.checkpoint)} ·
                working branch {orDash(epic.working_branch)}
              </p>
              {epic.lines.map((line, index) => (
                <EpicLine
                  key={`${line.check}-${index}`}
                  epicId={epic.epic_id}
                  line={line}
                  index={index}
                />
              ))}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
