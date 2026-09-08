/**
 * `RunCard.tsx` reads `card.kind_label` generically (4.14) — the frozen `run-card.test.ts`
 * proves it for `repo-init` only. This story's own binding rule ("`readiness`/`repo-init`
 * Runs show that word in place of progress — 4.14 already reads `kind_label`; verify") is
 * verified here for `readiness` specifically, since the backend's `_KIND_LABELS` map (SPEC
 * CAP-12) has carried `"readiness": "readiness"` since before this story and nothing in
 * `RunCard.tsx` special-cases either string.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import RunCard from '../../src/components/RunCard';
import type { components } from '../../src/api/schema';

type CardOut = components['schemas']['CardOut'];

function card(overrides: Partial<CardOut> = {}): CardOut {
  return {
    id: '1',
    token: 'RUN',
    status: 'running',
    park_kind: null,
    branch: 'epics/1',
    project_name: 'Acme',
    repository_slug: 'acme-app',
    current_step_label: 'checkout',
    harness: 'claude',
    template: 'readiness',
    version: 1,
    progress: null,
    kind_label: null,
    age_seconds: 30,
    needs_you_since: null,
    ...overrides,
  };
}

describe('RunCard · readiness kind_label', () => {
  it('shows readiness in place of progress', () => {
    const html = renderToStaticMarkup(
      createElement(RunCard, { card: card({ progress: null, kind_label: 'readiness' }) }),
    );

    expect(html).toContain('readiness');
  });
});
