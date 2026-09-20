import { expect, test } from '@playwright/test';

const pages = ['/', '/publications.html', '/media.html', '/it.html', '/projects.html', '/diplomas.html'];
const cyrillic = /[\u0400-\u04FF]/;

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

  test('media cards survive invalid primary JSON by using fallback data', async ({ page }) => {
    const invalidJson = '<<<<<<< Updated upstream\n{}\n=======\n{}\n>>>>>>> Stashed changes\n';
    await page.route('**/data/media/published.json', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: invalidJson,
    }));
    await page.route('**/data/media/news_mentions.json', route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: invalidJson,
    }));
    await page.goto('/media.html');
    await page.waitForFunction(() => document.querySelectorAll('#media-list .media-card').length >= 20);
    await expect(page.locator('#media-list .note')).toHaveCount(0);
  });

  test('English media cards render translated dynamic text', async ({ page }) => {
    await page.goto('/en/media.html');
    await page.waitForFunction(() => document.querySelectorAll('#media-list .media-card').length >= 20);
    await expect(page.locator('#media-list .note')).toHaveCount(0);
    for (const card of await page.locator('#media-list .media-card:not([data-translation-status="pending"])').all()) {
      expect(await card.innerText()).not.toMatch(cyrillic);
    }
    for (const card of await page.locator('#media-list .media-card[data-translation-status="pending"]').all()) {
      await expect(card.locator('.media-translation-note')).toContainText('English translation pending');
    }
    expect(await page.locator('#media-list .media-card').count()).toBeGreaterThanOrEqual(22);
    await expect(page.getByRole('link', { name: /Tolk: Russia.s shrinking younger population/ })).toBeVisible();
  });

  test('new Russian media remains visible with an explicit pending English translation', async ({ page }) => {
    const record = {
      id: 'pending-fixture', url: 'https://example.org/academic-news',
      title: 'Новая научная публикация', title_ru: 'Новая научная публикация',
      description_ru: 'Информация о новом исследовании Арсения Ситковского.',
      source_name: 'Научный институт',
      translation_state: { status: 'pending', fields: ['title_en', 'description_en', 'source_name_en'], reason: 'model_unavailable' },
    };
    await page.route('**/data/media/published.json', route => route.fulfill({
      contentType: 'application/json', body: JSON.stringify({ records: [record] }),
    }));
    await page.goto('/en/media.html');
    await expect(page.locator('#media-list h2')).toHaveText(record.title_ru);
    await expect(page.locator('.media-translation-note')).toContainText('English translation pending');
    await expect(page.locator('#media-list .media-link')).toHaveAttribute('href', record.url);
    await page.goto('/media.html');
    await expect(page.locator('#media-list h2')).toHaveText(record.title_ru);
    await expect(page.locator('.media-translation-note')).toHaveCount(0);
  });

  for (const path of ['/media.html', '/en/media.html']) {
    test(`${path} retains the archive and displays both September news items`, async ({page}) => {
      await page.goto(path);
      for (const suffix of ['pervaya-zashchita-dissovet-24124405-2026', 'sitkovskij-zashhitil-kandidatskuyu-dissertaciyu/']) {
        await expect(page.locator(`#media-list h2 a[href$="${suffix}"]`)).toBeVisible();
      }
      await expect(page.locator('#risi-archive')).toBeVisible();
    });
  }

  test('publication search works without public collector diagnostics', async ({page}) => {
    await page.goto('/publications.html');
    await expect(page.locator('#count')).toHaveText(/^[1-9]\d*$/);
    const total = Number(await page.locator('#count').textContent());
    await page.locator('#q').fill('10.17853/1994-5639-2026-1-33-64');
    await expect.poll(async () => Number(await page.locator('#count').textContent())).toBeGreaterThan(0);
    await expect.poll(async () => Number(await page.locator('#count').textContent())).toBeLessThan(total);
    await expect(page.locator('.pub-row').first()).toContainText(/Сравнительный|Comparative/);
    await expect(page.locator('[data-source-health]')).toHaveCount(0);
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

  test('English teaching lecture titles render without Cyrillic', async ({ page }) => {
    await page.goto('/en/teaching.html');
    const details = page.locator('.teaching-lecture-details');
    if (!(await details.evaluate((node) => (node as HTMLDetailsElement).open))) {
      await details.locator('summary').click();
    }
    const titles = await page.locator('.teaching-lecture-title').allInnerTexts();
    expect(titles).toHaveLength(8);
    expect(titles).toContain('Institutional foundations of public and municipal administration');
    expect(titles).toContain('How to become successful');
    expect(titles.join(' ')).not.toMatch(cyrillic);
  });
});
