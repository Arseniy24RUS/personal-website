import { expect, test } from '@playwright/test';

const leadStories = [
  'https://new.ras.ru/press-center/zasedanie-nts-kntr-demograficheskie-vyzovy-i-novye-mery-podderzhki-semey/',
  'https://isd-ras.ru/news/2026/10/zasedanie-nauchno-tehnicheskogo-soveta-ran/',
  'https://isd-ras.ru/news/2026/9/ekspertiza-novogo-nacproekta-semya/',
];

for (const lang of ['ru', 'en']) {
  const prefix = lang === 'en' ? '/en' : '';

  test(`${lang}: featured media keep their order ahead of newer articles`, async ({ page }) => {
    await page.goto(`${prefix}/media.html`);
    const cards = page.locator('#media-list .media-card');
    for (const [index, url] of leadStories.entries()) {
      const card = cards.nth(index);
      await expect(card.locator('h2 a')).toHaveAttribute('href', url);
      const photo = card.locator('img');
      await photo.scrollIntoViewIfNeeded();
      await expect.poll(() => photo.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBeGreaterThan(0);
    }
    for (const url of [
      'https://deminform.ru/news/institutu-sotsialnoy-demografii-prisvoyeno-imya-leonida-rybakovskogo',
      'https://t.me/tolk_tolk/28031',
    ]) {
      await expect(cards.locator(`h2 a[href="${url}"]`)).toHaveCount(1);
    }
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
