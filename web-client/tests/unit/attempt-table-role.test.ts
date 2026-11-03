/**
 * `AttemptsTable.tsx` (story 1-7, spine AD-21, ratified 2026-11-01): the `#` cell names an
 * attempt that is not the agent's own. `consult` reads `{n} · senior`, `session` reads
 * `{n} · session`, and an `agent` attempt, with or without `role`, reads `{n}`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import AttemptsTable, { type AttemptDetail } from '../../src/components/run/AttemptsTable';

function attempt(over: Partial<AttemptDetail> = {}): AttemptDetail {
  return {
    id: 'a1',
    n: 1,
    status: 'done',
    token: 'DON',
    started_at: null,
    ended_at: null,
    seconds: null,
    harness: null,
    model: null,
    session_id: null,
    exit_code: null,
    cost_usd: null,
    cost_provisional: false,
    tokens_in: null,
    tokens_out: null,
    dispatch_prompt: null,
    retry_prompt: null,
    result: null,
    command: null,
    resume_command: null,
    session_lifetime_ends_at: null,
    ...over,
  };
}

function render(over: Partial<AttemptDetail>): string {
  return renderToStaticMarkup(
    createElement(AttemptsTable, {
      attempts: [attempt(over)],
      selectedN: null,
      onSelect: () => {},
      onDrawer: () => {},
    }),
  );
}

function firstCell(over: Partial<AttemptDetail>): string {
  const match = /<tbody><tr[^>]*><td>(.*?)<\/td>/.exec(render(over));
  return match?.[1] ?? '';
}

describe('AttemptsTable — attempt role in the # cell', () => {
  it('reads the bare number for an agent attempt that omits role', () => {
    expect(firstCell({ n: 2 })).toBe('2');
  });

  it('reads the bare number for an agent attempt that states its role', () => {
    expect(firstCell({ n: 2, role: 'agent' })).toBe('2');
  });

  it('reads "· senior" for a consult attempt', () => {
    expect(firstCell({ n: 3, role: 'consult' })).toBe('3 · senior');
  });

  it('reads "· session" for an Operator session attempt', () => {
    expect(firstCell({ n: 4, role: 'session' })).toBe('4 · session');
  });

  it('keeps the eight columns whatever the role', () => {
    expect(render({ role: 'consult' }).match(/<th /g)).toHaveLength(8);
  });
});
