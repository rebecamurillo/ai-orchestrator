/**
 * The metric catalogue, loaded once per page. Every label, method description, source and
 * missing word a hint shows comes from this response, never from the web client (RM-2).
 */
import { atom } from 'nanostores';

import { api } from '../api/client';
import type { components } from '../api/schema';

type CatalogueEntryOut = components['schemas']['CatalogueEntryOut'];
type CatalogueMethodOut = components['schemas']['CatalogueMethodOut'];

export interface CatalogueState {
  status: 'idle' | 'loading' | 'ready' | 'failed';
  entries: Record<string, CatalogueEntryOut>;
}

const INITIAL: CatalogueState = { status: 'idle', entries: {} };

export const $catalogue = atom<CatalogueState>(INITIAL);

let inflight: Promise<void> | null = null;
let generation = 0;

/** A second call shares the first; after a failure the next call fetches again, once. */
export function loadCatalogue(): Promise<void> {
  if (inflight !== null) return inflight;
  $catalogue.set({ status: 'loading', entries: {} });
  const mine = generation;
  const request = (async () => {
    try {
      const { data } = await api.GET('/metrics/catalogue');
      // a request superseded by resetCatalogue() writes nothing
      if (generation !== mine) return;
      if (!data) throw new Error('catalogue request failed');
      $catalogue.set({
        status: 'ready',
        entries: Object.fromEntries(data.items.map((item) => [item.id, item])),
      });
    } catch {
      if (generation !== mine) return;
      $catalogue.set({ status: 'failed', entries: {} });
      inflight = null;
    }
  })();
  inflight = request;
  return request;
}

/** Test seam and page-navigation reset. */
export function resetCatalogue(): void {
  generation += 1;
  inflight = null;
  $catalogue.set(INITIAL);
}

export function entryOf(id: string): CatalogueEntryOut | null {
  return $catalogue.get().entries[id] ?? null;
}

/** `methodId` is `{metric}@{n}`. */
export function methodOf(entry: CatalogueEntryOut, methodId: string): CatalogueMethodOut | null {
  const n = Number(methodId.slice(methodId.lastIndexOf('@') + 1));
  return entry.methods.find((m) => m.n === n) ?? null;
}
