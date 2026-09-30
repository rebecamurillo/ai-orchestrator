/**
 * `src/lib/newwf/catalog.ts` — which Templates the form offers and what each one asks for.
 *
 * Replaces what `newwf-state.test.ts` pinned as `TEMPLATE_ORDER` and `TEMPLATE_INPUT_FIELDS`
 * constants (Operator instruction 2026-09-22): these pin the rules that now produce them.
 * Template shapes come from `newwf-catalog-fixture.ts`, which the tests own (hard rule 6).
 */
import { describe, expect, it } from 'vitest';

import {
  DEFAULT_ROOT_TEMPLATES,
  buildCatalog,
  deriveFields,
  deriveLabel,
  derivesHarness,
  fieldsFor,
  firstTemplate,
  offers,
  parseRootTemplates,
  usesHarness,
} from '../../src/lib/newwf/catalog';
import {
  FIXTURE_INPUTS,
  FIXTURE_ORDER,
  OPTIONAL_INPUT_DEFAULT,
  OPTIONAL_INPUT_TEMPLATE,
  catalogWithDefaulted,
  fixtureCatalog,
} from './newwf-catalog-fixture';
import type { components } from '../../src/api/schema';

type InputDeclOut = components['schemas']['InputDeclOut'];

const keys = (name: string): string[] =>
  fieldsFor(fixtureCatalog(), name).map((field) => field.key);

describe('parseRootTemplates — ROOT_TEMPLATES is the source of truth', () => {
  it('falls back to the shipped default when the variable is unset', () => {
    expect(parseRootTemplates(undefined)).toEqual(FIXTURE_ORDER);
    expect(parseRootTemplates(null)).toEqual(FIXTURE_ORDER);
  });

  it('falls back when the variable is set but blank — envField’s own default cannot', () => {
    expect(parseRootTemplates('')).toEqual(FIXTURE_ORDER);
    expect(parseRootTemplates('   ')).toEqual(FIXTURE_ORDER);
    expect(parseRootTemplates(',, ,')).toEqual(FIXTURE_ORDER);
  });

  it('keeps the Operator’s own order, and offers names nothing shipped', () => {
    expect(parseRootTemplates('epic-oss,epic')).toEqual(['epic-oss', 'epic']);
  });

  it('trims whitespace and drops duplicates, first occurrence winning', () => {
    expect(parseRootTemplates(' epic , epic-oss ,epic, ')).toEqual(['epic', 'epic-oss']);
  });

  it('names no Template itself: the default list is the only place one is written', () => {
    expect(DEFAULT_ROOT_TEMPLATES.split(',')).toEqual(FIXTURE_ORDER);
  });
});

describe('buildCatalog — the variable filters what is stored, it does not conjure it', () => {
  it('drops a name the Template store did not answer for', () => {
    const catalog = buildCatalog(['epic', 'ghost'], FIXTURE_INPUTS);

    expect(catalog.names).toEqual(['epic']);
    expect(offers(catalog, 'ghost')).toBe(false);
  });

  it('offers nothing when no listed name resolved', () => {
    const catalog = buildCatalog(['ghost'], FIXTURE_INPUTS);

    expect(catalog.names).toEqual([]);
    expect(firstTemplate(catalog)).toBe('');
  });

  it('preserves the order asked for, not the order of the answers', () => {
    expect(buildCatalog(['task', 'epic'], FIXTURE_INPUTS).names).toEqual(['task', 'epic']);
  });

  it('selects the first offered Template by default', () => {
    expect(firstTemplate(buildCatalog(['task', 'epic'], FIXTURE_INPUTS))).toBe('task');
  });
});

