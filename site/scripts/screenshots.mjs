// SPDX-License-Identifier: AGPL-3.0-or-later
// Regenerate the README screenshots from a running preview server:
//   npm run build && npm run preview &   then   node scripts/screenshots.mjs
import { mkdirSync } from 'node:fs';
import { chromium, devices } from '@playwright/test';

const base = process.env.BASE_URL ?? 'http://localhost:4173/';
const out = new URL('../../docs/images/', import.meta.url).pathname;
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || undefined,
});

async function shoot(
  name,
  path,
  { theme = 'light', viewport = { width: 1440, height: 900 }, device, before } = {},
) {
  const context = await browser.newContext(
    device
      ? { ...devices[device], colorScheme: theme }
      : { viewport, deviceScaleFactor: 2, colorScheme: theme },
  );
  const page = await context.newPage();
  await page.goto(new URL(path, base).href, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  if (before) await before(page);
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}${name}.png` });
  await context.close();
  console.log(`wrote docs/images/${name}.png`);
}

await shoot('landing', './');
await shoot('results', './?service=CPT%3A70553', {
  before: async (page) => {
    const row = page.locator('ol.list > li').nth(1);
    await row.hover();
  },
});
await shoot('insurer', './?service=MS-DRG%3A470&payer=Northwind+Health&sort=payer');
await shoot('detail', './?service=CPT%3A74177', {
  before: async (page) => {
    await page.locator('ol.list > li button').nth(3).click();
    await page.waitForTimeout(700);
  },
});
await shoot('dark', './?service=CPT%3A45378', { theme: 'dark' });
await shoot('mobile', './?service=CPT%3A70553', { device: 'iPhone 13' });
await shoot('sql', './', {
  before: async (page) => {
    await page.getByRole('button', { name: 'SQL' }).click();
    await page.getByRole('button', { name: 'Run query' }).click();
    await page.locator('dialog table tbody tr').first().waitFor({ timeout: 45_000 });
  },
});
await browser.close();
