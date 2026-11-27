// @vitest-environment jsdom
/** Story 11.1: StepsStrip (AC4). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import StepsStrip from '../../src/components/initiative/StepsStrip';
import { detail, step } from './initiative-fixtures';

afterEach(cleanup);

const mount = (over: { current?: string | null; onSelect?: (id: string) => void } = {}) => {
  const d = detail();
  return render(
    createElement(StepsStrip, {
      workflow: d.workflows[0],
      currentStepId: over.current === undefined ? 'ux' : over.current,
      selectedStepId: 'ux',
      onSelect: over.onSelect ?? (() => {}),
      forceStepId: null,
      onForce: vi.fn(),
    }),
  );
};

describe('StepsStrip', () => {
  it('is an ordered list of six buttons under the label', () => {
    mount();
    const strip = screen.getByTestId('ini-steps');
    expect(strip.textContent).toContain('STEPS OF SPEC');
    expect(strip.textContent).toContain('6 steps');
    const list = strip.querySelector('ol');
    expect(list).not.toBeNull();
    expect(list?.querySelectorAll('li > button')).toHaveLength(6);
  });

  it('marks the current step and announces it', () => {
    mount();
    const ux = screen.getByTestId('ini-step-ux');
    expect(ux.getAttribute('aria-current')).toBe('step');
    expect(ux.getAttribute('aria-label')).toBe('3 ux, running, your turn · 14 turns');
    expect(ux.textContent).toContain('1.3 · CONVERSATION');
    expect(ux.textContent).toContain('NOW');
    expect(ux.getAttribute('data-selected')).toBe('true');
    expect(screen.getByTestId('ini-step-arch').getAttribute('aria-current')).toBeNull();
    expect(screen.getByTestId('ini-step-arch').textContent).not.toContain('NOW');
  });

  it('has no current step in a workflow that is not the current one', () => {
    mount({ current: null });
    expect(screen.getByTestId('ini-step-ux').getAttribute('aria-current')).toBeNull();
    expect(screen.getByTestId('ini-steps').textContent).not.toContain('NOW');
  });

  it('strikes a skipped step through and rules a blocked one', () => {
    const d = detail();
    const steps = [
      step('a', { token: 'SKP', status: 'skipped' }),
      step('b', { token: 'BLK', status: 'waiting for her', line: 'needs a decision' }),
      step('c', { kind: 'automatic', token: 'QUE', line: 'to come', agent: 'verify' }),
    ];
    render(
      createElement(StepsStrip, {
        workflow: { ...d.workflows[0], steps },
        currentStepId: 'b',
        selectedStepId: null,
        onSelect: () => {},
        forceStepId: null,
        onForce: vi.fn(),
      }),
    );
    expect(screen.getByTestId('ini-step-a').querySelector('s')?.textContent).toBe('a');
    expect(screen.getByTestId('ini-step-b').getAttribute('data-left-rule')).toBe('needs-you');
    expect(screen.getByTestId('ini-step-b').getAttribute('aria-label')).toBe(
      '2 b, needs you, needs a decision',
    );
    expect(screen.getByTestId('ini-step-c').textContent).toContain('1.3 · AUTOMATIC');
    expect(screen.getByTestId('ini-step-c').querySelector('s')).toBeNull();
  });

  it('selects a step by id on click', () => {
    const onSelect = vi.fn();
    mount({ onSelect });
    fireEvent.click(screen.getByTestId('ini-step-product'));
    expect(onSelect).toHaveBeenCalledWith('product');
  });
});

describe('StepsStrip Start now (story 11.4)', () => {
  const mountForce = (forceStepId: string | null, onForce = vi.fn()) => {
    const d = detail();
    render(
      createElement(StepsStrip, {
        workflow: d.workflows[0],
        currentStepId: 'ux',
        selectedStepId: 'ux',
        onSelect: () => {},
        forceStepId,
        onForce,
      }),
    );
    return onForce;
  };

  it('renders one action beside, not inside, the cell button and calls onForce', () => {
    const onForce = mountForce('plan');
    const actions = document.querySelectorAll('[data-testid^="ini-force-"]');
    expect(actions).toHaveLength(1);
    const action = screen.getByTestId('ini-force-plan');
    expect(action.tagName).toBe('BUTTON');
    expect(action.textContent).toBe('Start now');
    expect(action.closest('[data-testid="ini-step-plan"]')).toBeNull();
    expect(action.closest('li')).toBe(screen.getByTestId('ini-step-plan').closest('li'));
    fireEvent.click(action);
    expect(onForce).toHaveBeenCalledWith('plan');
  });

  it('renders none without a forceStepId', () => {
    mountForce(null);
    expect(document.querySelectorAll('[data-testid^="ini-force-"]')).toHaveLength(0);
  });
});
