/* Geometry and clipboard regressions for small, real-world mobile data sets.
 * Every API response is synthetic. No live admin account or payment call is used.
 */
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const { chromium } = createRequire(resolve(__dirname, '../../console/package.json'))('@playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173';
const output = process.env.ARTIFACT_DIR || '/tmp/dpb-layout-quality';
const baseline = process.env.CAPTURE_BASELINE === '1';

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}),
    headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.addInitScript(() => Object.defineProperty(navigator, 'clipboard', {
      configurable: true, value: { writeText: async text => { window.__copiedText = text; } },
    }));
    let count = 1;
    let pendingDeposits = 0;
    let customerInput = 'sample18169@example.test';
    const order = () => ({
      id: 1001, user_id: 1, tg_user_id: 123, first_name: 'Sample Customer', username: 'sample_customer',
      product_id: 1, product_title: 'Premium subscription', price: 99, status: 'completed',
      fulfillment: 'waiting', source: 'manual', created_at: '2026-10-17T08:00:00Z',
      customer_input: customerInput, delivered_item: '', duration_label: '12 months',
    });
    await page.route('**/api/**', async route => {
      const req = route.request();
      assert.equal(req.method(), 'GET', 'Geometry tests must not submit any admin mutations');
      const path = new URL(req.url()).pathname.split('/admin/')[1];
      let body = [];
      if (path === 'session') body = { signed_in: true, csrf: 'synthetic-test-csrf', store_name: 'Sample Store' };
      else if (path === 'settings') body = { currency: 'BDT', currency_symbol: '৳', store_name: 'Sample Store', validity_presets: '12 months' };
      else if (path === 'suppliers/status') body = { is_configured: false, providers: [] };
      else if (path === 'overview') body = {
        total_users: count ? 1 : 0, total_orders: count, total_revenue: count * 99,
        available_stock: 0, waiting_orders: count, pending_deposits: pendingDeposits,
        chart_data: [], stock_summary: [],
        recent_orders: Array.from({ length: count }, (_, i) => ({ ...order(), id: 1001 + i })),
      };
      else if (/^orders\/\d+$/.test(path)) body = { order: order(), stock_item: null, messages: [] };
      else if (path === 'orders') body = { orders: [order()], total: 1, waiting: 1, summary: {} };
      else if (path === 'inventory') body = { items: [], total: 0, summary: { available_units: 0, sold_units: 0, expired_units: 0, in_stock_products: 0 } };
      else if (path === 'deposits') body = { deposits: [], total: 0, summary: { pending_count: 0, total_completed_amount: 0, pending_amount: 0, today_amount: 0 } };
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    });
    const checks = [];
    for (const width of [320, 360, 390, 412, 760, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 860 });
      for (const total of [0, 1, 5]) {
        count = total;
        await page.goto(`${baseURL}/#overview`);
        await page.reload();
        await page.locator(baseline ? '.recent-orders' : '.home-recent').waitFor();
        await page.waitForTimeout(100);
        if (width === 390 && total === 1) await page.screenshot({ path: `${output}/home-${baseline ? 'before' : 'after'}.png` });
        if (baseline) continue;
        assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Home fits ${width}`);
        const header = await page.locator('.home-recent > header').boundingBox();
        const heading = await page.getByRole('heading', { name: 'Recent orders', exact: true }).boundingBox();
        const viewAll = await page.getByRole('button', { name: 'View all', exact: true }).boundingBox();
        assert.ok(header.height <= 64, `Recent order header is compact at ${width}: ${header.height}`);
        assert.ok(viewAll.width < header.width * .45, 'View all is not a full-width toolbar');
        assert.ok(Math.abs((heading.y + heading.height / 2) - (viewAll.y + viewAll.height / 2)) < 10, 'Title and View all stay on one line');
        assert.ok(viewAll.height >= 44, 'View all retains a touch target');
        const metrics = await page.locator('.home-metric').evaluateAll(nodes => nodes.map(node => {
          const r = node.getBoundingClientRect(); return { x: r.x, y: r.y, height: r.height };
        }));
        assert.equal(metrics.length, 4);
        if (width <= 760) {
          assert.equal(Math.round(metrics[0].y), Math.round(metrics[1].y), 'Metrics use two compact columns');
          assert.ok(metrics.every(item => item.height <= 120), 'Metric cards do not contain empty vertical space');
          assert.ok(await page.getByRole('navigation', { name: 'Quick navigation' }).getByRole('button', { name: 'Stock', exact: true }).isVisible());
        }
        if (total) {
          const row = await page.locator('.home-order').first().boundingBox();
          assert.ok(row.height <= 105 && row.height >= 64, `Recent order row stays compact: ${row.height}`);
          assert.ok(row.y - header.y - header.height < 8, 'No gap before the first order');
        }
        await page.locator('.home-revenue > summary').click();
        assert.ok(await page.locator('.home-revenue[open]').isVisible(), 'Revenue remains accessible');
        checks.push({ width, orders: total });
      }
      if (baseline) continue;
      for (const text of ['sample18169@example.test', `${'longcustomer'.repeat(12)}@example.test`, 'Name: Sample Customer\nEmail: sample@example.test\nPlan: 12 months']) {
        customerInput = text;
        await page.goto(`${baseURL}/#orders/1001`);
        await page.reload();
        await page.getByRole('button', { name: 'Copy customer info', exact: true }).waitFor();
        const button = page.getByRole('button', { name: 'Copy customer info', exact: true });
        const row = await button.boundingBox();
        const parent = await page.locator('.order-detail-customer').boundingBox();
        assert.ok(row.width >= parent.width - 2, 'Customer input uses the entire row');
        assert.ok(row.height >= 44, 'Copy customer input is touch accessible');
        assert.equal(await button.locator('span').innerText(), text, 'Customer data is not rewritten');
        await button.click();
        assert.equal(await page.evaluate(() => window.__copiedText), text, 'Copy preserves the exact customer input');
        const overflow = await button.evaluate(node => node.scrollWidth > node.clientWidth + 1);
        assert.equal(overflow, false, 'Long and multiline customer input fits without clipping');
        const customer = await page.getByRole('dialog').getByText('Sample Customer', { exact: true }).boundingBox();
        assert.ok(customer.height < 32, 'Customer name has a usable value column');
        const emptyCard = page.locator('.order-modal-cred-card:has(.order-not-delivered)');
        const emptyCardBox = await emptyCard.boundingBox();
        const noteBox = await emptyCard.locator('.order-not-delivered').boundingBox();
        assert.ok(noteBox.y + noteBox.height <= emptyCardBox.y + emptyCardBox.height + 1, `Empty credentials text stays inside its card: ${JSON.stringify({ width, emptyCardBox, noteBox })}`);
        if (text.length < 40 && !text.includes('\n')) {
          const height = await button.locator('span').evaluate(node => node.getBoundingClientRect().height);
          if (height >= 30) {
            await page.screenshot({ path: `${output}/input-wrap-${width}.png` });
            console.log(await button.evaluate(node => ({
              viewport: innerWidth, width: node.getBoundingClientRect().width,
              textWidth: node.querySelector('span').getBoundingClientRect().width,
              font: getComputedStyle(node.querySelector('span')).font,
              ancestors: [...(function* () { let p = node.parentElement; while (p && !p.classList.contains('modal-backdrop')) { yield p; p = p.parentElement; } })()].map(p => ({ class: p.className, width: p.getBoundingClientRect().width, padding: getComputedStyle(p).padding })),
            })));
          }
          assert.ok(height < 30, `A normal email stays on one line at ${width}px`);
          if (width === 390) {
            await page.mouse.move(0, 0);
            await page.screenshot({ path: `${output}/order-input-after.png` });
          }
        }
        await page.keyboard.press('Escape');
      }
    }
    if (baseline) {
      console.log('Captured existing small-store Home layout at eight widths; no new-layout assertions run.');
      return;
    }
    await page.setViewportSize({ width: 390, height: 860 });
    await page.goto(`${baseURL}/#overview`);
    await page.getByRole('navigation', { name: 'Quick navigation' }).getByRole('button', { name: 'Stock', exact: true }).click();
    await page.waitForURL('**/#inventory');
    await page.getByRole('button', { name: 'More navigation' }).click();
    await page.getByRole('dialog', { name: 'Mobile navigation' }).getByRole('button', { name: 'Deposits', exact: true }).click();
    await page.waitForURL('**/#deposits');
    pendingDeposits = 1;
    await page.goto(`${baseURL}/#overview`);
    await page.reload();
    await page.getByRole('navigation', { name: 'Pending work' }).getByRole('button', { name: /Deposits/ }).click();
    await page.waitForURL('**/#deposits');
    assert.equal(errors.length, 0, `Browser errors: ${errors.join('; ')}`);
    fs.writeFileSync(`${output}/results.json`, JSON.stringify({ homeCases: checks, inputCases: 24, navigation: 'passed', browserErrors: errors }, null, 2));
    console.log(`${checks.length} Home states, 24 exact-copy customer input cases and Stock/Deposits navigation passed.`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
