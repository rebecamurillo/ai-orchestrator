import { afterEach, describe, expect, it } from 'vitest';

import { $stepDrawer, closeStepDrawer, openStepDrawer } from '../../src/stores/step-drawer';

afterEach(() => $stepDrawer.set(null));

describe('step drawer store', () => {
  it('opens on a (seq, n) with its opener, closes to null, and a second open replaces the first', () => {
    openStepDrawer(13, 2, 'x');
    expect($stepDrawer.get()).toEqual({ seq: 13, n: 2, openerId: 'x' });
    openStepDrawer(14, 0, 'y');
    expect($stepDrawer.get()).toEqual({ seq: 14, n: 0, openerId: 'y' });
    closeStepDrawer();
    expect($stepDrawer.get()).toBeNull();
  });
});
