/**
 * The base components, rendered.
 *
 * `astro/container` runs a component the way a page runs it, so these assertions are made
 * against real output rather than against the source that produces it. What matters here is
 * the part of the visual system a stylesheet cannot hold: which word token gets which
 * signal, that a zero count renders nothing at all rather than a grey nothing, and that the
 * shell parts carry the test-ids UX-DR18 fixes for every later screen.
 */
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { experimental_AstroContainer as AstroContainer } from 'astro/container';
import { beforeAll, describe, expect, it } from 'vitest';

import AlertBanner from '../../src/components/AlertBanner.astro';
import AppRail from '../../src/components/AppRail.astro';
import Button from '../../src/components/Button.astro';
import CommandBlock from '../../src/components/CommandBlock.astro';
import DenseTable from '../../src/components/DenseTable.astro';
import EmptyState from '../../src/components/EmptyState.astro';
import FooterReadout from '../../src/components/FooterReadout.astro';
import KvTable from '../../src/components/KvTable.astro';
import RecordRow from '../../src/components/RecordRow.astro';
import SectionHead from '../../src/components/SectionHead.astro';
import StatusToken from '../../src/components/StatusToken.astro';
import SurfaceBar from '../../src/components/SurfaceBar.astro';

let container: AstroContainer;

beforeAll(async () => {
  container = await AstroContainer.create();
});

function render(
  component: Parameters<AstroContainer['renderToString']>[0],
  props: Record<string, unknown>,
): Promise<string> {
  return container.renderToString(component, { props });
}

function source(name: string): string {
  return readFileSync(
    fileURLToPath(new URL(`../../src/components/${name}`, import.meta.url)),
    'utf8',
  );
}

/** Astro appends a scope class; the authored class name survives beside it. */
function hasClass(html: string, name: string): boolean {
  return new RegExp(`class="[^"]*\\b${name}\\b`).test(html);
}

describe('StatusToken', () => {
  // the full vocabulary, and the only mapping of it onto the three v1 signal hues
  const SIGNALS: Record<string, string> = {
    QUE: 'neutral',
    RUN: 'run',
    BLK: 'needs-you',
    CHK: 'needs-you',
    DON: 'neutral',
    ERR: 'failed',
    CAN: 'neutral',
    SKP: 'neutral',
  };

  it.each(Object.entries(SIGNALS))('%s renders on the %s signal', async (token, signal) => {
    const html = await render(StatusToken, { token });

    expect(html).toContain(`data-token="${token}"`);
    expect(html).toContain(`data-signal="${signal}"`);
    expect(html).toContain(`>${token}<`);
  });

  it('gives the chip and the token one colour by construction', () => {
    const css = source('StatusToken.astro');

    // 7px square, not a dot: a circle reads as a bullet, a square as an indicator lamp
    expect(css).toMatch(/width:\s*7px/);
    expect(css).toMatch(/height:\s*7px/);
    // the chip takes the token's colour rather than repeating it — they cannot drift apart
    expect(css).toMatch(/background:\s*currentColor/);
  });

  it('renders the chip alongside the token', async () => {
    const html = await render(StatusToken, { token: 'RUN' });

    expect(hasClass(html, 'chip')).toBe(true);
  });

  it('never gives a skipped or cancelled step the running colour', async () => {
    for (const token of ['SKP', 'CAN', 'DON', 'QUE']) {
      expect(await render(StatusToken, { token })).toContain('data-signal="neutral"');
    }
  });
});

describe('AppRail', () => {
  const base = { active: 'workflows', workflows: 0, runs: 0, needsYou: 0 };

  it('carries the four navigation test-ids and the brand subtitle', async () => {
    const html = await render(AppRail, base);

    for (const id of ['nav-workflows', 'nav-runs', 'nav-projects', 'nav-templates']) {
      expect(html).toContain(`data-testid="${id}"`);
    }
    expect(html).toContain('MVP · single operator');
    expect(html).toContain('CONFIGURE');
  });

  it.each(['workflows', 'runs', 'projects', 'templates'])('marks %s active', async (active) => {
    const html = await render(AppRail, { ...base, active });

    expect(html).toMatch(new RegExp(`data-testid="nav-${active}"[^>]*aria-current="page"`));
    expect([...html.matchAll(/aria-current="page"/g)]).toHaveLength(1);
  });

  it('shows the needs-you count on the amber signal when work is waiting', async () => {
    const html = await render(AppRail, { ...base, workflows: 7, needsYou: 3 });

    expect(html).toMatch(/data-testid="nav-needs-you"[^>]*data-signal="needs-you"/);
    expect(html).toContain('3 need you');
  });

  it('renders no needs-you element at all when nothing is waiting', async () => {
    // NFR-6: a screen with nothing needing the Operator has no amber pixel. Not rendering
    // the count is what makes that true; the Playwright scan only confirms it.
    const html = await render(AppRail, { ...base, workflows: 7, needsYou: 0 });

    expect(html).not.toContain('nav-needs-you');
    expect(html).not.toContain('need you');
  });
});

describe('FooterReadout', () => {
  it('states the four figures in the shell format', async () => {
    const html = await render(FooterReadout, {
      running: 2,
      queued: 1,
      needsYou: 2,
      updated: '14:07:31',
    });

    expect(html).toContain('data-testid="footer-readout"');
    expect(html).toContain('2 running · 1 queued / 2 need you / updated 14:07:31');
  });

  it('reads an em dash for the update time before anything has been polled', async () => {
    const html = await render(FooterReadout, { running: 0, queued: 0, needsYou: 0, updated: '—' });

    expect(html).toContain('0 running · 0 queued / 0 need you / updated —');
  });
});

