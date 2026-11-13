import { beforeEach, expect, it } from 'vitest';

import {
  $openHint,
  $originTarget,
  closeHint,
  closeOrigin,
  openHint,
  openOrigin,
} from '../../src/stores/metric-ui';
import { target } from './metrics-fixtures';

beforeEach(() => {
  closeHint();
  closeOrigin();
});

it('keeps one hint open: opening another swaps, closing clears', () => {
  openHint('a');
  expect($openHint.get()).toBe('a');
  openHint('b');
  expect($openHint.get()).toBe('b');
  closeHint();
  expect($openHint.get()).toBeNull();
});

it('opens, swaps and closes the origin drawer target', () => {
  const first = target();
  const second = target({ runLabel: 'Run 8' });
  openOrigin(first);
  expect($originTarget.get()).toBe(first);
  openOrigin(second);
  expect($originTarget.get()).toBe(second);
  closeOrigin();
  expect($originTarget.get()).toBeNull();
});
