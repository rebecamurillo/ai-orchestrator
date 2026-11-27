// @vitest-environment jsdom
/** Story 11.2: the Conversation column (AC1, AC4–AC9). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('../../src/api/client', () => ({ api: { POST: vi.fn() } }));

import Conversation from '../../src/components/initiative/Conversation';
import { convStep, file, turn } from './conversation-fixtures';
import { detail, step, workflow, type Step } from './initiative-fixtures';

afterEach(cleanup);

function mount(s: Step, over: Parameters<typeof detail>[0] = {}, isCurrent = true, next?: Step) {
  const onSelectStep = vi.fn();
  const d = detail(over);
  const w = workflow('spec', 1, { steps: next ? [s, next] : [s] });
  render(createElement(Conversation, { detail: d, workflow: w, step: s, isCurrent, onSelectStep }));
  return onSelectStep;
}

const statuses = () => screen.queryAllByRole('status').map((e) => e.textContent);
const many = (k: number) => Array.from({ length: k }, (_, i) => turn(i + 1));

describe('Conversation', () => {
  it('AC1: running and queued lines, composer enabled', () => {
    mount(
      convStep({
        turns: [
          turn(14),
          turn(15, { status: 'running', reply: '', started_at: '2026-11-26T21:18:04Z' }),
          turn(16, {
            status: 'queued',
            message: 'Also the parent can hide a drawing from the summary.',
          }),
        ],
      }),
      { attention: 'queued' },
    );
    expect(screen.getByTestId('ini-turn-14')).toBeTruthy();
    expect(screen.getByTestId('ini-turn-15')).toBeTruthy();
    expect(screen.queryByTestId('ini-turn-16')).toBeNull();
    expect(statuses()).toEqual([
      'agent answering turn 15 · started 21:18:04',
      'queued · waits for turn 15 to finish: "Also the parent can hide a drawing from the summary."',
    ]);
    expect((screen.getByTestId('ini-message') as HTMLTextAreaElement).disabled).toBe(false);
    expect((screen.getByTestId('ini-send') as HTMLButtonElement).disabled).toBe(false);
  });

  it('AC4: closed line with an open-next button; planned next ends the line', () => {
    const closed = convStep({ token: 'DON', files: [file('DESIGN.md'), file('EXPERIENCE.md')] });
    const onSelect = mount(closed, {}, false, step('tech', { status: 'running' }));
    const line = screen.getByRole('status');
    expect(line.textContent).toBe(
      'step closed · DESIGN.md, EXPERIENCE.md written · committed on spec/familio-dessin-v2 · tech started → open tech',
    );
    fireEvent.click(within(line).getByRole('button', { name: 'open tech' }));
    expect(onSelect).toHaveBeenCalledWith('tech');
    cleanup();
    mount(closed, {}, false, step('tech'));
    expect(screen.getByRole('status').textContent).toBe(
      'step closed · DESIGN.md, EXPERIENCE.md written · committed on spec/familio-dessin-v2',
    );
  });

  it('AC5: the not-closed reason once, amber, with the composer', () => {
    const reason =
      'step not closed · EXPERIENCE.md has status draft, the done content is status final · the step stays open';
    mount(convStep({ park_reason: reason, turns: [turn(1)] }), {
      attention: 'blocked',
      reason: 'ignored',
    });
    const lines = screen.getAllByRole('status');
    expect(lines).toHaveLength(1);
    expect(lines[0].textContent).toBe(reason);
    expect(lines[0].getAttribute('data-signal')).toBe('needs-you');
    expect(screen.getByTestId('ini-message')).toBeTruthy();
  });

  it('AC6: blocked line unless the last turn failed', () => {
    const blocked = { attention: 'blocked', reason: 'R' } as const;
    mount(convStep({ park_reason: 'other', turns: [turn(1)] }), blocked);
    expect(statuses()).toEqual(['step blocked · R']);
    expect(screen.getByRole('status').getAttribute('data-signal')).toBe('needs-you');
    cleanup();
    mount(convStep({ turns: [turn(1, { status: 'failed' })] }), blocked);
    // Revised by story 11.5 (2026-11-26): a failed last turn now renders its red failed-turn
    // line; the `step blocked` line still never shows beside it.
    expect(statuses()).toEqual(['turn 1 failed · log']);
    expect(statuses().some((t) => t?.startsWith('step blocked'))).toBe(false);
    expect(screen.getByRole('status').getAttribute('data-signal')).toBe('failed');
  });

  it('AC7: your-turn line only without a reason', () => {
    mount(convStep({ turns: [turn(14)] }), { attention: 'your_turn', reason: '' });
    expect(statuses()).toEqual(['your turn · turn 15']);
    cleanup();
    mount(convStep({ turns: [turn(14)] }), { attention: 'your_turn', reason: 'why' });
    expect(statuses()).toEqual([]);
  });

  it.each(['DON', 'SKP'] as const)('AC8: a %s step is a record', (token) => {
    mount(convStep({ token, turns: many(23) }), {}, false);
    expect(screen.getAllByTestId(/^ini-turn-/).map((e) => e.getAttribute('data-testid'))).toEqual([
      'ini-turn-21',
      'ini-turn-22',
      'ini-turn-23',
    ]);
    expect(screen.queryByTestId('ini-message')).toBeNull();
    expect(screen.queryByTestId('ini-send')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'show all 23 turns' }));
    expect(screen.getAllByTestId(/^ini-turn-/)).toHaveLength(23);
    expect(screen.queryByRole('button', { name: /show all/ })).toBeNull();
  });

  it('AC8: no show-all button for 3 turns or fewer', () => {
    mount(convStep({ token: 'DON', turns: many(3) }), {}, false);
    expect(screen.queryByRole('button', { name: /show all/ })).toBeNull();
  });

  it('AC9: attribution, head and round line, no avatar', () => {
    mount(convStep({ turns: many(14) }));
    const li = screen.getByTestId('ini-turn-14');
    expect(li.textContent).toContain('You · 21:15');
    expect(li.textContent).toContain('message 14');
    expect(li.textContent).toContain('Agent · claude-opus-5-5 · 21:16');
    expect(li.textContent).toContain('reply 14');
    expect(screen.getByTestId('ini-conversation-head').textContent).toContain(
      'CONVERSATION · UX · ux-designer · claude · claude-opus-5-5',
    );
    expect(screen.getByTestId('ini-conversation-head').textContent).toContain('round 1 · 14 turns');
    expect(document.querySelector('img, [class*="avatar"], [class*="typing"]')).toBeNull();
  });

  it('AC9: an empty reply shows no agent part; a gate turn has no attribution', () => {
    mount(
      convStep({
        turns: [
          turn(1, { reply: '' }),
          turn(2, { author: 'gate', message: 'gate says', reply: 'ok' }),
        ],
      }),
    );
    expect(screen.getByTestId('ini-turn-1').textContent).not.toContain('Agent');
    const gate = screen.getByTestId('ini-turn-2').textContent ?? '';
    expect(gate).toContain('gate says');
    expect(gate).not.toContain('You ·');
    expect(gate).not.toContain('Agent ·');
  });

  it('renders no composer when the step is not current or not parked on conversation', () => {
    mount(convStep(), {}, false);
    expect(screen.queryByTestId('ini-message')).toBeNull();
    cleanup();
    mount(convStep({ park_kind: 'blocked' }));
    expect(screen.queryByTestId('ini-message')).toBeNull();
  });
});

describe('Conversation forced-start line (story 11.4)', () => {
  const mountForced = (prevLine: string, prevToken: 'SKP' | 'DON' = 'SKP', first = false) => {
    const prev = step('ux', { token: prevToken, line: prevLine });
    const tech = convStep({ id: 'tech' });
    const steps = first ? [tech] : [prev, tech];
    const w = workflow('spec', 1, { steps });
    render(
      createElement(Conversation, {
        detail: detail(),
        workflow: w,
        step: tech,
        isCurrent: false,
        onSelectStep: vi.fn(),
      }),
    );
  };

  it('opens with the mechanism line, before the turns', () => {
    mountForced('skipped, forced · 21:44');
    const line = screen.getAllByRole('status')[0];
    expect(line.textContent).toBe(
      'ux skipped, forced at 21:44 · its files on spec/familio-dessin-v2 are what tech reads',
    );
    const turns = document.querySelector('ol.ini-turns') as HTMLElement;
    expect(line.compareDocumentPosition(turns) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('drops the time when the line has none', () => {
    mountForced('skipped, forced');
    expect(screen.getAllByRole('status')[0].textContent).toBe(
      'ux skipped, forced · its files on spec/familio-dessin-v2 are what tech reads',
    );
  });

  it('renders nothing when the previous step is not SKP or tech is first', () => {
    mountForced('done', 'DON');
    expect(document.body.textContent).not.toContain('skipped, forced');
    cleanup();
    mountForced('skipped, forced · 21:44', 'SKP', true);
    expect(document.body.textContent).not.toContain('skipped, forced');
  });
});

describe('Conversation stops (story 11.5, 2026-11-26)', () => {
  it('AC2: the failed turn is a red line with a log link', () => {
    mount(
      convStep({
        turns: [
          turn(1),
          turn(2, {
            status: 'failed',
            failure_reason: 'stalled: no activity for 30 min',
            attempt_id: 'att-2',
            run_id: 'run-s',
          }),
        ],
      }),
      { attention: 'blocked', reason: '' },
    );
    const line = screen.getByRole('status');
    expect(line.textContent).toBe('turn 2 failed · stalled: no activity for 30 min · log');
    expect(line.getAttribute('data-signal')).toBe('failed');
    expect(within(line).getByText('log').getAttribute('href')).toBe(
      '/api/runs/run-s/attempts/att-2/log',
    );
  });

  it('AC1: the merge step has its own mechanism line and a composer', () => {
    mount(
      convStep({
        kind: 'automatic',
        park_kind: 'merge_conflict',
        turns: [turn(1)],
        run_id: 'run-s',
      } as Partial<Step>),
      { attention: 'your_turn', reason: '' },
    );
    expect(statuses()).toEqual(['your turn · nothing is pushed to main until the agent retries']);
    expect(screen.getByTestId('ini-message')).toBeTruthy();
    expect(document.querySelector('.ini-hint')).toBeNull();
  });

  it('AC7: a gate turn renders as the defects block and the owners line follows', () => {
    const s = step('tech', {
      kind: 'conversation',
      turns: [
        turn(1, {
          author: 'gate',
          defects: 2,
          owner: 'tech',
          message: '1. … 2. …',
          reply: 'Both defects are …',
          started_at: '2026-11-22T22:10:00Z',
        }),
      ],
    } as Partial<Step>);
    const d = detail({ round: 2, owners: ['tech'], attention: 'blocked' } as never);
    const w = workflow('spec', 1, {
      steps: [s, step('gate', { kind: 'automatic', agent: 'delivery-lead' })],
    });
    render(
      createElement(Conversation, {
        detail: d,
        workflow: w,
        step: s,
        isCurrent: true,
        onSelectStep: vi.fn(),
      }),
    );
    const li = screen.getByTestId('ini-turn-1');
    expect(li.querySelector('.ini-defects')).toBeTruthy();
    expect(li.textContent).toContain('2 DEFECTS · OWNER TECH');
    expect(li.textContent).toContain('Gate · delivery-lead · 22:10');
    expect(li.textContent).toContain('1. … 2. …');
    expect(li.textContent).toContain('Both defects are …');
    expect(statuses()).toContain(
      'after this step closes, the gate re-runs · no other step reopens',
    );
  });

  it('AC7: no owners line in round 1', () => {
    mount(convStep({ id: 'tech', turns: [turn(1)] } as Partial<Step>), {
      round: 1,
      owners: ['tech'],
      attention: 'blocked',
    } as never);
    expect(statuses().join()).not.toContain('after this step closes');
  });
});

describe('Conversation fresh-branch line (story 11.6, 2026-11-26)', () => {
  const mountReopened = (reopened_after: unknown) => {
    const tech = convStep({ id: 'tech', turns: [turn(1)], reopened_after } as Partial<Step>);
    render(
      createElement(Conversation, {
        detail: detail(),
        workflow: workflow('spec', 1, { steps: [tech] }),
        step: tech,
        isCurrent: false,
        onSelectStep: vi.fn(),
      }),
    );
  };
  const FRESH = 'on a fresh spec/familio-dessin-v2 from main';

  it('shows before the first turn when the branch was created', () => {
    mountReopened({ workflow: 'build', branch: 'created' });
    const line = screen.getByText(FRESH);
    expect(line.getAttribute('role')).toBe('status');
    expect(
      line.compareDocumentPosition(screen.getByTestId('ini-turn-1')) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('is absent when the branch was attached or there is no reopen', () => {
    mountReopened({ workflow: 'build', branch: 'attached' });
    expect(screen.queryByText(FRESH)).toBeNull();
    cleanup();
    mountReopened(null);
    expect(screen.queryByText(FRESH)).toBeNull();
  });
});
