/**
 * `src/stores/template-validation.ts` — the channel between the two islands (3.6).
 *
 * `TemplateEditor` and the diagram sit in two different grid cells of the Templates screen,
 * so they cannot share React state; `web-client/AGENTS.md` names nanostores as this
 * component's cross-island mechanism, and a store is testable in `environment: 'node'` where
 * a DOM `CustomEvent` is not.
 *
 * The monotonic `seq` is the part worth proving: two validations of identical text have to be
 * distinguishable, or re-validating unchanged text after a failure would publish a value
 * `useStore` treats as unchanged and the stale line would never clear.
 */
import { beforeEach, describe, expect, it } from 'vitest';

import {
  $templateValidation,
  publishValidation,
  resetTemplateValidation,
} from '../../src/stores/template-validation';

beforeEach(() => {
  resetTemplateValidation();
});

describe('the template validation store', () => {
  it('starts empty, so a diagram mounted before any Validate draws its own initial graph', () => {
    expect($templateValidation.get()).toBeNull();
  });

  it('publishes the validated text and whether it validated', () => {
    publishValidation({ yaml: 'name: demo\n', ok: true });

    expect($templateValidation.get()).toEqual({ seq: 1, yaml: 'name: demo\n', ok: true });
  });

  it('counts up, so two identical outcomes are two distinguishable values', () => {
    const first = publishValidation({ yaml: 'same', ok: false });
    const second = publishValidation({ yaml: 'same', ok: false });

    expect(first.seq).toBe(1);
    expect(second.seq).toBe(2);
    expect(second).not.toBe(first);
    expect($templateValidation.get()).toBe(second);
  });

  it('keeps counting across a failed and a successful outcome alike', () => {
    publishValidation({ yaml: 'a', ok: false });
    publishValidation({ yaml: 'b', ok: true });

    expect($templateValidation.get()).toEqual({ seq: 2, yaml: 'b', ok: true });
  });

  it('notifies a subscriber with each outcome as it is published', () => {
    const seen: (number | null)[] = [];
    const unsubscribe = $templateValidation.subscribe((value) => seen.push(value?.seq ?? null));

    publishValidation({ yaml: 'a', ok: true });
    publishValidation({ yaml: 'a', ok: true });
    unsubscribe();

    expect(seen).toEqual([null, 1, 2]);
  });

  it('resets to empty, and starts counting again', () => {
    publishValidation({ yaml: 'a', ok: true });

    resetTemplateValidation();

    expect($templateValidation.get()).toBeNull();
    expect(publishValidation({ yaml: 'b', ok: true }).seq).toBe(1);
  });
});
