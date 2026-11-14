// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import HintControl from '../../src/components/metrics/HintControl';
import { $catalogue, resetCatalogue } from '../../src/stores/catalogue';
import { $openHint, closeHint, openHint } from '../../src/stores/metric-ui';
import { entry } from './metrics-fixtures';

beforeEach(() => {
  $catalogue.set({
    status: 'ready',
    entries: { 'cost.total': entry('cost.total'), 'cost.other': entry('cost.other') },
  });
});

afterEach(() => {
  cleanup();
  closeHint();
  resetCatalogue();
});

const NAME = 'how label of cost.total is calculated';
const button = () => screen.getByRole('button', { name: NAME });

describe('opening', () => {
  it('is a typed button named from the catalogue label', () => {
    render(createElement(HintControl, { metricId: 'cost.total' }));
    expect(button().getAttribute('type')).toBe('button');
  });

  it('does not open on hover', () => {
    render(createElement(HintControl, { metricId: 'cost.total' }));
    fireEvent.mouseEnter(button());
    fireEvent.mouseOver(button());
    fireEvent.pointerEnter(button());
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it.each([
    ['click', (b: HTMLElement) => fireEvent.click(b)],
    [
      'Enter',
      (b: HTMLElement) => {
        // a native button turns Enter and Space into a click; jsdom does not, so both are dispatched
        fireEvent.keyDown(b, { key: 'Enter' });
        fireEvent.click(b);
      },
    ],
    [
      'Space',
      (b: HTMLElement) => {
        fireEvent.keyDown(b, { key: ' ' });
        fireEvent.click(b);
      },
    ],
  ])('opens a non-modal dialog with focus inside on %s', (_name, act) => {
    render(createElement(HintControl, { metricId: 'cost.total' }));
    act(button());
    const dialog = screen.getByRole('dialog');
    expect(dialog.getAttribute('aria-modal')).toBeNull();
    expect(document.activeElement).toBe(dialog);
  });
});

describe('closing', () => {
  it('closes on Escape and returns focus to the control', () => {
    render(createElement(HintControl, { metricId: 'cost.total' }));
    fireEvent.click(button());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    expect(document.activeElement).toBe(button());
  });

  it('closes on a second click', () => {
    render(createElement(HintControl, { metricId: 'cost.total' }));
    fireEvent.click(button());
    fireEvent.click(button());
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('ignores other keys and Escape while closed', () => {
    render(createElement(HintControl, { metricId: 'cost.total' }));
    fireEvent.keyDown(button(), { key: 'Escape' });
    fireEvent.click(button());
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'a' });
    expect(screen.getByRole('dialog')).toBeTruthy();
  });

  it('keeps one hint open: opening a second closes the first', () => {
    render(
      createElement(
        'div',
        null,
        createElement(HintControl, { metricId: 'cost.total' }),
        createElement(HintControl, { metricId: 'cost.other' }),
      ),
    );
    fireEvent.click(button());
    fireEvent.click(screen.getByRole('button', { name: 'how label of cost.other is calculated' }));
    const dialogs = screen.getAllByRole('dialog');
    expect(dialogs).toHaveLength(1);
    expect(dialogs[0]!.getAttribute('aria-label')).toBe('how label of cost.other is calculated');
  });
});

describe('unmounting', () => {
  it('clears its open hint when the control unmounts, and leaves another open hint alone', () => {
    const { unmount } = render(createElement(HintControl, { metricId: 'cost.total' }));
    fireEvent.click(button());
    expect($openHint.get()).not.toBeNull();
    unmount();
    expect($openHint.get()).toBeNull();

    const other = render(createElement(HintControl, { metricId: 'cost.total' }));
    openHint('another-control');
    other.unmount();
    expect($openHint.get()).toBe('another-control');
  });
});

describe('content and absence', () => {
  it('shows the label when asked and the catalogue rows when open', () => {
    render(createElement(HintControl, { metricId: 'cost.total', showLabel: true }));
    expect(screen.getByText('label of cost.total', { selector: '.metric-label' })).toBeTruthy();
    fireEvent.click(button());
    expect(screen.getByText('source of cost.total')).toBeTruthy();
  });

  it('renders neither label nor control for a metric with no catalogue entry', () => {
    const markup = renderToStaticMarkup(
      createElement(HintControl, { metricId: 'unknown.metric', showLabel: true }),
    );
    expect(markup).toBe('');
  });
});
