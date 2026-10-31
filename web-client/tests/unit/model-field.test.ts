/**
 * `ModelField.tsx` — the one select/input pair behind MODEL and every model-named Template
 * input (spec-model-input-selectors, 2026-10-30).
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import ModelField from '../../src/components/ModelField';

function render(models: string[], value = '', placeholder?: string): string {
  return renderToStaticMarkup(
    createElement(ModelField, { testId: 't', value, models, placeholder, onChange: () => {} }),
  );
}

describe('ModelField', () => {
  it('is a select with a blank — option and one option per model when a list exists', () => {
    const markup = render(['a', 'b'], 'b');
    expect(markup).toContain('<select');
    expect(markup).toContain('<option value="">—</option>');
    expect(markup).toContain('<option value="a">a</option>');
    expect(markup).toContain('<option value="b" selected="">b</option>');
  });

  it('is a free-text input with the placeholder when the list is empty', () => {
    const markup = render([], 'typed', 'harness default');
    expect(markup).toContain('<input');
    expect(markup).not.toContain('<select');
    expect(markup).toContain('placeholder="harness default"');
    expect(markup).toContain('value="typed"');
  });

  it('omits the placeholder when none is given', () => {
    expect(render([])).not.toContain('placeholder');
  });

  it.each([[['a']], [[]]])('reports the new value for models %j', (models) => {
    const seen: string[] = [];
    const element = ModelField({ testId: 't', value: '', models, onChange: (v) => seen.push(v) });
    (element.props as { onChange: (e: { target: { value: string } }) => void }).onChange({
      target: { value: 'a' },
    });
    expect(seen).toEqual(['a']);
  });
});
