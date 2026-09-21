import { expect, test } from '@playwright/test';

const featured = ['digital-demographic-observatory', 'github-1298698239'];

for (const language of ['ru', 'en'] as const) {
  test(`IT resources retain every card and show localized ${language} content`, async ({ page, request }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const resources = await (await request.get('/data/it/resources.json')).json();
    const baseline = await (await request.get('/data/it/retention_baseline.json')).json();
    const path = language === 'en' ? '/en/it.html' : '/it.html';
    await page.goto(path);
    await expect(page.locator('html')).toHaveAttribute('lang', language);
    await expect(page).toHaveTitle(language === 'en' ? /IT Resources/ : /ИТ-ресурсы/);
    await expect(page.locator('.it-card')).toHaveCount(resources.items.length);
    expect(resources.items.length).toBeGreaterThanOrEqual(26);
    expect(await page.locator('#it-featured .it-card').evaluateAll(cards => cards.map(card => card.getAttribute('data-resource-id')))).toEqual(featured);
    const rendered = await page.locator('.it-card').evaluateAll(cards => cards.map(card => card.getAttribute('data-resource-id')));
    expect(rendered.slice(0, 2)).toEqual(featured);
    const oldIds = new Set(baseline.items.map((item: {id: string}) => item.id));
    expect(rendered.filter(id => oldIds.has(id))).toEqual(baseline.items.map((item: {id: string}) => item.id));
    for (const item of resources.items) {
      const card = page.locator(`[data-resource-id="${item.id}"]`);
      await expect(card.locator('h2')).toHaveText(item[`title_${language}`]);
      await expect(card.locator('p')).toHaveText(item[`description_${language}`]);
      await expect(card.locator('.it-link')).toHaveAttribute('href', item.url);
      await expect(card.locator('img')).toHaveAttribute('alt', item[`title_${language}`]);
      await card.locator('img').scrollIntoViewIfNeeded();
      await expect.poll(() => card.locator('img').evaluate(img => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0)).toBe(true);
    }
    if (language === 'en') expect((await page.locator('.it-card').allInnerTexts()).join(' ')).not.toMatch(/[\u0400-\u04FF]/);
    expect(errors).toEqual([]);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(2);
  });
}

test('featured cards use whole images and switch layout with the viewport', async ({ page }) => {
  await page.goto('/it.html');
  await expect(page.locator('#it-featured .it-card')).toHaveCount(2);
  const horizontal = (page.viewportSize()?.width || 0) > 760;
  for (const id of featured) {
    const card = page.locator(`[data-resource-id="${id}"]`);
    const image = card.locator('.it-thumb');
    const text = card.locator('.it-body');
    const imageBox = await image.boundingBox();
    const textBox = await text.boundingBox();
    expect(imageBox).not.toBeNull(); expect(textBox).not.toBeNull();
    if (horizontal) expect(textBox!.x).toBeGreaterThanOrEqual(imageBox!.x + imageBox!.width - 1);
    else expect(textBox!.y).toBeGreaterThanOrEqual(imageBox!.y + imageBox!.height - 1);
    await expect(card.locator('img')).toHaveCSS('object-fit', 'contain');
    await card.hover();
    await expect(card.locator('img')).toHaveCSS('transform', 'none');
  }
  await expect(page.locator('#it-list .it-card--featured')).toHaveCount(0);
  await expect(page.locator('[data-resource-id="settlements-projection-dashboard"] img')).toHaveCSS('object-fit', 'cover');
  await expect(page.locator('[data-resource-id="settlements-projection-dashboard"]')).toHaveCSS('flex-direction', 'column');
});

test('language switch keeps the same featured projects and their target links', async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem('lang', 'ru'));
  await page.goto('/it.html');
  await page.locator('[data-lang-toggle]').click();
  await expect(page).toHaveURL(/\/en\/it\.html$/);
  await expect(page.locator('#it-featured h2')).toHaveText(['Digital Demographic Observatory', 'GIR — Global Index Research Platform']);
  await expect(page.locator('#it-featured .it-link').nth(0)).toHaveAttribute('href', 'https://digitaldemography.ru/');
  await expect(page.locator('#it-featured .it-link').nth(1)).toHaveAttribute('href', 'https://gir.digitaldemography.ru/');
});
