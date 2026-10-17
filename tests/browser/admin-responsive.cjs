/* Optional browser regression suite.
 * Requires @playwright/test in the test environment and a served console build.
 * BASE_URL=http://127.0.0.1:4173 CHROMIUM_PATH=/path/to/chromium node tests/browser/admin-responsive.cjs
 * API calls are intercepted with synthetic fixtures. No production data is used.
 */
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const { chromium } = createRequire(resolve(__dirname, '../../console/package.json'))('@playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const baseURL = process.env.BASE_URL || 'http://127.0.0.1:4173';
const output = process.env.ARTIFACT_DIR || '/tmp/dpb-admin-design';
const product = {
  id: 1, title: 'Premium subscription with a deliberately long product name',
  description: 'Synthetic test product', category_id: 1, category_name: 'Subscriptions',
  price: 150, reseller_price: 120, duration_label: '1 month', warranty_label: 'Full warranty',
  icon: '', custom_emoji_id: '', sort_order: 0, is_active: 1, is_pinned: 0,
  delivery_type: 'stock', stock: 3, upstream_product_id: null, supplier_code: null,
  requires_customer_input: false, customer_input_prompt: '',
};
const summary = {
  total_orders: 28, total_revenue: 4200, delivered_orders: 26, waiting_orders: 2,
  total_users: 19, total_balance: 500, with_balance_count: 3, banned_count: 0,
  total_completed_amount: 150, pending_count: 1, pending_amount: 125, today_amount: 150,
};
const customer = {
  id: 1, tg_user_id: 123, first_name: 'A very long customer name for mobile testing',
  username: 'synthetic_customer', balance: 500, total_spent: 150, rank: 'Customer',
  is_banned: 0, created_at: '2026-10-17T08:00:00Z',
};
const order = {
  id: 42, user_id: 1, tg_user_id: 123, first_name: customer.first_name,
  product_id: 1, product_title: product.title, price: 150, delivered_item: '',
  status: 'completed', fulfillment: 'waiting', source: 'manual', created_at: customer.created_at,
  customer_input: 'synthetic.customer.with.a.long.address@example.test',
};
const deposit = {
  id: 19, user_id: 1, tg_user_id: 123, first_name: customer.first_name, method_id: 1,
  method_name: 'bKash', amount: 125, transaction_id: 'SYNTHETICTRX1234567890',
  status: 'pending', created_at: customer.created_at, auto_verify: 'none',
};

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
    let signedIn = true;
    let failSave = false;
    let savedPayload;
    let products = [{ ...product }];
    let longName = false;
    let failOverview = false;
    let emptyOverview = false;
    await page.route('**/api/**', async route => {
      const req = route.request();
      const path = new URL(req.url()).pathname.replace('/api/admin/', '');
      let body = [];
      if (path === 'session') body = { signed_in: signedIn, csrf: 'synthetic-test-csrf', store_name: longName ? 'A deliberately very long digital storefront name for narrow screen testing' : 'Digital Store' };
      else if (path === 'settings') body = { currency_symbol: '৳', store_name: longName ? 'A deliberately very long digital storefront name for narrow screen testing' : 'Digital Store', validity_presets: '1 month,1 year', admin_tg_ids: '', usd_rate: '125', currency: 'BDT' };
      else if (path === 'products' && req.method() === 'GET') body = products;
      else if (path.startsWith('products') && ['POST', 'PUT'].includes(req.method())) {
        savedPayload = req.postDataJSON();
        if (failSave) return route.fulfill({ status: 422, contentType: 'application/json', body: JSON.stringify({ detail: 'Test validation error' }) });
        products = [{ ...product, ...savedPayload, id: 2 }];
        body = { success: true, id: 2 };
      }
      else if (path === 'categories') body = [{ id: 1, name: 'Subscriptions', icon: '', sort_order: 0, is_active: 1 }];
      else if (path === 'overview') {
        if (failOverview) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Test dashboard error' }) });
        body = {
          ...summary, available_stock: 3, pending_deposits: 1,
          ...(emptyOverview ? { total_users: 0, total_orders: 0, total_revenue: 0, waiting_orders: 0, pending_deposits: 0 } : {}),
          chart_data: [], stock_summary: [],
          recent_orders: emptyOverview ? [] : [{ id: 42, user_id: 1, tg_user_id: 123, first_name: 'A very long customer name that should never overflow the screen', product_title: product.title, price: 150, status: 'completed', fulfillment: 'waiting', source: 'manual', created_at: '2026-10-17T08:00:00Z' }],
        };
      }
      else if (path === 'orders') body = { orders: [order], total: 1, waiting: 2, summary };
      else if (path === 'deposits') body = { deposits: [deposit], total: 1, summary };
      else if (path === 'users') body = { users: [customer], total: 1, summary };
      else if (path === 'inventory') body = { items: [], total: 0, summary: { total: 0, available: 0, sold: 0, expired: 0 } };
      else if (path === 'emojis') body = { system: [], custom: [], all: [] };
      else if (path === 'reseller-applications') body = { applications: [], total: 0, summary: { pending: 0, approved: 0, rejected: 0 } };
      else if (path === 'suppliers/status') body = { is_configured: false, connected: false, providers: [], base_url: '', balance: null };
      else if (path === 'audit-logs') body = { entries: [], total: 0, actions: [] };
      else if (path === 'payments/status') body = { enabled: false, configured: false };
      else if (path === 'broadcast') body = { recipient_count: 0, recent: [] };
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    });
    const results = [];
    const screens = ['overview', 'orders', 'deposits', 'users', 'products', 'suppliers', 'inventory', 'categories', 'validities', 'emojis', 'broadcast', 'reseller-apps', 'activity', 'settings'];
    for (const width of [320, 390, 760, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const screen of screens) {
        await page.goto(`${baseURL}/#${screen}`);
        await page.locator('.main-inner').waitFor();
        await page.waitForTimeout(100);
        const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
        assert.ok(dimensions.document <= dimensions.viewport + 1, `${screen} overflows at ${width}px: ${dimensions.document}`);
        if (width <= 760 && ['orders', 'deposits', 'products', 'users'].includes(screen)) {
          const rows = page.locator('.main-inner table tbody tr:not(.empty-row)');
          await rows.first().waitFor();
          assert.equal(await rows.first().evaluate(el => getComputedStyle(el).display), 'grid', `${screen} uses populated mobile cards`);
        }
        if (width <= 760 && screen === 'orders') {
          const geometry = await page.locator('.orders-directory tbody tr').first().evaluate(row => {
            const cell = label => row.querySelector(`[data-label="${label}"]`).getBoundingClientRect();
            const product = cell('Product'), buyer = cell('Buyer'), status = cell('Status'), id = cell('Order');
            const details = row.querySelector('.order-customer-input').getBoundingClientRect();
            return {
              productBottom: product.bottom, buyerTop: buyer.top,
              detailsBottom: details.bottom, detailsTop: details.top,
              orderTop: id.top, statusTop: status.top,
              rowHeight: row.getBoundingClientRect().height,
              inputFits: row.querySelector('.order-customer-input').scrollWidth <= details.width + 1,
            };
          });
          assert.ok(geometry.buyerTop >= geometry.productBottom + 8, 'Buyer clears product cell');
          assert.ok(geometry.buyerTop >= geometry.detailsBottom + 8, 'Customer details never overlap buyer');
          assert.ok(Math.abs(geometry.orderTop - geometry.statusTop) <= 12, 'Order and status share the first row');
          assert.ok(geometry.inputFits, 'Long customer details wrap inside the card');
          assert.ok(geometry.rowHeight < 420, 'Populated order stays compact');
        }
        results.push({ screen, width, ...dimensions });
      }
      console.log(`Passed all 14 screens at ${width}px`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    for (const screen of ['orders', 'products', 'deposits']) {
      await page.goto(`${baseURL}/#${screen}`);
      await page.locator('.main-inner table tbody tr').first().waitFor();
      await page.waitForTimeout(150);
      assert.equal(await page.locator('.mobile-app-heading h1').innerText(), screen[0].toUpperCase() + screen.slice(1));
      assert.equal(await page.locator('.main-inner > .page-head').isVisible(), false, 'App bar replaces repeated desktop heading');
      await page.screenshot({ path: `${output}/${screen}-mobile.png`, fullPage: true });
      if (screen === 'products' || screen === 'orders') {
        const filterButton = page.getByRole('button', { name: screen === 'products' ? 'Product filters' : 'Order filters', exact: true });
        const extras = page.locator(screen === 'products' ? '#product-extra-filters' : '#order-date-filter');
        assert.equal(await extras.isVisible(), false, 'Extra filters stay out of the default mobile list');
        await filterButton.click();
        assert.equal(await extras.isVisible(), true, 'Extra filters remain accessible');
        assert.equal(await filterButton.getAttribute('aria-expanded'), 'true');
        await filterButton.click();
        if (screen === 'products') {
          const inputRect = await page.getByRole('searchbox', { name: 'Search products' }).boundingBox();
          const buttonRect = await filterButton.boundingBox();
          assert.ok(Math.abs(inputRect.y - buttonRect.y) <= 3, 'Search and filters share one compact app-toolbar row');
        }
      }
    }
    const originalOrder = { ...order };
    Object.assign(order, { id: 1001, product_title: 'Gemini Pro', first_name: 'Demo Customer', customer_input: 'demo@example.test', price: 99 });
    await page.goto(`${baseURL}/#orders`);
    await page.reload();
    await page.getByRole('button', { name: 'Gemini Pro', exact: true }).waitFor();
    await page.screenshot({ path: `${output}/orders-mobile-preview.png`, fullPage: true });
    Object.assign(order, { customer_input: '', status: 'completed', fulfillment: 'delivered', delivery_status: 'failed' });
    await page.reload();
    await page.getByText('message failed', { exact: true }).waitFor();
    assert.equal(await page.locator('.order-customer-input').count(), 0, 'No empty customer-details block');
    assert.ok(await page.getByRole('button', { name: 'Details', exact: true }).isVisible(), 'Completed order keeps its details action');
    Object.assign(order, originalOrder);
    await page.goto(`${baseURL}/#overview`);
    await page.locator('.attention-banner').waitFor();
    await page.mouse.move(0, 0);
    await page.screenshot({ path: `${output}/dashboard-mobile.png`, fullPage: true });
    assert.equal(await page.locator('.overview-metric').count(), 4);
    assert.equal(await page.locator('.overview-orders tbody tr').first().evaluate(el => getComputedStyle(el).display), 'grid');
    await page.getByRole('button', { name: 'More navigation' }).click();
    const drawer = page.getByRole('dialog', { name: 'Mobile navigation' });
    await drawer.waitFor();
    await page.waitForFunction(() => {
      const rect = document.querySelector('#mobile-navigation').getBoundingClientRect();
      return Math.abs(rect.bottom - innerHeight) <= 1;
    });
    const sheet = await drawer.boundingBox();
    assert.ok(Math.abs(sheet.y + sheet.height - 844) <= 1, 'Navigation opens as a bottom sheet');
    await page.screenshot({ path: `${output}/navigation-mobile.png` });
    assert.equal(await page.locator('main').evaluate(el => el.inert), true);
    const drawerScroll = await drawer.locator('.drawer-nav').evaluate(el => {
      el.scrollTop = el.scrollHeight;
      return { scrollTop: el.scrollTop, touchAction: getComputedStyle(el.closest('.drawer-panel')).touchAction };
    });
    assert.ok(drawerScroll.scrollTop > 0, 'Long drawer navigation can scroll on mobile');
    assert.equal(drawerScroll.touchAction, 'pan-y');
    await drawer.getByRole('button', { name: 'Sign out' }).focus();
    await page.keyboard.press('Tab');
    assert.equal(await drawer.evaluate(el => el.contains(document.activeElement)), true, 'Tab stays inside drawer');
    await page.keyboard.press('Escape');
    await drawer.waitFor({ state: 'hidden' });
    assert.equal(await page.locator('main').evaluate(el => el.inert), false);
    assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'More navigation');
    await page.getByRole('button', { name: 'More navigation' }).click();
    await drawer.getByRole('button', { name: 'Settings', exact: true }).click();
    await page.waitForURL('**/#settings');
    await drawer.waitFor({ state: 'hidden' });
    await page.getByRole('button', { name: 'More navigation' }).click();
    await page.setViewportSize({ width: 1024, height: 900 });
    await drawer.waitFor({ state: 'hidden' });
    assert.equal(await page.locator('main').evaluate(el => el.inert), false, 'Resize releases background lock');
    assert.equal(await page.locator('.rail').isVisible(), true);
    await page.setViewportSize({ width: 768, height: 900 });
    assert.equal(await page.locator('.rail').isVisible(), true, 'Tablet keeps working navigation');
    assert.equal(await page.locator('.mobile-header').isVisible(), false, 'Tablet does not duplicate the header');

    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto(`${baseURL}/#products`);
    await page.locator('.products-list').waitFor();
    await page.getByRole('button', { name: /new product/i }).first().click();
    const dialog = page.getByRole('dialog', { name: 'New product' });
    await dialog.waitFor();
    const formMetrics = await dialog.evaluate(el => ({
      client: el.querySelector('.body').clientWidth, scroll: el.querySelector('.body').scrollWidth,
      footer: el.querySelector('footer').getBoundingClientRect().bottom, viewport: innerHeight,
    }));
    assert.ok(formMetrics.scroll <= formMetrics.client + 1, 'Product form fits mobile width');
    assert.ok(formMetrics.footer <= formMetrics.viewport, 'Product actions fit viewport');
    await page.screenshot({ path: `${output}/product-form-mobile.png`, fullPage: true });
    await dialog.getByPlaceholder('e.g. NordVPN').fill('Mobile test product');
    await dialog.getByLabel('Regular Price', { exact: true }).fill('150');
    failSave = true;
    await dialog.getByRole('button', { name: 'Add product', exact: true }).click();
    await dialog.getByRole('alert').waitFor();
    assert.match(await dialog.getByRole('alert').innerText(), /Test validation error/);
    failSave = false;
    await dialog.getByRole('button', { name: 'Add product', exact: true }).click();
    await dialog.waitFor({ state: 'hidden' });
    assert.equal(savedPayload.title, 'Mobile test product');
    assert.equal(savedPayload.price, 150);
    assert.equal(savedPayload.category_id, null);

    longName = true;
    await page.goto(`${baseURL}/#overview`);
    await page.reload();
    await page.locator('.attention-banner').waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Long store/customer names fit');
    longName = false;
    await page.setViewportSize({ width: 1440, height: 1000 });
    await page.goto(`${baseURL}/#overview`);
    await page.reload();
    await page.locator('.attention-banner').waitFor();
    await page.screenshot({ path: `${output}/dashboard-desktop.png`, fullPage: true });
    failOverview = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await page.getByRole('alert').filter({ hasText: 'Refresh failed' }).waitFor();
    await page.goto(`${baseURL}/#overview`);
    await page.reload();
    await page.getByRole('button', { name: 'Try again', exact: true }).waitFor();
    failOverview = false;
    emptyOverview = true;
    await page.getByRole('button', { name: 'Try again', exact: true }).click();
    await page.getByRole('heading', { name: 'You’re all caught up' }).waitFor();
    assert.match(await page.locator('.recent-orders').innerText(), /No orders yet/);

    signedIn = false;
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto(baseURL);
    await page.reload();
    await page.getByRole('heading', { name: 'Welcome back' }).waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Sign-in fits 320px');
    assert.equal(errors.length, 0, `Browser errors: ${errors.join('; ')}`);
    fs.writeFileSync(`${output}/results.json`, JSON.stringify({ results, formMetrics, errors, interactions: 'passed', fixtureData: true }, null, 2));
    console.log(`84 responsive screen checks and interaction regressions passed. Synthetic screenshots: ${output}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
