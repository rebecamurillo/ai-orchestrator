/**
 * `tsc --noEmit` resolves `.astro` imports inside `.astro` files through the Astro compiler,
 * but a `.ts` file importing a component has no such module type — and unit tests render
 * components with `astro/container`, so they do exactly that.
 *
 * Declaring the module here does not weaken `astro check`: the language server resolves the
 * real component ahead of this ambient declaration and still reports a missing or mistyped
 * prop at a call site.
 */
declare module '*.astro' {
  const component: import('astro/runtime/server/index.js').AstroComponentFactory;
  export default component;
}
