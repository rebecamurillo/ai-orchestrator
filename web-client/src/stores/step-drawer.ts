/** The one step drawer on the Run page: which `(seq, n)` is open and the element that opened it. */
import { atom } from 'nanostores';

export interface StepDrawerTarget {
  seq: number;
  n: number;
  openerId: string;
}

export const $stepDrawer = atom<StepDrawerTarget | null>(null);

export function openStepDrawer(seq: number, n: number, openerId: string): void {
  $stepDrawer.set({ seq, n, openerId });
}

export function closeStepDrawer(): void {
  $stepDrawer.set(null);
}
