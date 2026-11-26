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
    expect(statuses()).toEqual([]);
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
