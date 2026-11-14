// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import HistoryTable from '../../src/components/runs/HistoryTable';
import type { HistoryRowOut } from '../../src/lib/runs/history';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { closeHint } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';

const row = {
  attempt_id: 'a1',
  run_id: 'r1',
  seq: 1,
  started_at: '2026-09-09T08:04:05Z',
  ended_at: '2026-09-09T08:06:35Z',
  seconds: 150,
  project_name: 'acme',
  run_label: 'x',
  path: 'build',
  kind: 'agent',
  harness: 'codex',
  model: 'm',
  session_id: null,
  status: 'done',
  token: 'DON',
  tokens_in: 1,
  tokens_out: 2,
  cost_usd: '0.250000',
  cost_provisional: false,
  trace_url: null,
  log_tail_url: '/x',
} as HistoryRowOut;

const NAME = 'how recorded spend is calculated';

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: { 'spend.recorded': entry('spend.recorded', { label: 'recorded spend' }) },
  });
  render(createElement(HistoryTable, { rows: [row] }));
});
afterEach(() => {
  cleanup();
  closeHint();
  resetCatalogue();
});

describe('HistoryTable cost head hint', () => {
  it('opens on click, Enter and Space, never on hover', () => {
    const button = screen.getByRole('button', { name: NAME });
    fireEvent.mouseEnter(button);
    fireEvent.pointerOver(button);
    expect(screen.queryByText('how spend.recorded v2')).toBeNull();
    fireEvent.click(button);
    expect(screen.getByText('how spend.recorded v2')).toBeTruthy();
    fireEvent.click(button);
    expect(screen.queryByText('how spend.recorded v2')).toBeNull();
    fireEvent.keyDown(button, { key: 'Enter' });
    fireEvent.click(button);
    expect(button.getAttribute('aria-expanded')).toBe('true');
  });

  it('leaves the cell and the other heads untouched', () => {
    expect(screen.getByText('$0.250000').querySelector('button')).toBeNull();
    expect(screen.getAllByRole('button', { name: /is calculated/ })).toHaveLength(1);
    const head = screen.getByRole('columnheader', { name: /^cost/ });
    expect(head.textContent).toContain('cost');
  });
});
