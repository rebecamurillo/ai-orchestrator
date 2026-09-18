/**
 * Unit test pair for `src/components/run/DiagramSection.tsx` (story 1-4).
 * check-test-pairs.mjs requires at least one test file that names the module.
 *
 * Written first (TDD, AD-18): must fail before DiagramSection.tsx exists.
 */
import { describe, expect, it } from 'vitest';

import DiagramSection from '../../src/components/run/DiagramSection';

describe('DiagramSection', () => {
  it('is a function component', () => {
    expect(typeof DiagramSection).toBe('function');
  });
});
