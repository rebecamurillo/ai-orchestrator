/** AC9 (epic 2 story 2): the island mounts one `StepDrawer` and labels the STEPS tab. */
import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';

const source = readFileSync(new URL('../../src/islands/RunDetail.tsx', import.meta.url), 'utf8');

describe('RunDetail island', () => {
  it('mounts one StepDrawer with the runId and ids the STEPS tab', () => {
    expect(source.match(/<StepDrawer runId=\{runId\} \/>/g)).toHaveLength(1);
    expect(source).toContain('id="wf-steps-heading"');
  });
});
