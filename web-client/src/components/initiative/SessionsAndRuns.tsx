/**
 * The right column's SESSIONS AND RUNS list. A Run row links to its workflow page; a session
 * row carries no link because the API sends no Run id for a session.
 */
import type { components } from '../../api/schema';
import { sessionLine } from '../../lib/initiative/files';

type SessionEntry = components['schemas']['SessionEntryOut'];

export default function SessionsAndRuns({ sessions }: { sessions: SessionEntry[] }) {
  return (
    <section className="ini-links" data-testid="ini-links">
      <div className="ini-section-head">
        <span>SESSIONS AND RUNS</span>
      </div>
      {sessions.map((entry) => (
        <div className="ini-link" data-testid="ini-link" key={`${entry.kind}-${entry.id}`}>
          <span className="ini-link-workflow">{entry.workflow}</span>
          {entry.kind === 'run' ? (
            <a href={`/workflows/${entry.id}`}>{sessionLine(entry)}</a>
          ) : (
            <span>{sessionLine(entry)}</span>
          )}
        </div>
      ))}
    </section>
  );
}
