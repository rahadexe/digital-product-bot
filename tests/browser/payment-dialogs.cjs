/* Synthetic payment form geometry and shared-limit checks. No real writes. */
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const { chromium } = createRequire(resolve(__dirname, '../../console/package.json'))('@playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.BASE_URL || 'http://127.0.0.1:4173';
const output = process.env.ARTIFACT_DIR || '/tmp/dpb-payment-dialogs';
const methods = ['bKash', 'Nagad', 'Rocket', 'Binance'].map((name, index) => ({
  id: index + 1, name, account_info: '01900000000', instructions: 'Synthetic payment instructions.',
  min_deposit: index === 3 ? 1 : 50, account_type: index === 3 ? 'crypto' : 'personal',
  auto_verify: 'none', is_active: 1, sort_order: index + 1,
}));

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true,
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  const page = await browser.newPage();
  const errors = [];
  const writes = [];
  let rejectSave = true;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/api/admin/', '');
    if (route.request().method() !== 'GET') {
      writes.push({ path, payload: route.request().postDataJSON() });
      await new Promise(resolve => setTimeout(resolve, 350));
      return route.fulfill({ status: rejectSave ? 503 : 200, contentType: 'application/json',
        body: JSON.stringify(rejectSave ? { detail: 'Synthetic save failed. Try again.' } : { success: true }) });
    }
    let data = [];
    if (path === 'session') data = { signed_in: true, csrf: 'fixture', store_name: 'Sample Store' };
    if (path === 'settings') data = { store_name: 'Sample Store', currency: 'USD', currency_symbol: '$',
      usd_rate: '125', max_deposit_limit: '400', zinipay_api_key: 'synthetic-configured' };
    if (path === 'deposit-methods') data = methods;
    if (path === 'payments/status') data = { configured: true, enabled: true };
    if (path === 'suppliers/status') data = { providers: [], is_configured: false };
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
  });
  let count = 0;
  try {
    for (const [width, height] of [[320,640],[390,844],[760,900],[768,900],[1024,768],[1440,900],[1440,480],[667,375]]) {
      await page.setViewportSize({ width, height });
      await page.goto(`${base}/#settings/payments`);
      for (const method of methods) {
        await page.getByTitle(`Edit ${method.name}`, { exact: true }).click();
        const dialog = page.getByRole('dialog');
        await dialog.getByRole('heading', { name: `Edit ${method.name}`, exact: true }).waitFor();
        const geo = await dialog.evaluate(node => {
          const box = node.getBoundingClientRect();
          const footer = node.querySelector(':scope > footer');
          const row = node.querySelector('.pm-form-row');
          const columns = [...row.children].map(child => child.getBoundingClientRect());
          return { x: box.x, y: box.y, right: box.right, bottom: box.bottom,
            overflow: node.scrollWidth > node.clientWidth + 1,
            bodyOverflow: node.querySelector('.body').scrollWidth > node.querySelector('.body').clientWidth + 1,
            footerBottom: footer.getBoundingClientRect().bottom,
            radius: getComputedStyle(node).borderBottomLeftRadius,
            footerRadius: getComputedStyle(footer).borderBottomLeftRadius,
            oneColumn: Math.abs(columns[0].x - columns[1].x) < 1 && columns[1].y > columns[0].y };
        });
        assert.ok(geo.x >= -1 && geo.y >= -1 && geo.right <= width + 1 && geo.bottom <= height + 1, JSON.stringify(geo));
        assert.equal(geo.overflow || geo.bodyOverflow, false, `${method.name} ${width}: horizontal overflow`);
        assert.ok(geo.footerBottom <= height + 1, 'Save stays visible on short screens');
        assert.equal(geo.radius, geo.footerRadius, 'Footer follows modal corners');
        assert.equal(geo.oneColumn, width <= 760, 'Payment fields stack on phones and pair on desktop');
        const limit = dialog.locator('.pm-deposit-limit');
        assert.match(await limit.innerText(), method.name === 'Binance' ? /400 USDT/ : /50,000 BDT/);
        const minimum = dialog.getByLabel(/Minimum Deposit/);
        await minimum.fill(method.name === 'Binance' ? '401' : '50001');
        assert.equal(await minimum.evaluate(node => node.checkValidity()), false);
        await dialog.getByRole('button', { name: 'Save Changes', exact: true }).click();
        assert.equal(writes.length, 0, 'Out-of-range minimum cannot submit');
        await minimum.fill(method.name === 'Binance' ? '0.5' : '50');
        assert.equal(await minimum.evaluate(node => node.checkValidity()), true);
        if ((width === 1440 && height === 900 || width === 390) && method.name === 'Rocket') {
          await dialog.locator('.body').evaluate(node => node.scrollTop = 0);
          await page.screenshot({ path: `${output}/rocket-${width}.png` });
        }
        await page.keyboard.press('Escape');
        count++;
      }
    }
    await page.setViewportSize({ width: 320, height: 640 });
    await page.getByRole('button', { name: /Add Payment Method/ }).click();
    await page.locator('.pm-provider-select-card.binance').click();
    assert.ok(await page.getByRole('dialog').evaluate(node => node.scrollWidth <= node.clientWidth + 1), 'Provider presets fit 320px');
    await page.keyboard.press('Escape');
    await page.getByTitle('Edit bKash', { exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click();
    assert.ok(await page.getByRole('button', { name: 'Saving…', exact: true }).isDisabled());
    await page.getByRole('dialog').getByRole('alert').waitFor();
    assert.equal(writes.length, 1);
    rejectSave = false;
    await page.getByRole('dialog').getByRole('button', { name: 'Save Changes', exact: true }).click();
    await page.getByRole('dialog').waitFor({ state: 'hidden' });
    assert.equal(writes.length, 2);
    assert.equal(writes[1].payload.min_deposit, 50);
    assert.equal('max_deposit' in writes[1].payload, false, 'Shared cap is not duplicated into methods');
    assert.deepEqual(errors, []);
    fs.writeFileSync(`${output}/results.json`, JSON.stringify({ count, errors, fixtureData: true }, null, 2));
    console.log(`${count} payment dialog viewport checks, provider selection, minimum validation and save retry passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