describe('EmptyState', () => {
  it('is a readout: an uppercase headline, then what is happening instead', async () => {
    const html = await render(EmptyState, {
      testId: 'board-empty',
      headline: 'NOTHING REGISTERED',
      lines: ['No project is registered.', 'Register one on /projects.'],
    });

    expect(html).toContain('data-testid="board-empty"');
    expect(html).toContain('NOTHING REGISTERED');
    expect(html).toContain('No project is registered.');
    expect(html).toContain('Register one on /projects.');
  });
});

describe('RecordRow', () => {
  it('lays every row on the one fixed grid', () => {
    // UX-DR5: the grid is a contract. A row that reads the token cannot choose its columns.
    expect(source('RecordRow.astro')).toContain('grid-template-columns: var(--record-grid)');
  });

  it('opens with the status token in the leftmost column', async () => {
    const html = await render(RecordRow, {
      token: 'BLK',
      project: 'orchestrator',
      repository: 'ai-orchestrator',
      title: 'story 4-1 · build',
      hint: 'waiting for your answer',
      age: '2d 04h',
      href: '/workflows/abc',
    });

    expect(html.indexOf('data-token="BLK"')).toBeLessThan(html.indexOf('orchestrator'));
    expect(html).toContain('waiting for your answer');
    expect(html).toContain('2d 04h');
  });
});

describe('SurfaceBar', () => {
  it('states the surface and its count, and offers no hero', async () => {
    const html = await render(SurfaceBar, { title: 'RUNS', count: '7 attempts' });

    expect(html).toContain('data-testid="surface-title"');
    expect(html).toContain('RUNS');
    expect(html).toContain('7 attempts');
  });

  it('omits the count when the surface has none to state', async () => {
    const html = await render(SurfaceBar, { title: 'NEW WORKFLOW' });

    expect(hasClass(html, 'count')).toBe(false);
  });
});

describe('AlertBanner', () => {
  // the only place a signal colour extends beyond a 7px chip, and it is a rule, not a fill
  it.each(['needs-you', 'failed'])('carries the %s signal as a 2px left rule', async (level) => {
    const html = await render(AlertBanner, { level, text: 'verify failed 2/2' });

    expect(html).toContain(`data-signal="${level}"`);
    expect(html).toContain('verify failed 2/2');
  });

  it('rules the left edge at 2px and fills nothing', () => {
    const css = source('AlertBanner.astro');

    expect(css).toMatch(/border-left:\s*2px solid/);
    expect(css).toContain('background: var(--color-surface-raised)');
  });
});

describe('Button', () => {
  it('navigates as a link when it is given a destination', async () => {
    const html = await render(Button, { label: 'START RUN', href: '/workflows/new' });

    expect(html).toMatch(/<a[^>]*href="\/workflows\/new"/);
  });

  it('acts as a button when it is not', async () => {
    const html = await render(Button, { label: 'VALIDATE' });

    expect(html).toMatch(/<button[^>]*type="button"/);
  });

  it.each(['default', 'primary', 'destructive'])('renders the %s variant', async (variant) => {
    const html = await render(Button, { label: 'CANCEL RUN', variant });

    expect(html).toContain(`data-variant="${variant}"`);
  });

  it('is an outline, never a fill', () => {
    // there is no filled button anywhere: a filled rectangle is an area of colour, and
    // colour is signal
    expect(source('Button.astro')).toContain('background: none');
  });
});

describe('KvTable', () => {
  it('prints a ratio as a ratio, beside its label', async () => {
    const html = await render(KvTable, {
      rows: [
        { label: 'cost', value: '$4.18 / $15.00' },
        { label: 'gates', value: '2/2' },
      ],
    });

    expect(html).toContain('cost');
    expect(html).toContain('$4.18 / $15.00');
    expect(html).toContain('2/2');
  });
});

describe('DenseTable', () => {
  it('renders one column head per column and one cell per value', async () => {
    const html = await render(DenseTable, {
      columns: ['path', 'kind', 'gate'],
      rows: [
        ['epics[0].stories[3].build', 'agent', 'quality gate'],
        ['epics[0].stories[3].verify', 'shell', 'unvalidated'],
      ],
      testId: 'newwf-plan',
    });

    expect(html).toContain('data-testid="newwf-plan"');
    // `<th[ >]`, not `<th`: `<thead` starts with the same three characters
    expect([...html.matchAll(/<th[\s>]/g)]).toHaveLength(3);
    expect([...html.matchAll(/<td[\s>]/g)]).toHaveLength(6);
    expect(html).toContain('epics[0].stories[3].build');
  });
});

describe('SectionHead', () => {
  it('is the label, under a hairline', async () => {
    const html = await render(SectionHead, { label: 'ARTIFACTS' });

    expect(html).toContain('ARTIFACTS');
    expect(source('SectionHead.astro')).toContain('border-bottom: 1px solid var(--color-line)');
  });
});

describe('CommandBlock', () => {
  it('quotes the command verbatim and never wraps it', async () => {
    const command = 'claude --resume 0199f0c1-2b3d-7c4e-9a1b-2c3d4e5f6071';
    const html = await render(CommandBlock, { label: 'RESUME THE SESSION', command });

    expect(html).toContain(command);
    expect(html).toContain('RESUME THE SESSION');
    // a wrapped command is a command that breaks when it is pasted
    expect(source('CommandBlock.astro')).toContain('white-space: pre');
  });
});
