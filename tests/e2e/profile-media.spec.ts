import { expect, test } from '@playwright/test';

const leadStories = [
  'https://new.ras.ru/press-center/zasedanie-nts-kntr-demograficheskie-vyzovy-i-novye-mery-podderzhki-semey/',
  'https://isd-ras.ru/news/2026/10/zasedanie-nauchno-tehnicheskogo-soveta-ran/',
  'https://isd-ras.ru/news/2026/9/ekspertiza-novogo-nacproekta-semya/',
];

for (const lang of ['ru', 'en']) {
  const prefix = lang === 'en' ? '/en' : '';

  test(`${lang}: expert and press feeds stay separate and use the supplied photos`, async ({ page }) => {
    await page.goto(`${prefix}/media.html`);
    const cards = page.locator('#media-list .media-card');
    await expect(page.locator('#media-expert')).toBeChecked();
    await expect(cards.first().locator('h2 a')).toHaveAttribute('href', leadStories[0]);
    await expect(cards.locator(`h2 a[href="${leadStories[1]}"]`)).toHaveCount(0);
    const seminar = cards.filter({ has: page.locator('h2 a[href="https://uiec.ru/new_070425/"]') });
    for (const [card, src] of [
      [cards.first(), 'ras-council-2026-provided.png'],
      [seminar, 'uiec-settlement-seminar-2025.jpg'],
    ] as const) {
      const photo = card.locator('img');
      await expect(photo).toHaveAttribute('src', `assets/media/mentions/${src}`);
      await photo.scrollIntoViewIfNeeded();
      await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
    }
    for (const url of [
      'https://deminform.ru/news/institutu-sotsialnoy-demografii-prisvoyeno-imya-leonida-rybakovskogo',
      'https://t.me/tolk_tolk/28031',
    ]) {
      await expect(cards.locator(`h2 a[href="${url}"]`)).toHaveCount(1);
    }
    const expertUrls = await cards.locator('h2 a').evaluateAll(links => links.map(link => link.getAttribute('href')));
    await page.locator('label[for="media-press"]').click();
    await expect(page.locator('#media-press')).toBeChecked();
    const pressDuplicate = cards.filter({ has: page.locator(`h2 a[href="${leadStories[1]}"]`) });
    await expect(pressDuplicate).toBeVisible();
    await expect(pressDuplicate.locator('img')).toHaveAttribute('src', 'assets/media/mentions/ras-council-2026-provided.png');
    await expect(cards.locator(`h2 a[href="${leadStories[2]}"]`)).toBeVisible();
    const pressUrls = await cards.locator('h2 a').evaluateAll(links => links.map(link => link.getAttribute('href')));
    expect(pressUrls.filter(url => expertUrls.includes(url))).toEqual([]);
    expect(expertUrls.length + pressUrls.length).toBeGreaterThanOrEqual(29);
    await expect(cards.locator('.media-image img')).toHaveCount(pressUrls.length);
    await page.locator('label[for="media-expert"]').click();
    await expect(cards.first().locator('h2 a')).toHaveAttribute('href', leadStories[0]);
    await expect(cards.locator('.media-image img')).toHaveCount(expertUrls.length);
    const archive = page.locator('#risi-list .risi-card');
    await expect(archive).toHaveCount(13);
    await expect(archive.locator('.media-image img')).toHaveCount(13);
    await archive.locator('.media-image.is-illustration').first().click();
    await expect(page.locator('#risi-reader[open]')).toBeVisible();
  });

  test(`${lang}: career, leadership and dissertation details are current`, async ({ page }) => {
    await page.goto(`${prefix}/`);
    const career = page.locator('#career details');
    await career.nth(0).locator('summary').click();
    const fnisc = career.nth(0).locator('.career-role');
    await expect(fnisc.nth(2).locator(`span.${lang}`).first()).toContainText(
      lang === 'en' ? 'Junior Research Fellow' : 'Младший научный сотрудник',
    );
    await career.nth(1).locator('summary').click();
    const rudn = career.nth(1).locator('.career-role');
    await expect(rudn.first().locator(`.career-tag.${lang}`)).toHaveText(
      lang === 'en' ? 'primary appointment' : 'основное место работы',
    );
    await expect(rudn.nth(1).locator('.career-date')).toHaveText('10.2024–08.2026');

    await expect(page.locator('#leadership + #grants')).toBeAttached();
    const leadership = page.locator('#leadership .leadership-entry');
    await expect(leadership).toHaveCount(2);
    for (const entry of await leadership.all()) {
      const logo = entry.locator('img');
      await expect(logo).toBeVisible();
      await logo.scrollIntoViewIfNeeded();
      await expect.poll(() => logo.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
    }
    const education = page.locator(`#education .education-list.${lang} .education-item`).first();
    await expect(education.locator('.education-year')).toHaveText('2026');
    await expect(education.locator('.education-kind')).toContainText(lang === 'en' ? 'defence' : 'Защита');
  });
}
