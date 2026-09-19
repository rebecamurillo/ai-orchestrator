/**
 * The GATE RECORD timeline (4.15, right column): `time · path · event · actor · text`, one
 * row per `gate_record[]` entry, oldest first (the API's own order — `infrastructure/db/
 * repositories/gate_records.py::list_for_run`). The last row carries a `■` marker, in the
 * signal colour while the Run is stopped (`needs_you`/`failed`), plain otherwise — the
 * binding rule's "current row `■` in the signal colour".
 *
 * Stateless (`renderToStaticMarkup`).
 */
import type { RunDetailOut, Token } from '../../lib/run/detail';
import { bannerLevel } from '../../lib/run/detail';

interface Props {
  detail: RunDetailOut;
  token: Token;
}

export default function GateRecord({ detail, token }: Props) {
  // Neutral for a `blocked` detail (5.10's own signal rule — see `Banner.tsx`'s own comment).
  const level = detail.alert?.park_kind === 'blocked' ? null : bannerLevel(token);
  const lastIndex = detail.gate_record.length - 1;

  return (
    <section className="wf-gate-record" data-testid="wf-gate-record">
      <h2 className="wf-section-head">GATE RECORD</h2>
      {detail.gate_record.map((record, index) => (
        <p key={record.id} className="wf-gate-row">
          <span
            className="wf-gate-marker"
            data-signal={index === lastIndex && level ? level : undefined}
          >
            ■
          </span>
          <span>{record.at}</span>
          <span>{record.path ?? '—'}</span>
          <span>{record.event}</span>
          <span>{record.actor}</span>
          <span>{record.text}</span>
          {record.mode ? <span data-testid="wf-gate-mode">{record.mode}</span> : null}
        </p>
      ))}
    </section>
  );
}
