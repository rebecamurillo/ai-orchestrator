// @vitest-environment jsdom
import { createElement } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';

import TimeStrip from '../../src/components/charts/TimeStrip';
import type { TargetContext } from '../../src/lib/run/metrics-glance';
import { value } from './metrics-fixtures';

const ctx: TargetContext = {
  runLabel: 'Run 7',
  versions: [],
  selected: null,
  latest: 1,
  items: [],
  subscription: false,
};
const secs = (id: string, n: string) => value({ metric_id: id, unit: 'seconds', value_num: n });

afterEach(cleanup);

describe('TimeStrip', () => {
  it('draws machine time solid in data-1 and waiting hatched in data-2 with its duration', () => {
    const { container } = render(
      createElement(TimeStrip, {
        title: 'where the time went',
        keyText: 'Machine time · hatched = Waiting on you',
        ctx,
        rows: [
          { id: 'time.machine', label: 'Machine time', value: secs('time.machine', '5400') },
          {
            id: 'time.parked',
            label: 'Waiting on you',
            value: secs('time.parked', '1800'),
            texture: 'hatch',
          },
        ],
      }),
    );
    const [machine, parked] = [...container.querySelectorAll('[role="button"]')];
    expect(machine.querySelector('rect')?.getAttribute('fill')).toBe('var(--color-chart-data-1)');
    expect(machine.querySelector('rect')?.getAttribute('height')).toBe('12');
    expect(machine.querySelector('text')?.textContent).toBe('1h 30m');
    const rect = parked.querySelector('rect');
    expect(rect?.getAttribute('fill')).toBe('url(#hatch-2)');
    expect(rect?.getAttribute('stroke')).toBe('var(--color-chart-data-2)');
    expect(rect?.getAttribute('stroke-width')).toBe('1');
    expect(parked.querySelector('text')?.textContent).toBe('0h 30m');
    expect(container.textContent).toContain('1h 40m');
    expect(screen.getByRole('figure').getAttribute('aria-label')).toBe('where the time went');
  });
});
