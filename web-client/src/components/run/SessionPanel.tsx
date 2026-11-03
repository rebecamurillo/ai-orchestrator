/**
 * The Operator's senior session on the Run page (story 2-4, SPEC CAP-7): the offer at a stop
 * that admits `session_start`, the start form, and — once the server holds the Run — the
 * conversation, the message box and the close.
 *
 * Stateful only in what no other component reads: the form's choices, the draft, and which
 * anchor files the Operator has confirmed. The island owns every post and returns the
 * problem a refused one produced, so this panel never decides what the server allows. The
 * stop's other controls are absent while a session is open because `admitted_signals` omits
 * them; this panel states that, it does not enforce it.
 */
import { useEffect, useRef, useState } from 'react';

import { api } from '../../api/client';
import type { components } from '../../api/schema';
import type { SignalIn, SignalKind } from '../../lib/run/signals';
import {
  CLOSE_LABEL,
  LOCK_LINE,
  SEND_LABEL,
  SESSION_LABEL,
  confirmedFor,
  defaultScope,
  endBody,
  messageBody,
  offersSession,
  opensReview,
  canSend,
  reconcileModel,
  revertMessage,
  sessionOpen,
  startBody,
  startableHarnesses,
  toggleConfirmed,
  type HarnessOut,
  type ProbeResultOut,
  type SessionOut,
  type SessionScope,
} from '../../lib/run/session';
import SessionAnchors from './SessionAnchors';
import SessionStart from './SessionStart';
import SessionTurns from './SessionTurns';

const OFFER_SELECTOR = '[data-testid="wf-session-offer"]';

type ProblemDetail = components['schemas']['ProblemDetail'];
type Refusal = Promise<ProblemDetail | null>;

interface Props {
  runId: string;
  session: SessionOut | null;
  admitted: readonly SignalKind[];
  /** The signal in flight, if any: every control here waits for it. */
  posting: SignalKind | null;
  /** True while a message is being posted. */
  sending: boolean;
  onStart: (body: SignalIn) => Refusal;
  onEnd: (body: SignalIn) => Refusal;
  onMessage: (text: string) => Refusal;
}

