/**
 * Bracket↔dot-index bijection for step paths (story 1-2, AD-15).
 *
 * A step path uses bracket notation for array indices: `epics[0].stories[3].build`.
 * Astro's catch-all route parameter (`[...path]`) and URL path segments cannot safely
 * carry literal `[` / `]`, so the web-client converts them to dot-index form for URLs
 * and Astro params, then converts back to bracket form before calling the API.
 *
 * AD-15 guarantees no step `id` is all-digits, making the mapping injective:
 * - `encode`: `[n]` → `.n`  (regex `\[(\d+)\]` → `.$1`)
 * - `decode`: `.n` where `n` is a pure-digit segment → `[n]`  (regex `\.(\d+)` → `[$1]`)
 *
 * Root-only paths (e.g. `plan`) carry no brackets and map to themselves under both
 * directions.
 */

/** Convert a bracket-notation path to dot-index notation for use in a URL or Astro param.
 *
 * `encode('epics[0].stories[3].build')` → `'epics.0.stories.3.build'`
 * `encode('plan')` → `'plan'`
 */
export function encode(bracketPath: string): string {
  return bracketPath.replace(/\[(\d+)\]/g, '.$1');
}

/** Convert a dot-index path back to bracket notation for use in an API call.
 *
 * `decode('epics.0.stories.3.build')` → `'epics[0].stories[3].build'`
 * `decode('plan')` → `'plan'`
 *
 * Only pure-digit segments (matching `\d+`) are converted; alphabetic segments are left
 * as-is, so `decode('epics.stories.build')` returns `'epics.stories.build'` unchanged.
 */
export function decode(dotIndexPath: string): string {
  return dotIndexPath.replace(/\.(\d+)/g, '[$1]');
}
