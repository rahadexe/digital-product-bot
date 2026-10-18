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
const stockItem = { id: 7, product_id: 1, product_title: product.title, content: 'SYNTHETIC-STOCK-NOT-A-CREDENTIAL', status: 'available', max_uses: 3, uses: 1, created_at: customer.created_at, expires_at: '2028-10-17T08:00:00Z' };
const reseller = { id: 8, user_id: 1, tg_user_id: 123, full_name: customer.first_name, telegram_handle: '@synthetic_customer', phone_number: 'Not supplied', channel_link: 'https://example.test/store', status: 'pending', created_at: customer.created_at };
const invoice = { id: 9, reference: 'SYNTHETIC-INVOICE-REFERENCE', tg_user_id: 123, first_name: customer.first_name, provider: 'zinipay', credit_amount: 125, pay_amount: 125, rate: 1, status: 'pending', created_at: customer.created_at };
const emoji = { id: 1, name: 'Store subscription icon', emoji_id: '000000000000000001', is_system: false };

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
    let emptyLists = false;
    let failDeposits = false;
    let previewOrders = null;
    const mutations = [];
    await page.route('**/api/**', async route => {
      const req = route.request();
      const path = new URL(req.url()).pathname.replace('/api/admin/', '');
      if (req.method() !== 'GET') mutations.push({ path, method: req.method() });
      if (path === 'deposits' && failDeposits) return route.fulfill({ status: 500, contentType: 'application/json', body: JSON.stringify({ detail: 'Synthetic deposit load error' }) });
      let body = [];
      if (path === 'session') body = { signed_in: signedIn, csrf: 'synthetic-test-csrf', store_name: longName ? 'A deliberately very long digital storefront name for narrow screen testing' : 'Digital Store' };
      else if (path === 'settings') body = { currency_symbol: '৳', store_name: longName ? 'A deliberately very long digital storefront name for narrow screen testing' : 'Digital Store', validity_presets: '1 month,1 year', admin_tg_ids: '', usd_rate: '125', currency: 'BDT' };
      else if (path === 'products' && req.method() === 'GET') body = page.url().includes('#suppliers')
        ? [...products, { ...product, id: 90, upstream_product_id: 91, supplier_code: 'digital_mart', upstream_price: 90 }]
        : products;
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
      else if (path === 'orders') body = { orders: previewOrders || [order], total: previewOrders?.length || 1, waiting: 2, summary };
      else if (/^orders\/\d+$/.test(path)) body = { order, stock_item: null, messages: [] };
      else if (path === 'deposits') body = { deposits: [deposit], total: 1, summary };
      else if (path === 'users') body = { users: [customer], total: 1, summary };
      else if (path === 'users/123') body = { user: customer, reseller_key: null, reseller_stats: null };
      else if (path === 'inventory') body = { items: [stockItem], total: 1, summary: { available_units: 2, sold_units: 1, expired_units: 0, in_stock_products: 1 } };
      else if (path === 'emojis') body = { system: [], custom: [emoji], all: [emoji] };
      else if (path === 'reseller-applications') body = { applications: [reseller], total: 1, summary: { total: 1, pending: 1, approved: 0, rejected: 0 } };
      else if (path === 'suppliers/status') body = { is_configured: true, providers: [{ code: 'digital_mart', name: 'Digital Mart', currency: 'BDT', currency_symbol: '৳', is_configured: true, base_url: 'https://example.test/api', api_key_masked: '', balance: 3000, connected: true, markup_percent: 15, auto_sync: 1, low_balance_alert: 50, products_count: 1 }], base_url: 'https://example.test/api', account: { balance: 3000, currency_symbol: '৳' }, upstream_products_count: 1 };
      else if (path === 'suppliers/remote-products') body = { supplier: 'digital_mart', supplier_name: 'Demo supplier', currency: 'BDT', total: 1, filtered_total: 1, categories: ['Subscriptions'], products: [{ id: 91, title: product.title, category_name: 'Subscriptions', duration: '1 month', reseller_price: 90, regular_price: 150, currency: 'BDT', currency_symbol: '৳', in_store: false, icon: '', description: '', warranty: '', local_id: null }] };
      else if (path === 'audit-logs') body = { entries: [{ id: 1, action: 'product_updated', details: 'Updated subscription price and availability.', actor: 'Demo admin', created_at: customer.created_at }], total: 1, actions: ['product_updated'] };
      else if (path === 'failed-jobs') body = [{ kind: 'notification', id: 4, attempts: 2, error: 'Synthetic delivery error. Review the order before retrying.' }];
      else if (path === 'payments/status') body = { enabled: false, configured: false };
      else if (path === 'payments') body = { invoices: [invoice], total: 1 };
      else if (path === 'deposit-methods') body = [{ id: 1, name: 'bKash', account_info: 'Demo account', instructions: 'Send Money', min_deposit: 50, rate_to_currency: 1, is_active: 1, sort_order: 1, auto_verify: 'none', account_type: 'personal' }];
      else if (path === 'gate-channels') body = [{ id: 1, title: 'Store announcements', channel_id: '-1000000000000', invite_link: 'https://example.test/channel', is_active: 1, sort_order: 1 }];
      else if (path === 'update-channels') body = [{ id: 1, title: 'Customer support', url: 'https://example.test/help', is_active: 1, sort_order: 1 }];
      else if (path === 'broadcast') body = { recipient_count: 19, recent: [{ id: 1, created_at: customer.created_at, text: 'New subscriptions available. Browse Products to see the latest arrivals.', total: 19, success: 19, failed: 0, pending: 0 }] };
      if (emptyLists) {
        if (['products', 'categories'].includes(path)) body = [];
        if (path === 'users') body = { users: [], total: 0, summary };
        if (path === 'deposits') body = { deposits: [], total: 0, summary };
        if (path === 'inventory') body = { items: [], total: 0 };
        if (path === 'reseller-applications') body = { applications: [], total: 0 };
      }
      await route.fulfill({ contentType: 'application/json', body: JSON.stringify(body) });
    });
    const results = [];
    const screens = ['overview', 'orders', 'deposits', 'deposits/instant', 'users', 'users/123', 'products', 'suppliers', 'suppliers/config', 'suppliers/explore', 'inventory', 'categories', 'validities', 'emojis', 'broadcast', 'reseller-apps', 'activity', 'settings', 'settings/gate', 'settings/payments', 'settings/notifications'];
    for (const width of [320, 390, 760, 768, 1024, 1440]) {
      await page.setViewportSize({ width, height: 900 });
      for (const screen of screens) {
        await page.goto(`${baseURL}/#${screen.startsWith('suppliers/') ? 'suppliers' : screen}`);
        if (screen === 'deposits/instant' || screen.startsWith('suppliers')) await page.reload();
        await page.locator('.main-inner').waitFor();
        if (screen === 'suppliers/config') {
          await page.locator('.supplier-configuration').waitFor();
          await page.locator('.supplier-configuration > summary').click();
        }
        if (screen === 'suppliers/explore') await page.getByRole('button', { name: /Browse catalog/ }).click();
        await page.waitForTimeout(100);
        const dimensions = await page.evaluate(() => ({ viewport: innerWidth, document: document.documentElement.scrollWidth }));
        if (dimensions.document > dimensions.viewport + 1) {
          await page.screenshot({ path: `${output}/overflow-${screen.replaceAll('/', '-')}-${width}.png`, fullPage: true });
          console.log(await page.locator('.main-inner').evaluate(el => [...el.querySelectorAll('*')].filter(node => {
            const rect = node.getBoundingClientRect();
            return rect.right > innerWidth + 1 && getComputedStyle(node).display !== 'none';
          }).slice(0, 12).map(node => ({ tag: node.tagName, class: node.className, text: node.textContent.slice(0, 100), width: node.getBoundingClientRect().width }))));
        }
        assert.ok(dimensions.document <= dimensions.viewport + 1, `${screen} overflows at ${width}px: ${dimensions.document}`);
        if (['orders', 'products', 'deposits', 'deposits/instant', 'users', 'inventory', 'categories', 'validities', 'reseller-apps', 'suppliers', 'suppliers/config', 'suppliers/explore', 'emojis', 'broadcast'].includes(screen)) {
          const mobile = page.locator('.app-record-list');
          const desktop = page.locator('.desktop-record-scroll');
          assert.equal(await mobile.isVisible(), width <= 760, 'List markup is mobile-only');
          assert.equal(await desktop.isVisible(), width > 760, 'Table markup is desktop-only');
          if (width <= 760 && screen !== 'validities') {
            const row = mobile.locator('.app-record').first();
            await row.waitFor();
            const geometry = await row.evaluate(el => {
              const copy = el.querySelector('.app-record-copy').getBoundingClientRect();
              const tail = el.querySelector('.app-record-tail').getBoundingClientRect();
              return { height: el.getBoundingClientRect().height, copyRight: copy.right, amountLeft: tail.left, scroll: el.scrollWidth, width: el.clientWidth };
            });
            assert.ok(geometry.height >= 80 && geometry.height <= 144, 'Records stay compact even with long names');
            assert.ok(geometry.copyRight <= geometry.amountLeft - 4, 'Titles never collide with price/status');
            assert.ok(geometry.scroll <= geometry.width + 1, 'Record content stays contained');
            assert.equal(await row.locator('.app-record-meta, .app-record-chevron').count(), 0, 'List rows have no third metadata line or redundant chevron');
          }
        }
        assert.equal(await page.locator('.page-description, .page-head .eyebrow, .mobile-store-link').count(), 0, 'No decorative intro text or repeated store name');
        assert.doesNotMatch(await page.locator('.app-list-heading').allInnerTexts().then(texts => texts.join(' ')), /Tap to |Tap for |Latest first/, 'List headings do not explain obvious taps');
        if (width <= 760) {
          const redundantPagers = page.locator('.product-pagination.single-page, .order-pagination.single-page, .pager:not(:has(button:not(:disabled)))');
          assert.equal(await redundantPagers.evaluateAll(nodes => nodes.filter(node => node.getBoundingClientRect().height > 0).length), 0, 'Single-page counts/pagers do not repeat the list header');
        }
        if (width === 390 || width === 1440) {
          await page.evaluate(() => scrollTo(0, 0));
          await page.screenshot({ path: `${output}/audit-${screen.replaceAll('/', '-')}-${width}.png`, fullPage: true });
          if (width === 390) await page.screenshot({ path: `${output}/phone-${screen.replaceAll('/', '-')}.png` });
        }
        results.push({ screen, width, ...dimensions });
      }
      console.log(`Passed all ${screens.length} populated screens/subpages at ${width}px`);
    }
    await page.setViewportSize({ width: 390, height: 844 });
    const detailDialog = () => page.getByRole('dialog');
    const assertDialogFits = async () => {
      const geometry = await detailDialog().evaluate(el => {
        const r = el.getBoundingClientRect();
        return { left: r.left, right: r.right, top: r.top, bottom: r.bottom, width: innerWidth, height: innerHeight };
      });
      assert.ok(geometry.left >= -1 && geometry.right <= geometry.width + 1, 'Detail/form stays within phone width');
      assert.ok(geometry.top >= -1 && geometry.bottom <= geometry.height + 1, 'Detail/form fits the viewport');
    };
    // Tap-through checks ensure compact rows do not hide operational controls.
    await page.goto(`${baseURL}/#deposits`);
    await page.getByRole('button', { name: 'Review deposit D19', exact: true }).click();
    await assertDialogFits();
    assert.match(await detailDialog().innerText(), /SYNTHETICTRX1234567890/);
    await detailDialog().getByRole('button', { name: 'Verify deposit', exact: true }).click();
    await detailDialog().getByRole('heading', { name: 'Verify deposit D19?' }).waitFor();
    await detailDialog().getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Review deposit D19', exact: true }).click();
    await detailDialog().getByRole('button', { name: 'Reject deposit', exact: true }).click();
    await detailDialog().getByRole('heading', { name: 'Reject deposit D19?' }).waitFor();
    await page.keyboard.press('Escape');
    assert.equal(mutations.length, 0, 'Opening/cancelling payment review never credits or rejects a deposit');

    await page.goto(`${baseURL}/#deposits/instant`);
    await page.reload(); // The existing Deposits component owns its tab while mounted.
    await page.getByRole('button', { name: `View payment ${invoice.reference}` }).click();
    await assertDialogFits();
    assert.match(await detailDialog().innerText(), /Amount to pay/);
    await page.keyboard.press('Escape');

    await page.goto(`${baseURL}/#users`);
    await page.getByRole('button', { name: `View customer ${customer.first_name}`, exact: true }).click();
    await page.locator('.cust-profile-hero').waitFor();
    assert.match(await page.locator('.main-inner').innerText(), /Wallet|Balance/i);
    await page.screenshot({ path: `${output}/customer-detail-mobile.png`, fullPage: true });

    await page.goto(`${baseURL}/#inventory`);
    await page.getByRole('button', { name: 'View stock item 7', exact: true }).click();
    await assertDialogFits();
    await detailDialog().getByRole('button', { name: 'Edit stock', exact: true }).click();
    await detailDialog().getByRole('heading', { name: 'Edit item #7' }).waitFor();
    assert.equal(await detailDialog().locator('textarea').inputValue(), stockItem.content);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'View stock item 7', exact: true }).click();
    await detailDialog().getByRole('button', { name: 'Remove item', exact: true }).click();
    await detailDialog().getByRole('heading', { name: 'Stop selling this item?' }).waitFor();
    await detailDialog().getByRole('button', { name: 'Cancel', exact: true }).click();

    await page.goto(`${baseURL}/#categories`);
    await page.getByRole('button', { name: 'Manage category Subscriptions' }).click();
    await detailDialog().getByRole('button', { name: 'Edit category', exact: true }).click();
    await detailDialog().getByRole('heading', { name: 'Edit Category' }).waitFor();
    assert.equal(await detailDialog().getByRole('textbox', { name: 'Category Name' }).inputValue(), 'Subscriptions');
    await assertDialogFits();
    await page.keyboard.press('Escape');

    await page.goto(`${baseURL}/#validities`);
    assert.equal(await page.getByRole('button', { name: 'Delete validity 1 month', exact: true }).isDisabled(), true, 'Linked duration remains protected');
    await page.getByRole('button', { name: 'Delete validity 1 year', exact: true }).click();
    await detailDialog().waitFor();
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Add validity', exact: true }).click();
    await assertDialogFits();
    await page.keyboard.press('Escape');

    await page.goto(`${baseURL}/#reseller-apps`);
    await page.getByRole('button', { name: `Review reseller ${customer.first_name}`, exact: true }).click();
    await assertDialogFits();
    assert.equal(await detailDialog().getByRole('link', { name: 'https://example.test/store' }).getAttribute('href'), 'https://example.test/store');
    await detailDialog().getByRole('button', { name: 'Approve reseller', exact: true }).click();
    await detailDialog().getByRole('heading', { name: /Approve Reseller:/ }).waitFor();
    await page.keyboard.press('Escape');

    await page.goto(`${baseURL}/#broadcast`);
    await page.getByRole('button', { name: 'View broadcast 1', exact: true }).click();
    await assertDialogFits();
    assert.match(await detailDialog().innerText(), /New subscriptions available/);
    await page.keyboard.press('Escape');
    await page.getByPlaceholder('Write your message here...').fill('Synthetic test announcement');
    await page.getByRole('button', { name: 'Send Broadcast', exact: true }).click();
    await detailDialog().getByRole('heading', { name: 'Send broadcast?' }).waitFor();
    await detailDialog().getByRole('button', { name: 'Cancel', exact: true }).click();
    assert.equal(mutations.length, 0, 'Cancelled stock/category/reseller/broadcast actions never call write APIs');

    await page.goto(`${baseURL}/#emojis`);
    await page.getByRole('button', { name: `View emoji ${emoji.name}` }).click();
    await assertDialogFits();
    assert.match(await detailDialog().innerText(), /000000000000000001/);
    await detailDialog().getByRole('button', { name: 'Delete emoji', exact: true }).click();
    await detailDialog().getByRole('heading', { name: /Delete Emoji/ }).waitFor();
    await page.keyboard.press('Escape');
    await page.setViewportSize({ width: 320, height: 740 });
    await page.goto(`${baseURL}/#suppliers`);
    await page.reload();
    await page.getByRole('button', { name: 'View supplier product 90', exact: true }).click();
    await assertDialogFits();
    assert.match(await detailDialog().innerText(), /Wholesale rate/);
    await page.keyboard.press('Escape');
    await page.getByRole('checkbox', { name: 'Select supplier product 90', exact: true }).check();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Supplier bulk controls fit 320px');
    await page.getByRole('checkbox', { name: 'Select supplier product 90', exact: true }).uncheck();
    await page.getByRole('button', { name: /Browse catalog/ }).click();
    await page.getByRole('button', { name: 'View remote product 91', exact: true }).click();
    await assertDialogFits();
    assert.equal(await detailDialog().getByRole('button', { name: 'Import to Store', exact: true }).isEnabled(), true);
    await page.keyboard.press('Escape');
    await page.getByRole('checkbox', { name: 'Select remote product 91', exact: true }).check();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Remote import controls fit 320px');
    await page.getByRole('checkbox', { name: 'Select remote product 91', exact: true }).uncheck();
    assert.equal(mutations.length, 0, 'Supplier selection/details and cancelled emoji deletion never write');
    await page.goto(`${baseURL}/#settings/payments`);
    await page.getByTitle('Edit bKash').click();
    await detailDialog().getByRole('heading', { name: 'Edit bKash' }).waitFor();
    await assertDialogFits();
    await page.keyboard.press('Escape');
    await page.getByTitle('Configure ZiniPay Gateway & Auto-Verification').click();
    await detailDialog().getByRole('heading', { name: 'ZiniPay Gateway Settings' }).waitFor();
    await assertDialogFits();
    await page.keyboard.press('Escape');
    assert.equal(mutations.length, 0, 'Opening/cancelling gateway configuration never saves payment settings');
    await page.goto(`${baseURL}/#settings/notifications`);
    await page.getByRole('heading', { name: 'Admin alerts', exact: true }).waitFor();
    assert.equal(await page.getByRole('heading', { name: 'Administrator Notifications', exact: true }).count(), 0, 'Alerts have no repeated section title');
    const deliveryAlert = page.getByRole('switch', { name: 'Automatic deliveries', exact: true });
    assert.equal(await deliveryAlert.getAttribute('aria-checked'), 'false');
    await deliveryAlert.click();
    await detailDialog().getByRole('heading', { name: 'Enable Automatic deliveries?' }).waitFor();
    await assertDialogFits();
    await detailDialog().getByRole('button', { name: 'Cancel', exact: true }).click();
    assert.equal(await deliveryAlert.getAttribute('aria-checked'), 'false', 'Cancelling an alert toggle retains its setting');
    assert.equal(mutations.length, 0, 'Cancelling an alert toggle never writes settings');
    assert.equal(await page.locator('.flag-row .flag-row-text small').count(), 1, 'Only the useful low-stock clarification remains');
    await page.getByText('System & security', { exact: true }).click();
    await page.getByText('Manual Deposit Requests', { exact: true }).waitFor();
    await page.getByText('System & security', { exact: true }).click();
    await page.setViewportSize({ width: 390, height: 844 });

    emptyLists = true;
    for (const screen of ['deposits', 'users', 'inventory', 'categories', 'reseller-apps']) {
      await page.goto(`${baseURL}/#${screen}`);
      await page.reload();
      await page.locator('.app-list-empty').filter({ hasText: /No / }).first().waitFor();
      assert.equal(await page.locator('.app-list-empty:visible').count(), 1, `${screen} has one clear empty state`);
    }
    emptyLists = false;
    failDeposits = true;
    await page.goto(`${baseURL}/#deposits`);
    await page.reload();
    await page.getByRole('button', { name: 'Retry deposits', exact: true }).waitFor();
    failDeposits = false;
    await page.getByRole('button', { name: 'Retry deposits', exact: true }).click();
    await page.getByRole('button', { name: 'Review deposit D19', exact: true }).waitFor();

    for (const screen of ['orders', 'products', 'deposits']) {
      await page.goto(`${baseURL}/#${screen}`);
      await page.locator('.app-record-list .app-record').first().waitFor();
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
    previewOrders = [
      { ...order },
      { ...order, id: 1000, product_title: 'Netflix Premium', first_name: 'Sample Buyer', price: 249, fulfillment: 'delivered' },
      { ...order, id: 999, product_title: 'Canva Pro', first_name: 'Test Customer', price: 129, fulfillment: 'delivered' },
    ];
    await page.goto(`${baseURL}/#orders`);
    await page.reload();
    await page.getByRole('button', { name: 'Open order 1001: Gemini Pro', exact: true }).waitFor();
    await page.screenshot({ path: `${output}/orders-mobile-preview.png`, fullPage: true });
    previewOrders = null;
    await page.getByRole('button', { name: 'Open order 1001: Gemini Pro', exact: true }).click();
    const orderDialog = page.getByRole('dialog', { name: 'Order O1001', exact: true });
    await orderDialog.waitFor();
    await orderDialog.getByText('demo@example.test', { exact: true }).waitFor();
    await page.keyboard.press('Escape');
    await orderDialog.waitFor({ state: 'hidden' });
    Object.assign(order, { customer_input: '', status: 'completed', fulfillment: 'delivered', delivery_status: 'failed' });
    await page.reload();
    await page.locator('.order-feed').getByText('Delivery failed', { exact: true }).waitFor();
    assert.equal(await page.locator('.order-customer-input').count(), 0, 'No empty customer-details block');
    assert.ok(await page.locator('.order-feed .app-record').isVisible(), 'Completed order remains tappable');
    Object.assign(order, originalOrder);
    const originalProducts = products;
    products = [
      { ...product, title: 'Gemini Pro', price: 99, icon: 'G', duration_label: '1 month', stock: 8 },
      { ...product, id: 2, title: 'Netflix Premium', price: 249, icon: 'N', duration_label: '1 month', stock: 12 },
      { ...product, id: 3, title: 'Canva Pro', price: 129, icon: 'C', duration_label: '1 year', stock: 4 },
      { ...product, id: 4, title: 'Spotify Premium', price: 149, icon: 'S', duration_label: '3 months', stock: 0 },
    ];
    await page.goto(`${baseURL}/#products`);
    await page.reload();
    await page.locator('.product-feed .app-record').first().waitFor();
    await page.screenshot({ path: `${output}/products-mobile-preview.png`, fullPage: true });
    products = originalProducts;
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
    await page.locator('.product-feed').waitFor();
    await page.reload();
    await page.locator('.product-feed .app-record').first().click();
    const editDialog = page.getByRole('dialog', { name: 'Edit product', exact: true });
    await editDialog.waitFor();
    assert.equal(await editDialog.getByLabel('Regular Price', { exact: true }).inputValue(), '150', 'List opens existing edit form without changing price');
    await page.keyboard.press('Escape');
    await editDialog.waitFor({ state: 'hidden' });
    await page.locator('.product-feed .app-record-more').first().click();
    const actions = page.getByRole('dialog', { name: 'Product actions', exact: true });
    await actions.waitFor();
    await actions.getByRole('button', { name: 'Delete product', exact: true }).click();
    const deleteConfirm = page.getByRole('dialog').last();
    await deleteConfirm.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.getByRole('button', { name: 'Select', exact: true }).click();
    await page.getByRole('checkbox', { name: 'Select page', exact: true }).check();
    assert.match(await page.locator('.product-toolbar').innerText(), /1 product\(s\) selected/);
    await page.getByRole('button', { name: 'Deselect', exact: true }).click();
    await page.getByRole('button', { name: 'Done', exact: true }).click();
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
    await page.getByRole('heading', { name: 'All clear' }).waitFor();
    assert.match(await page.locator('.recent-orders').innerText(), /No orders yet/);

    signedIn = false;
    await page.setViewportSize({ width: 320, height: 640 });
    await page.goto(baseURL);
    await page.reload();
    await page.getByRole('heading', { name: 'Welcome back' }).waitFor();
    assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), 'Sign-in fits 320px');
    assert.equal(errors.length, 0, `Browser errors: ${errors.join('; ')}`);
    fs.writeFileSync(`${output}/results.json`, JSON.stringify({ results, formMetrics, errors, interactions: 'passed', fixtureData: true }, null, 2));
    console.log(`${results.length} populated responsive screen checks and interaction regressions passed. Synthetic screenshots: ${output}`);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
