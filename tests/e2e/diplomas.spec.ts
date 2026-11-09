import { expect, test } from '@playwright/test';

for (const lang of ['ru', 'en']) {
  test(`${lang}: diploma order and multi-page viewer`, async ({ page }) => {
    await page.goto(lang === 'en' ? '/en/diplomas.html' : '/diplomas.html');
    const tiles = page.locator('#gallery .diploma-thumb img');
    await expect(tiles.nth(0)).toHaveAttribute('src', /2026-rudn-letter-of-appreciation\.webp$/);
    await expect(tiles.nth(1)).toHaveAttribute('src', /2026-mgimo-kve\.webp$/);
    await page.getByRole('button', { name: '2025', exact: true }).click();
    await expect(tiles.nth(-3)).toHaveAttribute('src', /2025-world-mbf\.webp$/);
    await expect(tiles.nth(-2)).toHaveAttribute('src', /2025-icasf\.webp$/);
    await expect(tiles.last()).toHaveAttribute('src', /2025-mgimo-visual-programming\.webp$/);

    const world = page.getByRole('button', { name: /WORLD-MBF/ });
    await expect(world.locator('img')).toHaveCount(1);
    await world.click();
    const viewer = page.locator('#modal');
    const pages = viewer.locator('#modal-pages img');
    await expect(viewer).toBeVisible();
    await expect(pages).toHaveCount(2);
    await expect(pages.first()).toHaveAttribute('src', 'assets/diplomas/full/2025-world-mbf.webp');
    await expect(pages.last()).toHaveAttribute('src', 'assets/diplomas/full/2025-world-mbf-p02.webp');
    await expect(pages.last()).toHaveAttribute('height', '1480');
    await expect.poll(() => pages.evaluateAll(imgs => imgs.every(img => (img as HTMLImageElement).naturalWidth > 0))).toBe(true);
    await pages.last().scrollIntoViewIfNeeded();
    await expect(pages.last()).toBeInViewport();
    await expect(viewer.locator('#modal-download')).toHaveAttribute('download', '2025-world-mbf.pdf');
    await viewer.getByRole('button', { name: lang === 'en' ? 'Close' : 'Закрыть' }).click();
    await expect(viewer).toBeHidden();

    await tiles.last().click();
    await expect(viewer).toBeVisible();
    await expect(pages).toHaveCount(1);
    await expect(viewer).not.toHaveClass(/diploma-modal--multipage/);
  });
}
