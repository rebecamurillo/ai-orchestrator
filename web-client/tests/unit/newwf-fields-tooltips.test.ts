/**
 * Tooltips (title=) and mandatory/optional marks on the New Workflow form (story 2-5).
 * Rendered with `renderToStaticMarkup` — same pattern as `newwf-fields.test.ts`.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import NewWorkflowFields from '../../src/components/NewWorkflowFields';
import HarnessList from '../../src/components/HarnessList';
import { defaultFormState, withTemplate } from '../../src/lib/newwf/state';
import type { components } from '../../src/api/schema';

type HarnessOut = components['schemas']['HarnessOut'];

function renderFields(state = defaultFormState()): string {
  return renderToStaticMarkup(
    createElement(NewWorkflowFields, {
      state,
      projects: [],
      repositories: [],
      note: undefined,
      onChange: () => {},
    }),
  );
}

function renderHarness(harnesses: HarnessOut[], selected = ''): string {
  return renderToStaticMarkup(
    createElement(HarnessList, { harnesses, selected, onSelect: () => {} }),
  );
}

function harness(overrides: Partial<HarnessOut> = {}): HarnessOut {
  return {
    name: 'claude',
    enabled: false,
    last_readiness_at: null,
    failing_check: null,
    version_pin: '2.1.258',
    ...overrides,
  };
}

/**
 * Returns the substring of `markup` from the opening of the `<label` that most recently
 * precedes `marker` to its matching `</label>`. Used to check that a `title=` attribute and
 * label text are on the same element.
 */
function labelContaining(markup: string, marker: string): string {
  const idx = markup.indexOf(marker);
  if (idx === -1) throw new Error(`marker not found in markup: ${marker}`);
  const before = markup.lastIndexOf('<label', idx);
  if (before === -1) throw new Error(`no <label before marker: ${marker}`);
  const afterIdx = markup.indexOf('</label>', idx);
  if (afterIdx === -1) throw new Error(`no </label> after marker: ${marker}`);
  return markup.slice(before, afterIdx + '</label>'.length);
}

describe('NewWorkflowFields tooltips and mandatory marks', () => {
  it('TEMPLATE label has a non-empty title= and * mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-template"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('TEMPLATE *');
  });

  it('PROJECT label has a non-empty title= and * mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-project"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('PROJECT *');
  });

  it('REPOSITORY label has a non-empty title= and * mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-repository"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('REPOSITORY *');
  });

  it('BASE BRANCH label has a non-empty title= and * mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-base"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('BASE BRANCH *');
  });

  it('BUDGET label has a non-empty title= and * mark, no (optional)', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-budget"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('BUDGET (USD) *');
    expect(label).not.toContain('(optional)');
  });

  it('MODEL label has a non-empty title= and (optional) mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-model"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('MODEL (optional)');
  });

  it('MANUAL ESTIMATE label has a non-empty title= and (optional) mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-estimate"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain('MANUAL ESTIMATE (H) (optional)');
  });

  it('re-review label has a non-empty title= with no mandatory/optional suffix', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-rereview"');
    expect(label).toMatch(/title="[^"]+"/);
    // boolean toggle: no * or (optional) suffix
    expect(label).not.toContain('(optional)');
  });

  it('initiative template: initiative_folder label has non-empty title= and * mark', () => {
    const markup = renderFields();
    const label = labelContaining(markup, 'data-testid="newwf-input-initiative_folder"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain(' *');
  });

  it('epic template: branch label has non-empty title= and * mark', () => {
    const markup = renderFields(withTemplate(defaultFormState(), 'epic'));
    const label = labelContaining(markup, 'data-testid="newwf-input-branch"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain(' *');
  });

  it('epic template: spec_folder label has non-empty title= and * mark', () => {
    const markup = renderFields(withTemplate(defaultFormState(), 'epic'));
    const label = labelContaining(markup, 'data-testid="newwf-input-spec_folder"');
    expect(label).toMatch(/title="[^"]+"/);
    expect(label).toContain(' *');
  });

  it('no title value contains congratulatory language (NFR-8)', () => {
    const markup = renderFields();
    const titles = [...markup.matchAll(/title="([^"]+)"/g)].map((m) => m[1]);
    for (const t of titles) {
      expect(t, `title="${t}"`).not.toMatch(/please|successfully/i);
    }
  });
});

describe('HarnessList tooltip and legend', () => {
  it('fieldset has a non-empty title= and legend reads HARNESS (optional)', () => {
    const markup = renderHarness([harness()]);
    expect(markup).toContain('HARNESS (optional)');
    expect(markup).toMatch(/<fieldset[^>]*title="[^"]+"/);
  });

  it('no title value contains congratulatory language (NFR-8)', () => {
    const markup = renderHarness([harness()]);
    const titles = [...markup.matchAll(/title="([^"]+)"/g)].map((m) => m[1]);
    for (const t of titles) {
      expect(t, `title="${t}"`).not.toMatch(/please|successfully/i);
    }
  });
});
