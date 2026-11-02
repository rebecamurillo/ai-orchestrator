/**
 * Story 2-1, CAP-8: the *Pause* control beside *Cancel run* (`PauseControl.tsx`, wired into
 * `StopBody.tsx`'s running body), and the `paused` stop's own body.
 *
 * `vitest.config.ts` runs in `environment: 'node'`, so what is asserted is the closed render;
 * the confirm-and-post path is `ConfirmAction`'s tested contract and `run-detail-pause.spec.ts`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import PauseControl from '../../src/components/run/PauseControl';
import StopBody from '../../src/components/run/StopBody';
import type { RunDetailOut, SignalKind, Token } from '../../src/lib/run/detail';
import { PAUSE_REQUESTED_LINE } from '../../src/lib/run/pause';

function detail(over: Record<string, unknown>): RunDetailOut {
  return {
    run: {
      id: '1',
      status: 'running',
      branch: 'epics/1',
      pause_requested: undefined,
      ...(over.run as object),
    },
    alert: over.alert ?? null,
    steps: [],
    stories: [],
    gate_record: [],
    admitted_signals: over.admitted ?? [],
    cost: { budget_usd: '15', spent_usd: '0' },
    summary: null,
  } as unknown as RunDetailOut;
}

function body(
  d: RunDetailOut,
  token: Token,
  error: { title: string; detail?: string } | null = null,
): string {
  return renderToStaticMarkup(
    createElement(StopBody, {
      detail: d,
      token,
      onSignal: () => {},
      onCancelClick: () => {},
      posting: null,
      error: error as never,
    }),
  );
}

function control(d: RunDetailOut, disabled = false): string {
  return renderToStaticMarkup(
    createElement(PauseControl, {
      run: d.run,
      admitted: d.admitted_signals,
      disabled,
      onPause: () => {},
    }),
  );
}

const RUNNING: SignalKind[] = ['pause', 'cancel'];

describe('PauseControl', () => {
  it('offers a confirmed Pause while the server lists it', () => {
    const html = control(detail({ admitted: RUNNING }));

    expect(html).toContain('data-testid="wf-signal-pause"');
    expect(html).toContain('Pause');
    expect(html).not.toContain('data-testid="wf-confirm-pause"');
  });

  it('disables the trigger while a signal is in flight', () => {
    expect(control(detail({ admitted: RUNNING }), true)).toContain('disabled=""');
  });

  it('renders nothing when the server does not list pause', () => {
    expect(control(detail({ admitted: ['cancel'] }))).toBe('');
  });

  it('states the pending request in place of the button', () => {
    const html = control(detail({ admitted: ['cancel'], run: { pause_requested: true } }));

    expect(html).toContain('data-testid="wf-pause-requested"');
    expect(html).toContain(PAUSE_REQUESTED_LINE);
    expect(html).not.toContain('wf-signal-pause');
  });
});

describe('StopBody · a running Run', () => {
  it('puts Pause beside Cancel run', () => {
    const html = body(detail({ admitted: RUNNING }), 'RUN');

    expect(html).toContain('data-testid="wf-signal-pause"');
    expect(html).toContain('data-testid="wf-cancel"');
    expect(html.indexOf('wf-signal-pause')).toBeLessThan(html.indexOf('wf-cancel'));
  });

  it('keeps Cancel run alone once the request stands', () => {
    const html = body(detail({ admitted: ['cancel'], run: { pause_requested: true } }), 'RUN');

    expect(html).not.toContain('wf-signal-pause');
    expect(html).toContain('data-testid="wf-pause-requested"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it("shows the server's refusal in the existing error readout", () => {
    const html = body(detail({ admitted: RUNNING }), 'RUN', {
      title: 'Conflict',
      detail: 'signal pause invalid for status running / park None',
    });

    expect(html).toContain('data-testid="wf-signal-error"');
    expect(html).toContain('signal pause invalid for status running / park None');
  });

  it('keeps the plain Cancel run it always had when pause is not listed', () => {
    const html = body(detail({ admitted: ['cancel'] }), 'RUN');

    expect(html).not.toContain('wf-signal-pause');
    expect(html).toContain('data-testid="wf-cancel"');
  });
});

describe('StopBody · a paused stop', () => {
  const paused = detail({
    run: { status: 'needs_you' },
    alert: {
      token: 'CHK',
      reason: "paused at the Operator's request; next: stories[0].verify",
      park_kind: 'paused',
    },
    admitted: ['continue', 'cancel'],
  });

  it('has its own body with the reason, Continue and Cancel run', () => {
    const html = body(paused, 'CHK');

    expect(html).toContain('data-testid="wf-stop-paused"');
    expect(html).toContain('paused at the Operator&#x27;s request; next: stories[0].verify');
    expect(html).toContain('data-testid="wf-signal-continue"');
    expect(html).toContain('data-testid="wf-cancel"');
  });

  it('offers nothing else', () => {
    const html = body(paused, 'CHK');

    expect(html).not.toContain('wf-signal-pause');
    expect(html).not.toContain('wf-signal-retry');
    expect(html).not.toContain('wf-signal-skip');
  });
});
