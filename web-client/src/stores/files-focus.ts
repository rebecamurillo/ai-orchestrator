/** The diagram's *Files* button hands a node path (`epics[0]`, `epics[0].stories[1]`) to the files panel. */
import { atom } from 'nanostores';

export const $filesFocus = atom<string | null>(null);

export function focusFiles(path: string): void {
  $filesFocus.set(path);
}