export default function SessionPanel({
  runId,
  session,
  admitted,
  posting,
  sending,
  onStart,
  onEnd,
  onMessage,
}: Props) {
  const open = sessionOpen(session, admitted);
  const [formOpen, setFormOpen] = useState(false);
  const [scope, setScope] = useState<SessionScope | ''>('');
  const [harnesses, setHarnesses] = useState<HarnessOut[] | null>(null);
  const [harness, setHarness] = useState('');
  const [probe, setProbe] = useState<ProbeResultOut | null>(null);
  const [probing, setProbing] = useState(false);
  const [model, setModel] = useState('');
  const [draft, setDraft] = useState('');
  const [confirmed, setConfirmed] = useState<ReadonlySet<string>>(new Set());
  const [reviewing, setReviewing] = useState(false);
  const [refusal, setRefusal] = useState<ProblemDetail | null>(null);
  const probeSeqRef = useRef(0);
  const sectionRef = useRef<HTMLElement>(null);
  const mountedRef = useRef(false);

  // The control the Operator just used unmounts when the panel changes shape, which would drop
  // focus to the page. Each change hands it to the control that replaces it; the first render
  // leaves focus where the page put it.
  // The target waits for the post in flight, because a disabled control cannot take focus.
  const wantFocusRef = useRef<string | null>(null);
  useEffect(() => {
    if (mountedRef.current) wantFocusRef.current = open ? 'textarea' : OFFER_SELECTOR;
  }, [open]);
  useEffect(() => {
    if (mountedRef.current && !open) wantFocusRef.current = formOpen ? 'select' : OFFER_SELECTOR;
  }, [formOpen]);
  useEffect(() => {
    if (mountedRef.current && reviewing)
      wantFocusRef.current = '[data-testid="wf-session-anchors"]';
  }, [reviewing]);
  useEffect(() => {
    const selector = wantFocusRef.current;
    if (selector === null || posting !== null || sending) return;
    wantFocusRef.current = null;
    sectionRef.current?.querySelector<HTMLElement>(selector)?.focus();
  });
  useEffect(() => {
    mountedRef.current = true;
  }, []);

  useEffect(() => {
    if (!formOpen || harnesses !== null) return;
    let cancelled = false;
    void (async () => {
      try {
        const { data } = await api.GET('/harnesses');
        if (!cancelled) setHarnesses(startableHarnesses(data?.items ?? []));
      } catch {
        if (!cancelled) setHarnesses([]);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [formOpen, harnesses]);

  // a closed session leaves nothing behind: the next one starts from an empty review
  useEffect(() => {
    if (open) return;
    setReviewing(false);
    setRefusal(null);
    setConfirmed(new Set());
  }, [open]);

  // evaluated against each newer read too, so edits that reach the page after the refused
  // close's own refetch still open the review
  useEffect(() => {
    if (!opensReview(refusal, session)) return;
    setReviewing(true);
    setRefusal(null);
  }, [refusal, session]);

  async function chooseHarness(name: string): Promise<void> {
    const seq = ++probeSeqRef.current;
    setHarness(name);
    setProbe(null);
    setModel('');
    if (name === '') {
      setProbing(false);
      return;
    }
    setProbing(true);
    try {
      const { data } = await api.GET('/harnesses/{name}/probe', { params: { path: { name } } });
      if (seq !== probeSeqRef.current) return;
      setProbe(data ?? null);
      setModel((current) => reconcileModel(current, data?.models ?? []));
    } catch {
      if (seq === probeSeqRef.current) setProbe(null);
    } finally {
      if (seq === probeSeqRef.current) setProbing(false);
    }
  }

  async function start(): Promise<void> {
    if (scope === '') return;
    if ((await onStart(startBody(scope, harness, model))) === null) setFormOpen(false);
  }

  async function send(text: string): Promise<void> {
    if ((await onMessage(text)) === null) setDraft('');
  }

  async function revert(path: string): Promise<void> {
    await onMessage(revertMessage(path));
    setConfirmed((current) => (current.has(path) ? toggleConfirmed(current, path) : current));
  }

  async function close(paths: readonly string[]): Promise<void> {
    setRefusal(await onEnd(endBody(paths)));
  }

  if (open) {
    const turnRunning = session?.turn_running ?? false;
    const busy = posting !== null || sending;
    const edits = session?.anchor_edits ?? [];
    return (
      <section ref={sectionRef} className="wf-session" data-testid="wf-session">
        <p className="wf-session-lock" data-testid="wf-session-lock">
          {LOCK_LINE}
        </p>
        <SessionTurns runId={runId} turns={session?.turns ?? []} />
        <div className="wf-answer-box">
          <textarea
            className="wf-answer"
            data-testid="wf-session-message"
            rows={3}
            value={draft}
            disabled={turnRunning || busy || session === null}
            onChange={(event) => setDraft(event.target.value)}
            aria-label="Message to the senior"
          />
          <div className="wf-session-actions">
            <button
              type="button"
              className="wf-signal"
              data-testid="wf-session-send"
              disabled={!canSend(session, draft, busy)}
              onClick={() => void send(messageBody(draft).text)}
            >
              {SEND_LABEL}
            </button>
            {reviewing ? null : (
              <button
                type="button"
                className="wf-signal"
                data-testid="wf-session-close"
                disabled={turnRunning || busy}
                onClick={() => void close([])}
              >
                {CLOSE_LABEL}
              </button>
            )}
          </div>
        </div>
        {reviewing ? (
          <SessionAnchors
            edits={edits}
            confirmed={confirmed}
            turnRunning={turnRunning}
            posting={busy}
            onToggle={(path) => setConfirmed((current) => toggleConfirmed(current, path))}
            onRevert={(path) => void revert(path)}
            onClose={() => void close(confirmedFor(edits, confirmed))}
          />
        ) : null}
      </section>
    );
  }

  if (!offersSession(session)) return null;

  return (
    <section ref={sectionRef} className="wf-session" data-testid="wf-session-offer-zone">
      {formOpen ? (
        <SessionStart
          scopes={session?.scopes ?? []}
          scope={scope}
          harnesses={harnesses}
          harness={harness}
          probe={probe}
          probing={probing}
          model={model}
          posting={posting !== null}
          onScope={setScope}
          onHarness={(name) => void chooseHarness(name)}
          onModel={setModel}
          onStart={() => void start()}
          onDismiss={() => setFormOpen(false)}
        />
      ) : (
        <button
          type="button"
          className="wf-signal"
          data-testid="wf-session-offer"
          disabled={posting !== null}
          onClick={() => {
            setScope(defaultScope(session?.scopes ?? []));
            setFormOpen(true);
          }}
        >
          {SESSION_LABEL}
        </button>
      )}
    </section>
  );
}
