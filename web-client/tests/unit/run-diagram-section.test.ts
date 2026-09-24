/**
 * `src/components/run/DiagramSection.tsx` — the embedded run diagram's fetch, state and
 * surrounds (v3, 2026-09-24).
 *
 * The section opens a network call, subscribes to `$poll` and mounts React Flow, so it is
 * the Playwright suite that renders it: `tests/e2e/run-diagram.spec.ts` covers the tree, the
 * guardrails, the retry chips, the click grammar and the poll-under-a-drag case, and
 * `run-diagram-error.spec.ts` covers the failed `/graph` fetch and its retry control.
 *
 * What is asserted here is what a DOM would not add: that the module exports the component
 * the Run detail mounts, and that the words it puts on screen for an empty plan are the
 * words the spine names (EXPERIENCE-v1 §2.2 *States*: "Empty plan — the words `no steps
 * planned`, no canvas").
 */
import { describe, expect, it } from 'vitest';

import DiagramSection, { EMPTY_PLAN_TEXT } from '../../src/components/run/DiagramSection';
import { flowLayout } from '../../src/lib/diagram/flow-layout';
import { buildHierarchy } from '../../src/lib/diagram/run-tree';

describe('DiagramSection', () => {
  it('is the component RunDetail mounts', () => {
    expect(typeof DiagramSection).toBe('function');
  });

  it('says `no steps planned` for a plan with no rows, and draws no canvas', () => {
    const layout = flowLayout(buildHierarchy({ nodes: [], edges: [], groups: [] }, [], new Set()));

    expect(EMPTY_PLAN_TEXT).toBe('no steps planned');
    expect(layout.nodes).toEqual([]);
  });
});
