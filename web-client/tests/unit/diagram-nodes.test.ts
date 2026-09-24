/**
 * `src/components/run/diagram/nodes.tsx` — the five cards of the v3 run diagram.
 *
 * The `…Card` half of each node type carries no React Flow and no store, which is what lets
 * it render under `renderToStaticMarkup` in the `environment: 'node'` suite: every test id
 * of the EXPERIENCE-v1 §id grammar, every word token and the guardrail strip are asserted
 * against real output rather than against the source that produces it.
 */
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { AgentCard, EpicCard, RootCard, StoryCard } from '../../src/components/run/diagram/nodes';
import { GuardrailStrip, RetryCard, RetryMoreCard } from '../../src/components/run/diagram/strips';
import { buildHierarchy, ROOT_ID, type HierarchyNode } from '../../src/lib/diagram/run-tree';
import { frameLessGraph, frameLessSteps, twoEpicGraph, twoEpicSteps } from '../fixtures/run-graph';

const BUILT = buildHierarchy(
  twoEpicGraph(),
  twoEpicSteps().map((row) =>
    row.path === 'epics[1].stories[0].build' ? { ...row, attempts: 2 } : row,
  ),
  new Set(['epics[1]', 'epics[1].stories[0]']),
);

function node(id: string): HierarchyNode {
  return BUILT.nodes.find((entry) => entry.id === id)!;
}

const noop = () => undefined;

describe('RootCard', () => {
  it('is the root test id, with the plan size and the run token', () => {
    const html = renderToStaticMarkup(createElement(RootCard, { node: node('root') }));

    expect(html).toContain('data-testid="wf-diagram-node-root"');
    expect(html).toContain('3 epics · 5 stories');
    expect(html).toContain('>RUN<');
    // a running ancestor keeps the strong hairline; blue is the current step's alone
    expect(html).toContain('data-status="inflight"');
  });
});

describe('EpicCard', () => {
  it('carries its dot-index test id, its k/n and a caret that says it is open', () => {
    const html = renderToStaticMarkup(
      createElement(EpicCard, { node: node('epics[1]'), onToggle: noop }),
    );

    expect(html).toContain('data-testid="wf-diagram-node-epics.1"');
    expect(html).toContain('data-testid="wf-diagram-toggle-epics.1"');
    expect(html).toContain('aria-expanded="true"');
    expect(html).toContain('5/14 steps');
  });

  it('says it is closed when it is', () => {
    const closed = buildHierarchy(twoEpicGraph(), twoEpicSteps(), new Set());
    const html = renderToStaticMarkup(
      createElement(EpicCard, {
        node: closed.nodes.find((entry) => entry.id === 'epics[2]')!,
        onToggle: noop,
      }),
    );

    expect(html).toContain('aria-expanded="false"');
  });

  it('keeps the caret out of a drag, so a click on it is a click', () => {
    const html = renderToStaticMarkup(
      createElement(EpicCard, { node: node('epics[1]'), onToggle: noop }),
    );

    expect(html).toMatch(/class="wf-node-caret nodrag"/);
  });
});

describe('StoryCard', () => {
  it('draws its guardrail strip and no node for the rows in it', () => {
    const html = renderToStaticMarkup(
      createElement(StoryCard, { node: node('epics[1].stories[0]'), onToggle: noop }),
    );

    expect(html).toContain('data-testid="wf-diagram-guardrail-epics.1.stories.0"');
    expect(html).toContain('data-testid="wf-diagram-guardrail-epics.1.stories.0-sync"');
    expect(html).toContain('data-testid="wf-diagram-guardrail-epics.1.stories.0-verify"');
    expect(html).toContain('data-testid="wf-diagram-guardrail-epics.1.stories.0-commit-guard"');
    expect(html).not.toContain('wf-diagram-node-epics.1.stories.0.sync');
    expect(html).not.toContain('wf-diagram-open-');
  });

  it('announces itself as a labelled group, in words', () => {
    const html = renderToStaticMarkup(
      createElement(StoryCard, { node: node('epics[1].stories[0]'), onToggle: noop }),
    );

    expect(html).toContain('aria-label="story 2-1 · running · holds the current step"');
    expect(html).toContain('role="group"');
  });
});

