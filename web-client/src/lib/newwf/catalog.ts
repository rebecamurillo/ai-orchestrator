/**
 * Which Templates the New Workflow form offers, and what each one asks for.
 *
 * `ROOT_TEMPLATES` names them; each Template's own declared `inputs` decide its fields. The
 * catalog crosses the island boundary as a `client:load` prop, so it is plain data and every
 * question about it is a module function.
 */
import type { components } from '../../api/schema';

type InputDeclOut = components['schemas']['InputDeclOut'];

/** Offered when `ROOT_TEMPLATES` says nothing. `story` is absent: it is only ever called by
 * another Template (FR-33). */
export const DEFAULT_ROOT_TEMPLATES = 'initiative,epic,repo-init,story-run';

const SEPARATOR = ',';

/** Bound when the Run is created, never typed into this form. */
const RUNTIME_BOUND_TYPES: ReadonlySet<string> = new Set(['project', 'repository', 'item']);

/** Inputs the form already has a dedicated control for. */
const FORM_OWNED_NAMES: ReadonlySet<string> = new Set(['base_branch', 'harness', 'model']);

const HARNESS_INPUT = 'harness';

/** Label and tooltip copy, keyed by input name so any Template declaring the same input
 * inherits it. `branch` also overrides the derived label. */
const INPUT_COPY: Readonly<Record<string, { label?: string; tooltip: string }>> = {
  initiative_folder: {
    tooltip:
      'Path in the repository where planning output lands. Passed to the template as initiative_folder.',
  },
  branch: {
    label: 'WORKING BRANCH',
    tooltip:
      'Branch the harness creates and pushes this Run’s commits to. Passed to the template as branch.',
  },
  spec_folder: {
    tooltip:
      "Path holding the epic's stories.yaml and story spec files. Passed to the template as spec_folder.",
  },
  story_id: {
    tooltip:
      'Id of the one story from stories.yaml this Run works. Passed to the template as story_id.',
  },
  task_id: {
    tooltip: 'Id that names the task and its spec file. Passed to the template as task_id.',
  },
  title: { tooltip: 'One-line name of the change. Passed to the template as title.' },
  intent: {
    tooltip:
      'What the change should accomplish, in the Operator’s words. Passed to the template as intent.',
  },
  artifacts_dir: {
    tooltip:
      'Path in the repository where the task’s spec and review land. Passed to the template as artifacts_dir.',
  },
};

export interface TemplateInputField {
  key: string;
  label: string;
  tooltip: string;
  required: boolean;
  /** The Template's declared `default:` as text, or `''`. */
  initial: string;
}

export interface TemplateEntry {
  name: string;
  fields: TemplateInputField[];
  usesHarness: boolean;
}

export interface TemplateCatalog {
  /** Offered Templates, in `ROOT_TEMPLATES`' own order. */
  names: string[];
  entries: Record<string, TemplateEntry>;
}

export const EMPTY_CATALOG: TemplateCatalog = { names: [], entries: {} };

/** Trimmed, de-duplicated, order preserved. Blank reads as unset — `envField`'s own default
 * fires only for an absent variable. */
export function parseRootTemplates(raw: string | null | undefined): string[] {
  const names = splitNames(raw ?? '');
  return names.length > 0 ? names : splitNames(DEFAULT_ROOT_TEMPLATES);
}

function splitNames(raw: string): string[] {
  const seen = new Set<string>();
  const names: string[] = [];
  for (const segment of raw.split(SEPARATOR)) {
    const name = segment.trim();
    if (name === '' || seen.has(name)) continue;
    seen.add(name);
    names.push(name);
  }
  return names;
}

function isBindable(input: InputDeclOut): boolean {
  return !RUNTIME_BOUND_TYPES.has(input.type) && !FORM_OWNED_NAMES.has(input.name);
}

/** `spec_folder` → `SPEC FOLDER`. */
export function deriveLabel(name: string): string {
  return name.replace(/_/g, ' ').toUpperCase();
}

function initialOf(input: InputDeclOut): string {
  return input.default === null || input.default === undefined ? '' : String(input.default);
}

export function deriveFields(inputs: InputDeclOut[]): TemplateInputField[] {
  return inputs.filter(isBindable).map((input) => {
    const copy = INPUT_COPY[input.name];
    return {
      key: input.name,
      label: copy?.label ?? deriveLabel(input.name),
      tooltip: copy?.tooltip ?? `Passed to the template as ${input.name}.`,
      required: input.required,
      initial: initialOf(input),
    } satisfies TemplateInputField;
  });
}

/** Whether this Template dispatches a harness — by whether it declares one, never by name. */
export function derivesHarness(inputs: InputDeclOut[]): boolean {
  return inputs.some((input) => input.name === HARNESS_INPUT);
}

/** The names that resolved, in the order asked for; a name the store did not answer for is
 * dropped. Prototype-safe: `ROOT_TEMPLATES` is free text and this is where it becomes a key. */
export function buildCatalog(
  names: string[],
  inputsByName: Record<string, InputDeclOut[]>,
): TemplateCatalog {
  const entries: Record<string, TemplateEntry> = Object.create(null) as Record<
    string,
    TemplateEntry
  >;
  const offered: string[] = [];
  for (const name of names) {
    if (!Object.hasOwn(inputsByName, name)) continue;
    const inputs = inputsByName[name];
    if (!Array.isArray(inputs)) continue;
    offered.push(name);
    entries[name] = {
      name,
      fields: deriveFields(inputs),
      usesHarness: derivesHarness(inputs),
    };
  }
  return { names: offered, entries };
}

export function firstTemplate(catalog: TemplateCatalog): string {
  return catalog.names[0] ?? '';
}

export function offers(catalog: TemplateCatalog, name: string): boolean {
  return entryOf(catalog, name) !== undefined;
}

function entryOf(catalog: TemplateCatalog, name: string): TemplateEntry | undefined {
  return Object.hasOwn(catalog.entries, name) ? catalog.entries[name] : undefined;
}

export function fieldsFor(catalog: TemplateCatalog, name: string): TemplateInputField[] {
  return entryOf(catalog, name)?.fields ?? [];
}

export function usesHarness(catalog: TemplateCatalog, name: string): boolean {
  return entryOf(catalog, name)?.usesHarness ?? false;
}
