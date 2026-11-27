// @vitest-environment jsdom
/** Story 11.1: WorkflowTrack (AC3). */
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import WorkflowTrack from '../../src/components/initiative/WorkflowTrack';
import { detail, workflow } from './initiative-fixtures';

afterEach(cleanup);

const mount = (
  over: { showNow?: boolean; selected?: number | null; onSelect?: () => void } = {},
) => {
  const d = detail();
  return render(
    createElement(WorkflowTrack, {
      workflows: d.workflows,
      currentPosition: 1,
      showNow: over.showNow ?? true,
      selected: over.selected ?? 1,
      onSelect: over.onSelect ?? (() => {}),
    }),
  );
};

describe('WorkflowTrack', () => {
  it('renders the label, count and one button cell per workflow', () => {
    mount();
    const track = screen.getByTestId('ini-workflows');
    expect(track.textContent).toContain('WORKFLOWS · ONE AFTER ANOTHER');
    expect(track.textContent).toContain('2 workflows');
    expect(screen.getByTestId('ini-workflow-spec').tagName).toBe('BUTTON');
    expect(screen.getByTestId('ini-workflow-build').tagName).toBe('BUTTON');
    expect(track.querySelectorAll('[aria-hidden="true"]')).toHaveLength(1);
    expect(track.textContent).toContain('▸');
  });

  it('shows eyebrows, micro text, token and line, with NOW on the current cell only', () => {
    mount();
    const spec = screen.getByTestId('ini-workflow-spec').textContent ?? '';
    const build = screen.getByTestId('ini-workflow-build').textContent ?? '';
    expect(spec).toContain('WORKFLOW 1 · INTERACTIVE');
    expect(spec).toContain('NOW');
    expect(spec).toContain('spec-flow@3 · 6 steps');
    expect(spec).toContain('RUN');
    expect(spec).toContain('ux · your turn');
    expect(build).toContain('WORKFLOW 2 · AUTO');
    expect(build).not.toContain('NOW');
    expect(build).toContain('build-flow@3');
    expect(build).not.toContain('steps');
    expect(build).toContain('waits for spec');
  });

  it('carries no NOW when the initiative is done or cancelled', () => {
    mount({ showNow: false });
    expect(screen.getByTestId('ini-workflows').textContent).not.toContain('NOW');
  });

  it('puts the amber rule on a BLK cell only and marks the selected one', () => {
    const d = detail({
      workflows: [workflow('spec', 1, { token: 'BLK' }), workflow('build', 2, { token: 'QUE' })],
    });
    render(
      createElement(WorkflowTrack, {
        workflows: d.workflows,
        currentPosition: 1,
        showNow: true,
        selected: 2,
        onSelect: () => {},
      }),
    );
    expect(screen.getByTestId('ini-workflow-spec').getAttribute('data-left-rule')).toBe(
      'needs-you',
    );
    expect(screen.getByTestId('ini-workflow-build').getAttribute('data-left-rule')).toBeNull();
    expect(screen.getByTestId('ini-workflow-build').getAttribute('aria-pressed')).toBe('true');
    expect(screen.getByTestId('ini-workflow-spec').getAttribute('aria-pressed')).toBe('false');
  });

  it('selects a workflow by position on click', () => {
    const onSelect = vi.fn();
    mount({ onSelect });
    fireEvent.click(screen.getByTestId('ini-workflow-build'));
    expect(onSelect).toHaveBeenCalledWith(2);
  });
});
