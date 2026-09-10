/**
 * The one pure computation *Export trajectories* needs (SPEC CAP-6, UX-DR12): the count
 * text beside the bar action. Kept out of `index.astro`'s frontmatter so it unit-tests
 * without rendering, the way `lib/projects/runs.ts`'s own docstring explains for its own
 * two functions.
 */

/** `"0 trajectories"`, `"1 trajectory"`, `"3 trajectories"` — `pluralize` (`index.astro`)
 * appends a bare `s`, which reads `trajectorys`; this noun needs the real plural instead. */
export function trajectoryCountText(count: number): string {
  return `${count} ${count === 1 ? 'trajectory' : 'trajectories'}`;
}
