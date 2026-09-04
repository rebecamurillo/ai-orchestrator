import { expect, test, type Page } from '@playwright/test';

/**
 * One shell wraps every route (UX-DR3), and every route renders as an empty readout before
 * its data exists. The unit tests check the components in isolation; this is the only place
 * the composed page is measured — computed styles in a real browser, which is the only way
 * "no amber or red pixel" can be asserted rather than asserted about.
 */

const ROUTES = [
  {
    path: '/',
    nav: 'nav-workflows',
    title: 'WORKFLOWS',
    empty: 'board-empty',
    headline: 'NOTHING REGISTERED',
  },
  { path: '/runs', nav: 'nav-runs', title: 'RUNS', empty: 'runs-empty', headline: 'NO RUNS' },
  {
    path: '/projects',
    nav: 'nav-projects',
    title: 'PROJECTS',
    empty: 'projects-empty',
    headline: 'NO PROJECTS',
  },
  {
    path: '/templates',
    nav: 'nav-templates',
    title: 'TEMPLATES',
    empty: 'templates-empty',
    headline: 'NO TEMPLATES',
  },
  {
    path: '/workflows/new',
    nav: 'nav-workflows',
    title: 'NEW WORKFLOW',
    empty: 'newwf-empty',
    headline: 'NO TEMPLATE TO BIND',
  },
] as const;

const FOOTER = '0 running · 0 queued / 0 need you / updated —';

/** The two hues that mean "this needs you" and "this failed", as the browser reports them. */
const AMBER = 'rgb(228, 179, 60)';
const RED = 'rgb(224, 82, 82)';
const ACCENT = 'rgb(127, 212, 193)';

/**
 * Every place a colour can reach a pixel: text, ground, a border that is actually drawn, an
 * outline that is actually drawn, a shadow, a background image, and the two pseudo-elements.
 * A border-color on a zero-width border paints nothing, so reading it would report colours
 * the operator cannot see — the default border-color is the element's own `color`.
 */
async function paintedColours(
  page: Page,
): Promise<{ selector: string; property: string; value: string }[]> {
  return page.evaluate(() => {
    const found: { selector: string; property: string; value: string }[] = [];
    const describe = (element: Element): string => {
      const id = element.getAttribute('data-testid');
      return `${element.tagName.toLowerCase()}${id ? `[data-testid=${id}]` : ''}`;
    };

    const collect = (element: Element, pseudo: string | null) => {
      const style = getComputedStyle(element, pseudo);
      const selector = `${describe(element)}${pseudo ?? ''}`;
      const record = (property: string) => {
        const value = style.getPropertyValue(property);
        if (value) found.push({ selector, property, value });
      };

      record('color');
      record('background-color');
      record('background-image');
      record('box-shadow');
      for (const side of ['top', 'right', 'bottom', 'left']) {
        if (style.getPropertyValue(`border-${side}-width`) !== '0px') {
          record(`border-${side}-color`);
        }
      }
      if (style.getPropertyValue('outline-style') !== 'none') record('outline-color');
    };

    for (const element of document.querySelectorAll('*')) {
      collect(element, null);
      collect(element, '::before');
      collect(element, '::after');
    }
    return found;
  });
}

for (const route of ROUTES) {
  test.describe(route.path, () => {
    test('renders the surface inside the shell', async ({ page }) => {
      const response = await page.goto(route.path);

      expect(response?.status()).toBe(200);
      await expect(page.getByTestId('surface-title')).toHaveText(route.title);
      await expect(page.getByTestId(route.empty)).toContainText(route.headline);
      await expect(page.getByTestId('footer-readout')).toHaveText(FOOTER);
    });

    test('marks its rail item active and offers the whole rail', async ({ page }) => {
      await page.goto(route.path);

      await expect(page.getByTestId(route.nav)).toHaveAttribute('aria-current', 'page');
      for (const id of ['nav-workflows', 'nav-runs', 'nav-projects', 'nav-templates']) {
        await expect(page.getByTestId(id)).toBeVisible();
      }
      // nothing needs the Operator, so the amber count is not on the page at all
      await expect(page.getByTestId('nav-needs-you')).toHaveCount(0);
    });

    test('paints no amber and no red pixel', async ({ page }) => {
      await page.goto(route.path);

      const painted = await paintedColours(page);

      expect(painted.length).toBeGreaterThan(20);
      const signals = painted.filter(
        (entry) => entry.value.includes(AMBER) || entry.value.includes(RED),
      );
      expect(signals, JSON.stringify(signals)).toEqual([]);
    });
  });
}

test('the focus ring is the accent outline, on every focusable element in turn', async ({
  page,
}) => {
  await page.goto('/');

  // the rail is the first focusable region; four items plus whatever the surface offers
  for (let index = 0; index < 4; index += 1) {
    await page.keyboard.press('Tab');
    const focused = page.locator(':focus');

    await expect(focused).toHaveCSS('outline-color', ACCENT);
    await expect(focused).toHaveCSS('outline-style', 'solid');
    await expect(focused).toHaveCSS('outline-width', '1px');
    await expect(focused).toHaveCSS('outline-offset', '1px');
  }
});

test('every corner is square and nothing casts a shadow but the active rail marker', async ({
  page,
}) => {
  await page.goto('/');

  const shapes = await page.evaluate(() =>
    [...document.querySelectorAll('*')].map((element) => {
      const style = getComputedStyle(element);
      return {
        tag: element.tagName.toLowerCase(),
        radius: [
          style.borderTopLeftRadius,
          style.borderTopRightRadius,
          style.borderBottomLeftRadius,
          style.borderBottomRightRadius,
        ].join(' '),
        shadow: style.boxShadow,
      };
    }),
  );

  const rounded = shapes.filter((shape) => shape.radius !== '0px 0px 0px 0px');
  expect(rounded, JSON.stringify(rounded)).toEqual([]);

  const shadowed = shapes.filter((shape) => shape.shadow !== 'none');
  expect(shadowed.map((shape) => shape.shadow)).toEqual([
    `rgb(127, 212, 193) 2px 0px 0px 0px inset`,
  ]);
});
