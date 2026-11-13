// SPDX-License-Identifier: AGPL-3.0-or-later
import { expect, test, type Page } from '@playwright/test';

/** Fail the test if the page talks to anything but our own origin. */
function guardThirdParty(page: Page): string[] {
  const external: string[] = [];
  page.on('request', (req) => {
    const url = new URL(req.url());
    if (!['localhost', '127.0.0.1'].includes(url.hostname) && url.protocol.startsWith('http')) {
      external.push(req.url());
    }
  });
  return external;
}

test.describe('Pricelight', () => {
  test('landing page shows the dataset and the demo notice', async ({ page }) => {
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1 })).toContainText(
      'Know what a hospital will charge',
    );
    await expect(page.getByRole('note')).toContainText('synthetic');
    await expect(page.locator('.stats dd').first()).not.toHaveText('0');
    await expect(page.getByRole('img', { name: /Map of \d+ hospitals/ })).toBeVisible();
  });

  test('search, filter, open a hospital and come back', async ({ page }) => {
    const external = guardThirdParty(page);
    await page.goto('/');
    const search = page.getByRole('combobox').first();
    await search.fill('colonoscopy biopsy');
    await expect(page.getByRole('option').first()).toContainText('Colonoscopy with biopsy');
    await search.press('Enter');

    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Colonoscopy with biopsy');
    await expect(page).toHaveURL(/service=CPT%3A45380/);
    const rows = page.locator('ol.list > li');
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(10);

    // cheapest cash price first
    const firstCash = await rows.nth(0).locator('.primary').innerText();
    const secondCash = await rows.nth(1).locator('.primary').innerText();
    const n = (s: string) => Number(s.replace(/[^0-9.]/g, ''));
    expect(n(firstCash)).toBeLessThanOrEqual(n(secondCash));

    // pick an insurer: list re-sorts by that insurer's rate
    await page.getByRole('combobox', { name: 'Insurer' }).selectOption('Northwind Health');
    await expect(page).toHaveURL(/payer=Northwind/);
    await expect(rows.first().locator('.secondary')).toHaveText('Northwind Health');

    // open the first hospital
    await rows.first().getByRole('button').click();
    await expect(page).toHaveURL(/hospital=/);
    await expect(page.getByRole('table')).toBeVisible();
    await expect(page.getByText('This is not a quote.')).toBeVisible();
    await expect(page.getByRole('row').filter({ hasText: 'Northwind Health' }).first()).toHaveClass(
      /mine/,
    );

    // browser back returns to the list
    await page.goBack();
    await expect(page.getByRole('heading', { level: 1 })).toHaveText('Colonoscopy with biopsy');
    expect(external).toEqual([]);
  });

  test('deep links restore state', async ({ page }) => {
    await page.goto('/?service=MS-DRG%3A470&sort=name');
    await expect(page.getByRole('heading', { level: 1 })).toContainText('Hip or knee replacement');
    await expect(page.getByRole('combobox', { name: 'Sort by' })).toHaveValue('name');
    const names = await page.locator('ol.list .name').allInnerTexts();
    expect(names).toEqual([...names].sort((a, b) => a.localeCompare(b)));
  });

  test('state filter narrows the list', async ({ page }) => {
    await page.goto('/?service=CPT%3A80053');
    await page.getByRole('combobox', { name: 'State' }).selectOption({ index: 1 });
    const state = await page.getByRole('combobox', { name: 'State' }).inputValue();
    const places = await page.locator('ol.list .where').allInnerTexts();
    expect(places.length).toBeGreaterThan(0);
    for (const place of places) expect(place.endsWith(`, ${state}`)).toBe(true);
  });

  test('SQL explorer runs DuckDB in the browser without network extensions', async ({ page }) => {
    const external = guardThirdParty(page);
    await page.goto('/');
    await page.getByRole('button', { name: 'SQL' }).click();
    await page.getByRole('button', { name: 'Run query' }).click();
    await expect(page.locator('dialog table tbody tr').first()).toBeVisible({ timeout: 45_000 });
    expect(await page.locator('dialog table tbody tr').count()).toBeGreaterThan(5);
    expect(external).toEqual([]);
  });

  test('about dialog explains the data', async ({ page }) => {
    await page.goto('/');
    await page.getByRole('button', { name: 'About' }).click();
    await expect(page.getByRole('dialog')).toContainText('45 CFR Part 180');
    await expect(page.getByRole('dialog')).toContainText(/Version \d+\.\d+\.\d+ · build/);
  });
});