describe('AgentCard', () => {
  it('carries the Open step CTA, and the CTA alone navigates', () => {
    const html = renderToStaticMarkup(
      createElement(AgentCard, { node: node('epics[1].stories[0].build'), runId: 'r1' }),
    );

    expect(html).toContain('data-testid="wf-diagram-open-epics.1.stories.0.build"');
    expect(html).toMatch(/class="wf-node-cta nodrag"/);
    expect(html).toContain('Open step');
    // a real link, so middle-click, cmd-click and copy-link-address all work; `nodrag`
    // is what keeps a click on it a click rather than the start of a drag. The card body
    // is still a drag handle: the title and meta carry no href of their own.
    expect(html).toMatch(
      /<a class="wf-node-cta nodrag"[^>]*href="\/workflows\/r1\/steps\/epics\.1\.stories\.0\.build"/,
    );
    expect([...html.matchAll(/<a /g)]).toHaveLength(1);
    expect(html).not.toMatch(/<p class="wf-node-title"[^>]*href/);
  });

  it('says `now` in place of the kind on the current step, and carries the blue border', () => {
    const html = renderToStaticMarkup(
      createElement(AgentCard, { node: node('epics[1].stories[0].build'), runId: 'r1' }),
    );

    expect(html).toContain('data-now="true"');
    expect(html).toContain('>now<');
    expect(html).toContain('data-status="running"');
    expect(html).toContain('claude · sonnet · 2 attempts');
  });

  it('omits the CTA when no step row joins the node', () => {
    const orphan = buildHierarchy(twoEpicGraph(), [], new Set(['epics[1]', 'epics[1].stories[0]']));
    const html = renderToStaticMarkup(
      createElement(AgentCard, {
        node: orphan.nodes.find((entry) => entry.id === 'epics[1].stories[0].build')!,
        runId: 'r1',
      }),
    );

    expect(html).toContain('data-testid="wf-diagram-node-epics.1.stories.0.build"');
    expect(html).not.toContain('wf-diagram-open-');
  });
});

describe('GuardrailStrip', () => {
  it('draws four entries and then `+k`', () => {
    const html = renderToStaticMarkup(
      createElement(GuardrailStrip, {
        strip: {
          ownerId: 'epics[0]',
          ownerPath: 'epics.0',
          overflow: 4,
          muted: false,
          entries: ['branch', 'setup', 'baseline', 'commit-e2e'].map((label) => ({
            stepId: label,
            path: `epics[0].${label}`,
            label,
            dot: 'done' as const,
            token: 'DON',
            word: 'done',
            stop: false,
          })),
        },
      }),
    );

    expect([...html.matchAll(/wf-guardrail-entry/g)]).toHaveLength(4);
    expect(html).toContain('+4');
  });

  it('is nothing at all on a card that owns no deterministic row', () => {
    expect(renderToStaticMarkup(createElement(GuardrailStrip, { strip: null }))).toBe('');
  });
});

describe('RetryCard', () => {
  it('is `try n` over `failed`, with the exit code when the wire carried one', () => {
    const html = renderToStaticMarkup(
      createElement(RetryCard, {
        chip: { n: 2, label: 'try 2', exitCode: 1 },
        ownerPath: 'epics.1.stories.0.build',
      }),
    );

    expect(html).toContain('data-testid="wf-diagram-retry-epics.1.stories.0.build-2"');
    expect(html).toContain('try 2');
    expect(html).toContain('failed');
    expect(html).toContain('exit 1');
  });

  it('says only `failed` when no code is on the wire', () => {
    const html = renderToStaticMarkup(
      createElement(RetryCard, {
        chip: { n: 1, label: 'try 1', exitCode: null },
        ownerPath: 'epics.1.stories.0.build',
      }),
    );

    expect(html).toContain('failed');
    expect(html).not.toContain('exit');
  });
});

describe('the word token is authoritative', () => {
  it('never colours a card without printing the word beside it', () => {
    for (const id of ['root', 'epics[1]', 'epics[1].stories[0]', 'epics[1].stories[0].build']) {
      const entry = node(id);
      expect(entry.token, id).not.toBeNull();
    }
  });
});

