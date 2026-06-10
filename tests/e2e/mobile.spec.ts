import { expect, test } from '@playwright/test';

const pages = ['/', '/publications.html', '/media.html', '/it.html', '/projects.html', '/diplomas.html'];

test.describe('mobile portfolio layout', () => {
  for (const path of pages) {
    test(`${path} has no horizontal overflow and localized header`, async ({ page }) => {
      await page.goto(path);
      await expect(page.locator('[data-header] .brand')).toBeVisible();
      await expect(page.locator('[data-lang-toggle]')).toBeVisible();
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
      expect(overflow).toBeLessThanOrEqual(2);
      await expect(page.getByRole('link', { name: /Книги|Видео|Фото|Books|Video|Photos/ })).toHaveCount(0);
    });
  }

  test('language toggle navigates to localized publications URL', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('lang', 'ru'));
    await page.goto('/publications.html');
    await expect(page.locator('html')).toHaveAttribute('lang', 'ru');
    await page.getByRole('button', { name: /Switch|Переключить|EN|RU/ }).click();
    await expect(page).toHaveURL(/\/en\/publications\.html$/);
    await expect(page.locator('html')).toHaveAttribute('lang', 'en');
    await expect(page.locator('#src-all')).toHaveText('All sources');
  });

  test('media cards without images use full width', async ({ page }) => {
    await page.goto('/media.html');
    const noImage = page.locator('#media-list .media-card.no-image').first();
    await expect(noImage).toBeVisible();
    const box = await noImage.boundingBox();
    expect(box?.width || 0).toBeGreaterThan(300);
  });

  test('published media records load into the dynamic media list', async ({ page }) => {
    await page.goto('/media.html');
    await page.waitForFunction(() => document.querySelectorAll('#media-list .media-card').length >= 20);
    await expect(page.locator('#media-list .note')).toHaveCount(0);
  });

  test('teaching lecture thumbnails render from local assets', async ({ page }) => {
    await page.goto('/teaching.html');
    const thumbs = page.locator('.teaching-lecture-thumb img');
    await expect(thumbs).toHaveCount(8);
    await expect(thumbs.first()).toHaveAttribute('src', /^assets\/teaching\/thumbs\//);
    for (let index = 0; index < 8; index += 1) {
      const thumb = thumbs.nth(index);
      await thumb.scrollIntoViewIfNeeded();
      await expect
        .poll(() => thumb.evaluate((img) => (img as HTMLImageElement).complete && (img as HTMLImageElement).naturalWidth > 0))
        .toBe(true);
    }
  });
});
