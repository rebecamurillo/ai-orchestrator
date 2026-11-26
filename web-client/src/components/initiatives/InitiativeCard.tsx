/** One initiative: the whole card is a single link to its page. Nothing is derived here. */
import { ageText, isAgedNeedsYou, tokenSignal } from '../../lib/board/format';
import { ageSecondsSince, statusToken, type InitiativeRow } from '../../lib/initiatives/format';
import Tag from './Tag';
import WorkflowFoot from './WorkflowFoot';

interface Props {
  item: InitiativeRow;
  nowMs: number;
}

export default function InitiativeCard({ item, nowMs }: Props) {
  const { token, word } = statusToken(item.status);
  const signal = tokenSignal(token);
  const ageSeconds = ageSecondsSince(item.updated_at, nowMs);
  const blocked = item.status === 'waiting for her';
  return (
    <a
      className="ini-card"
      data-testid={`initiatives-card-${item.slug}`}
      href={`/initiatives/${item.id}`}
      draggable={false}
      data-left-rule={blocked ? 'needs-you' : undefined}
    >
      <span className="ini-card-head">
        <span className="ini-card-token" data-signal={signal}>
          <span className="ini-card-chip" />
          {token}
          <span className="ini-card-word">{word}</span>
        </span>
        <span
          className="ini-card-age"
          data-signal={isAgedNeedsYou(token, ageSeconds) ? 'needs-you' : undefined}
        >
          {ageText(ageSeconds)}
        </span>
      </span>
      <span className="ini-card-name">{item.name}</span>
      <span className="ini-card-tags">
        <Tag label="project" value={item.project_name} />
        {item.repo_tag.map((repo) => (
          <Tag key={repo} label="repo" value={repo} />
        ))}
      </span>
      <span className="ini-card-line" data-signal={blocked ? 'needs-you' : undefined}>
        {item.line}
      </span>
      <span className="ini-card-progress">{item.progress}</span>
      <WorkflowFoot workflows={item.workflows} current={item.workflow} />
    </a>
  );
}
