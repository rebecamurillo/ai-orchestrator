/**
 * The two quiet things on the v3 diagram: the guardrail strip at the foot of a card, and the
 * retry chips in the attempts gutter beside one.
 *
 * Split out of `nodes.tsx` so both stay under the 300-line component limit; neither touches
 * React Flow, so both render under `renderToStaticMarkup` in the `environment: 'node'` suite.
 *
 * **Colour is never the only carrier, and neither is a CSS separator.** The strip used to
 * join its entries with a `::before` `·`, which is invisible to an assistive technology — the
 * accessible name read `syncverifycommit-guard`. The separator is markup now, and each entry
 * carries its status word, visually hidden but spoken: `sync done · verify queued`.
 *
 * The dot is a **glyph**, one shape per state (`run-tree.ts::DOT_GLYPH`), not a square that
 * differs only in hue: a sighted operator who cannot separate the hues had nothing but a 4px
 * colour, and `title` needs a hover. The word does not fit beside four entries on a 228px
 * story card, so the shape carries it on screen and the word carries it in the accessible
 * name.
 */
import { Fragment } from 'react';
import { useStore } from '@nanostores/react';
import {
  DOT_GLYPH,
  type Guardrail,
  type GuardrailEntry,
  type RetryChip,
} from '../../../lib/diagram/run-tree';
import { $stepDrawer, openStepDrawer } from '../../../stores/step-drawer';

const SEP = <span className="wf-guardrail-sep"> · </span>;

function Entry({ entry, ownerPath }: { entry: GuardrailEntry; ownerPath: string }) {
  const open = useStore($stepDrawer);
  const id = `wf-guardrail-${ownerPath}-${entry.stepId}`;
  const selected = open?.seq === entry.seq;
  return (
    <button
      type="button"
      className={`wf-guardrail-entry nodrag${selected ? ' wf-guardrail-entry-selected' : ''}`}
      id={id}
      data-testid={`wf-diagram-guardrail-${ownerPath}-${entry.stepId}`}
      title={`${entry.label} · ${entry.word}`}
      data-selected={selected || undefined}
      onClick={() => openStepDrawer(entry.seq, entry.n, id)}
    >
      <i className="wf-guardrail-dot" data-status={entry.dot} aria-hidden="true">
        {DOT_GLYPH[entry.dot]}
      </i>
      {entry.label}
      <span className="wf-visually-hidden"> {entry.word}</span>
    </button>
  );
}

function entryList(entries: GuardrailEntry[], ownerPath: string) {
  return entries.map((entry, index) => (
    <Fragment key={entry.path}>
      {index > 0 ? SEP : null}
      <Entry entry={entry} ownerPath={ownerPath} />
    </Fragment>
  ));
}

/**
 * The deterministic and `checkpoint` rows a card owns, as words with a status dot each,
 * the quietest thing on the card. The graph's `run_order` splits them around the agent:
 * `BEFORE · … ▸ agent ▸ AFTER · …` (`AFTER STORIES` on an epic); a card with no `run_order`
 * entry lists its entries in plan order with no phase word. Each entry is a button that
 * opens the step drawer, and Tab order is reading order. A truncated strip has already kept
 * every stop in the visible set (`run-tree.ts::truncate`), so `+k` never hides the reason a
 * run is parked.
 */
export function GuardrailStrip({ strip }: { strip: Guardrail | null }) {
  if (strip === null) return null;
  const { ownerPath, before, after } = strip;
  const split = before.length > 0 || after.length > 0;
  return (
    <div
      className="wf-guardrail"
      data-muted={strip.muted}
      data-testid={`wf-diagram-guardrail-${ownerPath}`}
    >
      {split ? (
        <>
          {before.length > 0 ? (
            <>
              <span className="wf-guardrail-lab">BEFORE</span>
              {SEP}
              {entryList(before, ownerPath)}
            </>
          ) : null}
          {strip.agent !== null ? (
            <span className="wf-guardrail-agent"> ▸ {strip.agent} ▸ </span>
          ) : before.length > 0 && after.length > 0 ? (
            SEP
          ) : null}
          {after.length > 0 ? (
            <>
              <span className="wf-guardrail-lab">{strip.afterLabel}</span>
              {SEP}
              {entryList(after, ownerPath)}
            </>
          ) : null}
        </>
      ) : (
        entryList(strip.entries, ownerPath)
      )}
      {strip.overflow > 0 ? (
        <span className="wf-guardrail-more">
          {SEP}+{strip.overflow}
        </span>
      ) : null}
    </div>
  );
}

/**
 * One failed attempt, in the gutter: `try n` over `failed`, with the exit code when the wire
 * carries one — only the latest failed attempt's is on it.
 */
export function RetryCard({ chip, ownerPath }: { chip: RetryChip; ownerPath: string }) {
  return (
    <div
      className="wf-retry"
      data-testid={`wf-diagram-retry-${ownerPath}-${chip.n}`}
      role="group"
      aria-label={`${chip.label} · failed${chip.exitCode === null ? '' : ` · exit ${chip.exitCode}`}`}
    >
      <span className="wf-retry-try">{chip.label}</span>
      <span className="wf-retry-outcome">
        <em className="wf-retry-failed">failed</em>
        {chip.exitCode === null ? '' : ` exit ${chip.exitCode}`}
      </span>
    </div>
  );
}

/**
 * The chip standing for the failures the gutter did not draw. A run that retried thirty
 * times would otherwise paper the canvas with identical red rectangles and say no more than
 * this one does.
 */
export function RetryMoreCard({ overflow, ownerPath }: { overflow: number; ownerPath: string }) {
  return (
    <div
      className="wf-retry"
      data-testid={`wf-diagram-retry-${ownerPath}-more`}
      role="group"
      aria-label={`${overflow} more failed attempts`}
    >
      <span className="wf-retry-try">+{overflow}</span>
      <span className="wf-retry-outcome">
        <em className="wf-retry-failed">failed</em>
      </span>
    </div>
  );
}
