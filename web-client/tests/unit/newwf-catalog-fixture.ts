/**
 * The Template catalog the `newwf-*` unit tests bind against — a fixture the tests own.
 *
 * Transcribed from `templates/*.yaml` and fed through the real `buildCatalog`, so the tests
 * exercise the shipped derivation. A copy, deliberately: hard rule 6 forbids pinning shipped
 * Template content, so an edit to `templates/epic.yaml` must never turn a unit test red.
 */
import { buildCatalog, type TemplateCatalog } from '../../src/lib/newwf/catalog';
import type { components } from '../../src/api/schema';

type InputDeclOut = components['schemas']['InputDeclOut'];

function decl(
  name: string,
  type: string,
  required = true,
  fallback: string | number | boolean | null = null,
): InputDeclOut {
  return { name, type, required, default: fallback, values: [] };
}

/** The fixture Template with an optional, defaulted, bindable input, and that default. */
export const OPTIONAL_INPUT_TEMPLATE = 'defaulted';

/** The fixture Template a Run can never start from: it declares a required `item` input. */
export const CALLEE_ONLY_TEMPLATE = 'called-only';
export const OPTIONAL_INPUT_DEFAULT = '/home/agent/skills/bmad-build-auto';

const PROJECT = decl('project', 'project');
const REPOSITORY = decl('repository', 'repository');
const BASE_BRANCH = decl('base_branch', 'string');
const HARNESS = decl('harness', 'enum', false, 'claude');
const MODEL = decl('model', 'string', false);

/** The five shipped root Templates, as their files declare them. */
export const FIXTURE_INPUTS: Record<string, InputDeclOut[]> = {
  initiative: [PROJECT, REPOSITORY, BASE_BRANCH, decl('initiative_folder', 'path'), HARNESS, MODEL],
  epic: [
    PROJECT,
    REPOSITORY,
    BASE_BRANCH,
    decl('branch', 'string'),
    decl('spec_folder', 'path'),
    decl('epic', 'item', false),
    HARNESS,
    MODEL,
  ],
  'repo-init': [PROJECT, REPOSITORY, BASE_BRANCH, HARNESS, MODEL],
  'story-run': [
    PROJECT,
    REPOSITORY,
    BASE_BRANCH,
    decl('branch', 'string'),
    decl('spec_folder', 'path'),
    decl('story_id', 'string'),
    HARNESS,
    MODEL,
  ],
  task: [
    PROJECT,
    REPOSITORY,
    BASE_BRANCH,
    decl('branch', 'string'),
    decl('task_id', 'string'),
    decl('title', 'string'),
    decl('intent', 'string'),
    decl('artifacts_dir', 'path'),
    HARNESS,
    MODEL,
  ],
  /** A Template only ever reached through a caller's `for_each`: its `item` input is
   * *required*, which is the declaration that keeps it out of the derived offer (FR-33). */
  [CALLEE_ONLY_TEMPLATE]: [
    PROJECT,
    REPOSITORY,
    BASE_BRANCH,
    decl('spec_folder', 'path'),
    decl('unit', 'item'),
    HARNESS,
    MODEL,
  ],
  /** The one shape no shipped Template has: an optional bindable input with a default.
   * Without it, `(optional)` and the prefill are unreachable from any test. */
  [OPTIONAL_INPUT_TEMPLATE]: [
    PROJECT,
    REPOSITORY,
    BASE_BRANCH,
    decl('spec_folder', 'path'),
    decl('skill_dir', 'path', false, OPTIONAL_INPUT_DEFAULT),
    HARNESS,
    MODEL,
  ],
};

/** The order a `ROOT_TEMPLATES` line asks for in these tests. Fixture-owned names, not a
 * default the product holds: since the Operator decision of 2026-09-30 no list of Template
 * names lives in `src/` at all. */
export const FIXTURE_ORDER = ['initiative', 'epic', 'repo-init', 'story-run'];

/** `FIXTURE_ORDER` plus the optional-input Template, for the tests that need that shape. */
export function catalogWithDefaulted(): TemplateCatalog {
  return buildCatalog([...FIXTURE_ORDER, OPTIONAL_INPUT_TEMPLATE], FIXTURE_INPUTS);
}

/** The catalog those five build, in that order. */
export function fixtureCatalog(): TemplateCatalog {
  return buildCatalog(FIXTURE_ORDER, FIXTURE_INPUTS);
}

/** The name of the fixture Template that declares no `harness` input. */
export const NO_HARNESS_TEMPLATE = 'quiet';

/** The five, plus a Template declaring no `harness` input — the shape whose form hides the
 * harness list. No shipped Template has it, `repo-init` included. */
export function catalogWithQuiet(): TemplateCatalog {
  return buildCatalog([...FIXTURE_ORDER, NO_HARNESS_TEMPLATE], {
    ...FIXTURE_INPUTS,
    [NO_HARNESS_TEMPLATE]: [PROJECT, REPOSITORY, BASE_BRANCH, decl('notes', 'path')],
  });
}
