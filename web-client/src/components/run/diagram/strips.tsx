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
import { DOT_GLYPH, type Guardrail, type RetryChip } from '../../../lib/diagram/run-tree';

/**
 * The deterministic and `checkpoint` rows a card owns, as words with a status dot each.
 * Information only — not clickable, not connected, and deliberately the quietest thing on
 * the card. A truncated strip has already kept every stop in the visible set
 * (`run-tree.ts::truncate`), so `+k` never hides the reason a run is parked.
 */
export function GuardrailStrip({ strip }: { strip: Guardrail | null }) {
  if (strip === null) return null;
  return (
    <div
      className="wf-guardrail"
      data-muted={strip.muted}
      data-testid={`wf-diagram-guardrail-${strip.ownerPath}`}
    >
      {strip.entries.map((entry, index) => (
        <span
          key={entry.path}
          className="wf-guardrail-entry"
          data-testid={`wf-diagram-guardrail-${strip.ownerPath}-${entry.stepId}`}
          title={`${entry.label} · ${entry.word}`}
        >
          {index > 0 ? <span className="wf-guardrail-sep"> · </span> : null}
          <i className="wf-guardrail-dot" data-status={entry.dot} aria-hidden="true">
            {DOT_GLYPH[entry.dot]}
          </i>
          {entry.label}
          <span className="wf-visually-hidden"> {entry.word}</span>
        </span>
      ))}
      {strip.overflow > 0 ? (
        <span className="wf-guardrail-more">
          <span className="wf-guardrail-sep"> · </span>+{strip.overflow}
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
