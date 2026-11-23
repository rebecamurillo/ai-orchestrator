/**
 * The one step drawer of the Run page (epic 2 story 2, EXPERIENCE § 6.2): run order, log,
 * files read and files written of the `(seq, n)` in `$stepDrawer`. Token and phase are shown
 * as the read sends them; nothing here derives a status.
 */
import { useStore } from '@nanostores/react';
import { useEffect, useRef, useState } from 'react';

import { api } from '../../api/client';
import { tokenSignal } from '../../lib/board/format';
import {
  drawerRequestPath,
  filesReadLines,
  filesWrittenLines,
  headerLines,
  logHeading,
  runOrderView,
} from '../../lib/run/step-drawer';
import { encode } from '../../lib/step-path';
import { $originTarget } from '../../stores/metric-ui';
import { $poll } from '../../stores/poll';
import { $stepDrawer, closeStepDrawer, openStepDrawer } from '../../stores/step-drawer';
import { DrawerPanel } from './HelperDrawer';
import LogViewer from './LogViewer';
import type { components } from '../../api/schema';

type StepDrawerOut = components['schemas']['StepDrawerOut'];

// `key` is the `seq/n` the read answers, so a switch never shows the previous step's lines.
type Read = { key: string; out: StepDrawerOut } | { key: string; error: true } | null;

function Lines({ lines }: { lines: string[] }) {
  return (
    <>
      {lines.map((line, i) => (
        <p key={i} className="wf-step-drawer-line">
          {line}
        </p>
      ))}
    </>
  );
}

export default function StepDrawer({ runId }: { runId: string }) {
  const target = useStore($stepDrawer);
  const tick = useStore($poll);
  const originOpen = useStore($originTarget) !== null;
  const [read, setRead] = useState<Read>(null);
  const requests = useRef(0);
  const seq = target?.seq;
  const n = target?.n;
  const open = target !== null;

  useEffect(() => {
    if (seq === undefined || n === undefined) return;
    const mine = ++requests.current;
    const key = `${seq}/${n}`;
    void (async () => {
      const { data, error } = await api.GET('/runs/{run_id}/steps/{seq}/attempts/{n}/drawer', {
        params: { path: { run_id: runId, seq, n } },
      });
      if (mine !== requests.current) return;
      setRead(error || !data ? { key, error: true } : { key, out: data });
    })();
  }, [runId, seq, n, tick]);

  useEffect(() => {
    if (open) document.getElementById('wf-step-drawer-heading')?.focus();
  }, [open, seq]);

  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent): void {
      // an open origin drawer takes this Escape; the step drawer closes on the next one
      if (event.key === 'Escape' && !originOpen) close();
    }
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open, originOpen]);

  function close(): void {
    const openerId = $stepDrawer.get()?.openerId ?? '';
    closeStepDrawer();
    requests.current += 1;
    setRead(null);
    (document.getElementById(openerId) ?? document.getElementById('wf-steps-heading'))?.focus();
  }

  if (target === null) return null;
  const current = read !== null && read.key === `${target.seq}/${target.n}` ? read : null;
  const out = current !== null && 'out' in current ? current.out : null;
  const lines = out ? headerLines(out) : null;
  const order = out ? runOrderView(out) : null;

  const head = (
    <>
      <h2 id="wf-step-drawer-heading" className="wf-step-drawer-title" tabIndex={-1}>
        {lines?.label ?? ''}
      </h2>
      {lines ? (
        <a
          className="wf-step-drawer-full"
          data-testid="wf-step-drawer-full"
          href={`/workflows/${runId}/steps/${encode(lines.path)}`}
        >
          full page
        </a>
      ) : null}
    </>
  );

  return (
    <DrawerPanel className="wf-step-drawer" testId="wf-step-drawer" head={head} onClose={close}>
      {current !== null && 'error' in current ? (
        <p className="wf-step-drawer-line">
          could not read {drawerRequestPath(runId, target.seq, target.n)}
        </p>
      ) : null}
      {out && lines ? (
        <>
          <p className="wf-step-drawer-line">{lines.path}</p>
          <p className="wf-step-drawer-line">
            <span className="wf-step-token" data-signal={tokenSignal(lines.token)}>
              {lines.token}
            </span>
          </p>
          <p className="wf-step-drawer-line">{lines.kindGate}</p>
          <p className="wf-step-drawer-line">{lines.figure}</p>
          {order ? (
            <section data-testid="wf-step-drawer-order">
              <h3 className="wf-step-drawer-label">{order.heading}</h3>
              {order.rows.map((row) => (
                <button
                  key={row.seq}
                  type="button"
                  className={row.current ? 'wf-step-drawer-row-current' : undefined}
                  aria-current={row.current ? 'step' : undefined}
                  onClick={() => openStepDrawer(row.seq, 0, target.openerId)}
                >
                  <span>{row.phase}</span> <span>{row.label}</span> <span>{row.kind}</span>{' '}
                  <span className="wf-step-token" data-signal={tokenSignal(row.token)}>
                    {row.token}
                  </span>
                </button>
              ))}
            </section>
          ) : null}
          <section data-testid="wf-step-drawer-log">
            <h3 className="wf-step-drawer-label">{logHeading(out.header.n ?? target.n)}</h3>
            {out.log.attempt_id !== null ? (
              <LogViewer
                key={out.log.attempt_id}
                runId={runId}
                attemptId={out.log.attempt_id}
                isRunning={out.header.status === 'running'}
                // stand-in until story 4 changes LogViewer's props: download shows only for text
                logPath={out.log.state === 'text' ? out.log.attempt_id : null}
              />
            ) : null}
          </section>
          <section>
            <h3 className="wf-step-drawer-label">FILES READ</h3>
            <Lines lines={filesReadLines(out.files_read)} />
          </section>
          <section>
            <h3 className="wf-step-drawer-label">FILES WRITTEN</h3>
            <Lines lines={filesWrittenLines(out.files_written)} />
          </section>
        </>
      ) : null}
    </DrawerPanel>
  );
}
