/** `src/stores/files-focus.ts` — the diagram's *Files* button hands a node path to the files panel. */
import { afterEach, describe, expect, it } from 'vitest';

import { $filesFocus, focusFiles } from '../../src/stores/files-focus';

afterEach(() => $filesFocus.set(null));

describe('files focus store', () => {
  it('starts empty', () => {
    expect($filesFocus.get()).toBeNull();
  });

  it('holds the path focusFiles is given, and a second call replaces it', () => {
    focusFiles('epics[0]');
    expect($filesFocus.get()).toBe('epics[0]');
    focusFiles('epics[0].stories[1]');
    expect($filesFocus.get()).toBe('epics[0].stories[1]');
  });
});