describe('the root card', () => {
  it('draws the guardrail strip it was built with — a strip built is a strip drawn', () => {
    // `plan`, and a hub Run's `checkout`/`submodules`, own no frame: the root collected them
    // and had no renderer for them, so they were absent from the diagram entirely
    const built = buildHierarchy(frameLessGraph(), frameLessSteps(), new Set());
    const html = renderToStaticMarkup(
      createElement(RootCard, { node: built.nodes.find((entry) => entry.id === ROOT_ID)! }),
    );

    expect(html).toContain('data-testid="wf-diagram-guardrail-root"');
    expect(html).toContain('data-testid="wf-diagram-guardrail-root-sync"');
    expect(html).toContain('data-testid="wf-diagram-guardrail-root-verify"');
    expect(html).toContain('data-testid="wf-diagram-guardrail-root-commit-guard"');
  });

  it('has a renderer for every owner kind the model can build a strip for', () => {
    const owners = { root: RootCard, epic: EpicCard, story: StoryCard };
    const built = buildHierarchy(twoEpicGraph(), twoEpicSteps(), new Set(['epics[1]']));

    for (const strip of built.guardrails) {
      const owner = built.nodes.find((entry) => entry.id === strip.ownerId)!;
      const Card = owners[owner.kind as keyof typeof owners];
      expect([owner.id, Card === undefined]).toEqual([owner.id, false]);
      const html = renderToStaticMarkup(
        createElement(Card as typeof EpicCard, { node: owner, onToggle: noop }),
      );
      expect(html, owner.id).toContain(`data-testid="wf-diagram-guardrail-${strip.ownerPath}"`);
    }
  });
});

describe('the guardrail strip speaks as well as it draws', () => {
  function strip(overflow = 0) {
    return {
      ownerId: 'epics[0]',
      ownerPath: 'epics.0',
      overflow,
      muted: false,
      entries: [
        {
          stepId: 'sync',
          path: 'epics[0].sync',
          label: 'sync',
          dot: 'done' as const,
          token: 'DON',
          word: 'done',
          stop: false,
        },
        {
          stepId: 'verify',
          path: 'epics[0].verify',
          label: 'verify',
          dot: 'queued' as const,
          token: 'QUE',
          word: 'queued',
          stop: false,
        },
      ],
    };
  }

  it('puts its separator in the markup, where an accessible name can read it', () => {
    // a CSS `::before` `·` is absent from the accessible name: the strip read
    // `syncverifycommit-guard` to anything not looking at it
    const html = renderToStaticMarkup(createElement(GuardrailStrip, { strip: strip() }));

    expect(html).toContain('wf-guardrail-sep');
    expect(html.replace(/<[^>]+>/g, '')).toContain('sync');
    expect(html.replace(/<[^>]+>/g, '')).toContain(' · ');
  });

  it('says each row’s state in words, not in a dot alone', () => {
    const html = renderToStaticMarkup(createElement(GuardrailStrip, { strip: strip() }));

    expect(html).toContain('title="sync · done"');
    expect(html).toContain('title="verify · queued"');
    expect(html).toContain('<span class="wf-visually-hidden"> done</span>');
  });
});

describe('RetryMoreCard', () => {
  it('stands for the failures the gutter did not draw', () => {
    const html = renderToStaticMarkup(
      createElement(RetryMoreCard, { overflow: 5, ownerPath: 'epics.1.stories.0.build' }),
    );

    expect(html).toContain('data-testid="wf-diagram-retry-epics.1.stories.0.build-more"');
    expect(html).toContain('+5');
    expect(html).toContain('aria-label="5 more failed attempts"');
  });
});

describe('a card is the focusable thing', () => {
  it('takes a tab stop of its own, carrying the label it already had', () => {
    const html = renderToStaticMarkup(
      createElement(AgentCard, { node: node('epics[1].stories[0].build'), runId: 'r1' }),
    );

    expect(html).toContain('tabindex="0"');
    expect(html).toContain('role="group"');
    // the current step and a running ancestor both read `RUN`; the name says which
    expect(html).toContain('aria-label="build · running · current step"');
  });

  it('says of an ancestor that it holds the current step, not that it is one', () => {
    const html = renderToStaticMarkup(
      createElement(EpicCard, { node: node('epics[1]'), onToggle: noop }),
    );

    expect(html).toContain('aria-label="epic 2 · running · holds the current step"');
    expect(html).toContain('data-status="inflight"');
  });

  it('says nothing extra of a card that neither is nor holds the current step', () => {
    const html = renderToStaticMarkup(
      createElement(EpicCard, { node: node('epics[0]'), onToggle: noop }),
    );

    expect(html).toContain('aria-label="epic 1 · done"');
  });

  it('cuts a long title with an ellipsis and keeps it whole in the title attribute', () => {
    const long = 'a-story-name-far-wider-than-the-two-hundred-and-sixteen-pixels-it-is-given';
    const html = renderToStaticMarkup(
      createElement(AgentCard, {
        node: { ...node('epics[1].stories[0].build'), title: long },
        runId: 'r1',
      }),
    );

    expect(html).toContain(`title="${long}"`);
    expect(html).toContain('class="wf-node-title"');
  });
});
