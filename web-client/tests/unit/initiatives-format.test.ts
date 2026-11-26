import { describe, expect, it } from 'vitest';

import {
  ageSecondsSince,
  cancelledHiddenText,
  columnCountText,
  columnHeadName,
  columnTypeWord,
  footWord,
  hasRunning,
  initiativesRequestPath,
  placeItems,
  readoutText,
  statusToken,
} from '../../src/lib/initiatives/format';

const NOW = Date.parse('2026-11-26T12:00:00Z');
const hoursAgo = (h: number) => new Date(NOW - h * 3600_000).toISOString();

const row = (workflow: string, status: string, id = workflow + status) =>
  ({ id, workflow, status }) as never;

describe('statusToken', () => {
  it.each([
    ['running', 'RUN', 'running'],
    ['waiting for her', 'BLK', 'needs you'],
    ['done', 'DON', 'done'],
    ['failed', 'ERR', 'failed'],
    ['cancelled', 'CAN', 'cancelled'],
  ] as const)('%s', (status, token, word) => {
    expect(statusToken(status)).toEqual({ token, word });
  });
});

describe('readoutText (AC9)', () => {
  it('shows need you and the wait', () => {
    expect(
      readoutText({ ongoing: 3, need_you: 1, cancelled: 0, oldest_wait_at: hoursAgo(2) }, NOW),
    ).toBe('3 ongoing · 1 need you · oldest wait 2h 00m');
  });
  it('drops both parts', () => {
    expect(readoutText({ ongoing: 3, need_you: 0, cancelled: 0, oldest_wait_at: null }, NOW)).toBe(
      '3 ongoing',
    );
  });
});

it('ageSecondsSince', () => {
  expect(ageSecondsSince(hoursAgo(1), NOW)).toBe(3600);
});

describe('column words', () => {
  it('head and type', () => {
    expect(columnHeadName('spec')).toBe('SPEC');
    expect(columnTypeWord('interactive')).toBe('INTERACTIVE');
    expect(columnTypeWord('auto')).toBe('AUTO');
    expect(columnTypeWord('anything')).toBe('AUTO');
  });
  it('count line', () => {
    expect(columnCountText(3, 0)).toEqual({ ongoing: '3 ongoing', needYou: null });
    expect(columnCountText(3, 2)).toEqual({ ongoing: '3 ongoing', needYou: '2 need you' });
  });
  it('cancelled text', () => {
    expect(cancelledHiddenText(2)).toBe('2 cancelled, hidden · show');
  });
});

describe('placeItems', () => {
  const columns = [
    { workflow: 'spec', type: 'interactive' },
    { workflow: 'build', type: 'auto' },
    { workflow: 'deploy', type: 'auto' },
  ];
  it('routes by workflow and status', () => {
    const a = row('spec', 'waiting for her');
    const b = row('build', 'running');
    const c = row('build', 'done');
    const d = row('spec', 'cancelled');
    const e = row('ghost', 'running');
    const p = placeItems(columns, [a, b, c, d, e]);
    expect(p.byColumn.get('spec')).toEqual([a]);
    expect(p.byColumn.get('build')).toEqual([b]);
    expect(p.byColumn.get('deploy')).toEqual([]);
    expect(p.done).toEqual([c]);
    expect(p.cancelled).toEqual([d]);
  });
});

it('footWord', () => {
  expect(footWord({ workflow: 'spec', type: 'a', state: 'completed' })).toBe('spec · completed');
  expect(footWord({ workflow: 'build', type: 'a', state: 'ongoing' })).toBe('build · ongoing');
  expect(footWord({ workflow: 'deploy', type: 'a', state: null })).toBe('deploy');
});

it('initiativesRequestPath', () => {
  expect(initiativesRequestPath('ongoing', null)).toBe('/api/initiatives?filter=ongoing');
  expect(initiativesRequestPath('all', 'p 1')).toBe('/api/initiatives?filter=all&project_id=p%201');
});

it('hasRunning', () => {
  expect(hasRunning([row('a', 'done')])).toBe(false);
  expect(hasRunning([row('a', 'running')])).toBe(true);
});
