// @vitest-environment jsdom
/**
 * Guardrail entries as buttons around the agent (epic 2 story 3, EXPERIENCE § 12 delta 3).
 */
import { readFileSync } from 'node:fs';
import { createElement } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import { GuardrailStrip } from '../../src/components/run/diagram/strips';
import { buildHierarchy, type Guardrail } from '../../src/lib/diagram/run-tree';
import { $stepDrawer } from '../../src/stores/step-drawer';
import { twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';
import { epicOrderGraph, orderSteps, storyOrderGraph } from '../fixtures/run-order';

afterEach(() => {
  cleanup();
  $stepDrawer.set(null);
});

const OPEN = new Set(['epics[0]', 'epics[0].stories[0]']);

function stripOf(graph: ReturnType<typeof storyOrderGraph>, id: string): Guardrail | null {
  return buildHierarchy(graph, orderSteps(graph), OPEN).nodes.find((n) => n.id === id)!.guardrail;
}

function visible(container: HTMLElement): string {
  const clone = container.cloneNode(true) as HTMLElement;
  clone.querySelectorAll('.wf-visually-hidden, [aria-hidden="true"]').forEach((n) => n.remove());
  return clone.textContent!.replace(/\s+/g, ' ').trim();
}

const story = () => stripOf(storyOrderGraph(), 'epics[0].stories[0]');

describe('GuardrailStrip', () => {
  it('reads BEFORE · sync ▸ build ▸ AFTER · verify · commit · push', () => {
    const { container } = render(createElement(GuardrailStrip, { strip: story() }));
    expect(visible(container)).toBe('BEFORE · sync ▸ build ▸ AFTER · verify · commit · push');
  });

  it('reads the epic as BEFORE then AFTER STORIES, with no triangle', () => {
    const { container } = render(
      createElement(GuardrailStrip, { strip: stripOf(epicOrderGraph(), 'epics[0]') }),
    );
    const text = visible(container);
    expect(text).toContain('BEFORE · branch · setup · baseline');
    expect(text).toContain('AFTER STORIES · commit-e2e · e2e · push');
    expect(text).not.toContain('▸');
  });

  it('omits an empty phase and writes +k once at the end', () => {
    const strip = { ...story()!, before: [], agent: null, overflow: 2 };
    const { container } = render(createElement(GuardrailStrip, { strip }));
    expect(visible(container)).toBe('AFTER · verify · commit · push · +2');
    cleanup();
    const noAfter = { ...story()!, after: [], agent: null };
    const r = render(createElement(GuardrailStrip, { strip: noAfter }));
    expect(visible(r.container)).toBe('BEFORE · sync');
    cleanup();
    const both = { ...story()!, agent: null };
    const r2 = render(createElement(GuardrailStrip, { strip: both }));
    expect(visible(r2.container)).toBe('BEFORE · sync · AFTER · verify · commit · push');
  });

  it('draws the unsplit strip with no phase word, and nothing for null', () => {
    const built = buildHierarchy(
      twoEpicGraph(),
      twoEpicSteps(),
      new Set(['epics[0]', 'epics[0].stories[0]']),
    );
    const strip = built.nodes.find((n) => n.id === 'epics[0].stories[0]')!.guardrail;
    const { container } = render(createElement(GuardrailStrip, { strip }));
    const text = visible(container);
    expect(text).not.toMatch(/BEFORE|AFTER|▸/);
    expect(text).toContain('sync');
    cleanup();
    const empty = render(createElement(GuardrailStrip, { strip: null }));
    expect(empty.container.innerHTML).toBe('');
  });

  it('renders every entry as a named button in reading order', () => {
    render(createElement(GuardrailStrip, { strip: story() }));
    const buttons = screen.getAllByRole('button');
    expect(buttons.map((b) => b.textContent!.replace(/^\S\s?/, '').trim())).toEqual([
      'sync done',
      'verify done',
      'commit done',
      'push queued',
    ]);
    for (const b of buttons) {
      expect(b.getAttribute('type')).toBe('button');
      expect(b.className).toContain('wf-guardrail-entry');
      expect(b.className).toContain('nodrag');
      expect(b.id).not.toBe('');
      expect(b.getAttribute('data-testid')).toMatch(/^wf-diagram-guardrail-epics\.0\.stories\.0-/);
    }
  });

  it('opens the drawer on the clicked entry', () => {
    render(createElement(GuardrailStrip, { strip: story() }));
    const push = screen.getAllByRole('button').find((b) => b.textContent!.includes('push'))!;
    fireEvent.click(push);
    expect($stepDrawer.get()).toEqual({ seq: 5, n: 3, openerId: push.id });
  });

  it('marks only the entry whose seq is open', () => {
    render(createElement(GuardrailStrip, { strip: story() }));
    const selected = () =>
      screen
        .getAllByRole('button')
        .filter((b) => b.className.includes('wf-guardrail-entry-selected'))
        .map((b) => b.textContent);
    act(() => $stepDrawer.set({ seq: 3, n: 0, openerId: 'x' }));
    expect(selected()).toHaveLength(1);
    expect(selected()[0]).toContain('verify');
    act(() => $stepDrawer.set({ seq: 4, n: 0, openerId: 'x' }));
    expect(selected()[0]).toContain('commit');
  });

  it('no longer claims the strip is not clickable', () => {
    const src = readFileSync('src/components/run/diagram/strips.tsx', 'utf8');
    expect(src).not.toContain('not clickable, not connected');
    expect(src).toContain('run_order');
  });
});
