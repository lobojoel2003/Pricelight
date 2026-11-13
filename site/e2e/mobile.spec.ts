// SPDX-License-Identifier: AGPL-3.0-or-later
import { expect, test } from '@playwright/test';

test('works on a phone', async ({ page }) => {
  await page.goto('/');
  await page
    .getByRole('button', { name: /MRI of the brain/ })
    .first()
    .click();
  await expect(page.locator('ol.list > li').first()).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth > window.innerWidth + 1,
  );
  expect(overflow).toBe(false);
});
