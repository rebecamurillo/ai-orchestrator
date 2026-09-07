/**
 * The STORIES strip (4.15, right column): one section per epic (`n/m` done), one cell per
 * story by id — done filled, current amber, future hollow, skipped struck (binding rule).
 * Naming rule (UX-DR16): this strip prints labels (the epic head), never `path`.
 *
 * Stateless (`renderToStaticMarkup`); `''` (nothing rendered) for a Template with no Story
 * frame at all (`repo-init`) — `storiesByEpic([])` is `[]`.
 */
import { epicDoneCount, storiesByEpic, type StoryCellOut } from '../../lib/run/detail';

interface Props {
  stories: StoryCellOut[];
}

export default function StoriesStrip({ stories }: Props) {
  const groups = storiesByEpic(stories);
  if (groups.length === 0) return null;

  return (
    <section className="wf-stories" data-testid="wf-stories">
      <h2 className="wf-section-head">STORIES</h2>
      {groups.map(([epicIndex, cells]) => (
        <div key={epicIndex} className="wf-stories-epic">
          <p className="wf-stories-epic-head">
            epic {epicIndex} · {epicDoneCount(cells)}
          </p>
          <div className="wf-stories-cells">
            {cells.map((cell) => (
              <span
                key={cell.story_id}
                className="wf-story-cell"
                data-testid={`wf-story-${cell.story_id}`}
                data-state={cell.state}
                title={`${cell.story_id} · ${cell.state}`}
              />
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