describe('deriveFields — a Template asks for what it declares', () => {
  it('renders no field for an input bound at run time or owned by another control', () => {
    // `repo-init` declares only project, repository, base_branch, harness and model
    expect(keys('repo-init')).toEqual([]);
  });

  it('reproduces each shipped Template’s field list from its declarations alone', () => {
    // `task` left the shipped set and the default list (Operator decision, 2026-09-30);
    // the fixture keeps its declarations for the tests that need a fifth name.
    expect(keys('initiative')).toEqual(['initiative_folder']);
    expect(keys('epic')).toEqual(['branch', 'spec_folder']);
    expect(keys('story-run')).toEqual(['branch', 'spec_folder', 'story_id']);
  });

  it('derives the label from the input name, and every field states a tooltip', () => {
    expect(deriveLabel('spec_folder')).toBe('SPEC FOLDER');
    expect(deriveLabel('artifacts_dir')).toBe('ARTIFACTS DIR');

    for (const name of FIXTURE_ORDER) {
      for (const field of fieldsFor(fixtureCatalog(), name)) {
        expect(field.tooltip).not.toBe('');
      }
    }
  });

  it('keeps WORKING BRANCH, the one label the derivation would otherwise change', () => {
    const branch = fieldsFor(fixtureCatalog(), 'epic').find((field) => field.key === 'branch');

    expect(branch?.label).toBe('WORKING BRANCH');
  });

  it('states a tooltip for an input nobody wrote copy for', () => {
    const declared: InputDeclOut[] = [
      { name: 'skill_dir', type: 'path', required: false, default: null, values: [] },
    ];

    expect(deriveFields(declared)[0]?.tooltip).toContain('skill_dir');
  });

  it('carries `required` and prefills a declared default', () => {
    const declared: InputDeclOut[] = [
      { name: 'skill_dir', type: 'path', required: false, default: '/home/agent/x', values: [] },
      { name: 'spec_folder', type: 'path', required: true, default: null, values: [] },
    ];
    const [optional, mandatory] = deriveFields(declared);

    expect(optional).toMatchObject({ required: false, initial: '/home/agent/x' });
    expect(mandatory).toMatchObject({ required: true, initial: '' });
  });

  it('reads a non-string default as the text a field opens at', () => {
    const declared: InputDeclOut[] = [
      { name: 'depth', type: 'number', required: false, default: 3, values: [] },
    ];

    expect(deriveFields(declared)[0]?.initial).toBe('3');
  });
});

describe('derivesHarness — the rule that replaced a Template name', () => {
  it('shows the harness list for a Template that declares a harness input', () => {
    // `repo-init` declares one and carries a `uses: agent` step; the old rule hid it by name
    expect(usesHarness(fixtureCatalog(), 'repo-init')).toBe(true);
    expect(usesHarness(fixtureCatalog(), 'epic')).toBe(true);
  });

  it('hides it for a Template that declares none', () => {
    const declared: InputDeclOut[] = [
      { name: 'project', type: 'project', required: true, default: null, values: [] },
    ];

    expect(derivesHarness(declared)).toBe(false);
    expect(usesHarness(buildCatalog(['quiet'], { quiet: declared }), 'quiet')).toBe(false);
  });

  it('hides it for a Template this catalog does not offer at all', () => {
    expect(usesHarness(fixtureCatalog(), 'ghost')).toBe(false);
  });
});

/** `ROOT_TEMPLATES` is free text, and `buildCatalog` is where a segment of it becomes a key. */
describe('a name that collides with Object.prototype', () => {
  it.each(['constructor', '__proto__', 'toString', 'valueOf', 'hasOwnProperty'])(
    'is dropped rather than throwing or half-registering: %s',
    (name) => {
      const catalog = buildCatalog([name, 'epic'], FIXTURE_INPUTS);

      expect(catalog.names).toEqual(['epic']);
      expect(offers(catalog, name)).toBe(false);
      expect(fieldsFor(catalog, name)).toEqual([]);
      expect(usesHarness(catalog, name)).toBe(false);
    },
  );

  it('is offered normally when the Template store actually answers for it', () => {
    const catalog = buildCatalog(['constructor'], { constructor: FIXTURE_INPUTS.epic });

    expect(catalog.names).toEqual(['constructor']);
    expect(fieldsFor(catalog, 'constructor').map((field) => field.key)).toEqual([
      'branch',
      'spec_folder',
    ]);
  });

  it('reads a catalog that came back through JSON, as an island prop does', () => {
    const catalog = JSON.parse(
      JSON.stringify(buildCatalog(['epic'], FIXTURE_INPUTS)),
    ) as ReturnType<typeof buildCatalog>;

    expect(offers(catalog, 'toString')).toBe(false);
    expect(fieldsFor(catalog, 'toString')).toEqual([]);
  });
});

describe('an optional input that declares a default', () => {
  it('is carried onto the field the form renders', () => {
    const field = fieldsFor(catalogWithDefaulted(), OPTIONAL_INPUT_TEMPLATE).find(
      (candidate) => candidate.key === 'skill_dir',
    );

    expect(field).toMatchObject({ required: false, initial: OPTIONAL_INPUT_DEFAULT });
  });
});
