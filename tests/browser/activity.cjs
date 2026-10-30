/* Activity readability, filters and preservation of original evidence. Synthetic only. */
const { createRequire } = require('node:module');
const { resolve } = require('node:path');
const { chromium, expect } = createRequire(resolve(__dirname, '../../console/package.json'))('@playwright/test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const base = process.env.BASE_URL || 'http://127.0.0.1:4173';
const output = process.env.ARTIFACT_DIR || '/tmp/dpb-activity';
const entries = [
  ['adjust_balance', 'Adjusted balance of 123 by +10.00 (new balance: 25.00). Reason: Customer refund'],
  ['adjust_balance', 'Adjusted balance of 456 by -5.00 (new balance: 20.00). Reason: Duplicate credit'],
  ['product_updated', 'Product #42: is_active, price; price 10.00 -> 12.00'],
  ['settings_updated', 'Changed: max_deposit_limit, usd_rate'],
  ['login_failed', 'Invalid admin password from 192.0.2.1'],
  ['job_retry', 'notification job #4'],
  ['future_event', 'Unrecognized event <script>alert(1)</script>'],
].map(([action, details], i) => ({ id: i + 1, action, details, actor: i < 4 ? 'admin-session:fixture-id' : 'system', created_at: '2026-10-30T04:00:00Z' }));

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, ...(process.env.CHROMIUM_PATH ? { executablePath: process.env.CHROMIUM_PATH } : {}) });
  const page = await browser.newPage();
  const errors = [], writes = [], requests = [];
  let fail = false;
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/**', async route => {
    const url = new URL(route.request().url());
    const path = url.pathname.replace('/api/admin/', '');
    if (route.request().method() !== 'GET') writes.push(path);
    let data = [];
    if (path === 'session') data = { signed_in: true, csrf: 'fixture', store_name: 'Sample Store' };
    if (path === 'settings') data = { currency: 'USD', currency_symbol: '$' };
    if (path === 'audit-logs') {
      requests.push(Object.fromEntries(url.searchParams));
      if (fail) return route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ detail: 'Activity temporarily unavailable.' }) });
      const action = url.searchParams.get('action'), query = url.searchParams.get('search') || '';
      const filtered = entries.filter(entry => (!action || entry.action === action) && entry.details.includes(query));
      data = { entries: filtered, total: filtered.length, actions: [...new Set(entries.map(entry => entry.action))] };
    }
    if (path === 'failed-jobs') data = [{ kind: 'notification', id: 4, attempts: 2, error: 'Synthetic delivery error' }];
    await route.fulfill({ contentType: 'application/json', body: JSON.stringify(data) });
  });
  try {
    for (const width of [320, 390, 768, 1366, 1920]) {
      await page.setViewportSize({ width, height: 900 });
      await page.goto(`${base}/?width=${width}#activity`);
      await expect(page.locator('.activity-event')).toHaveCount(entries.length);
      const added = page.locator('.activity-event').filter({ has: page.getByRole('heading', { name: 'Wallet balance added', exact: true }) });
      await expect(added).toContainText('Customer 123');
      await expect(added).toContainText('Customer refund');
      await expect(added).toContainText('Admin console');
      await expect(added.locator('.activity-technical dd').first()).not.toBeVisible();
      await added.getByText('Technical details', { exact: true }).click();
      await expect(added.locator('.activity-technical')).toContainText(entries[0].details);
      await added.getByText('Technical details', { exact: true }).click();
      await expect(page.locator('.activity-facts')).toContainText(['Change', 'Change', 'Fields changed']);
      await expect(page.locator('.activity-event').filter({ hasText: 'Product #42' })).toContainText('From 10.00 to 12.00');
      await expect(page.locator('.activity-event').filter({ hasText: 'Store settings changed' })).toContainText('Maximum deposit, BDT exchange rate');
      assert.equal(await page.locator('.activity-event script').count(), 0);
      assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), `Activity fits ${width}px`);
      await page.screenshot({ path: `${output}/activity-${width}.png`, fullPage: true });
    }
    await page.getByRole('combobox', { name: 'Activity type' }).click();
    await page.getByRole('option', { name: 'Wallet balance changed', exact: true }).click();
    await expect(page.locator('.activity-event')).toHaveCount(2);
    assert.ok(requests.some(request => request.action === 'adjust_balance'), 'Filter uses backend action code');
    await page.getByRole('searchbox', { name: 'Search activity' }).fill('Customer refund');
    await expect(page.locator('.activity-event')).toHaveCount(1);
    await page.getByRole('searchbox', { name: 'Search activity' }).fill('nothing-matches');
    await expect(page.getByText('No activity matches these filters.')).toBeVisible();
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel', exact: true }).click();
    assert.equal(writes.length, 0, 'Reading logs and cancelling retry never mutates data');
    fail = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(page.locator('.activity-feed').getByRole('alert')).toContainText('Activity temporarily unavailable.');
    assert.deepEqual(errors, []);
    console.log('Activity passed at 5 widths: readable events, original evidence, filtering, empty/error states and safe retry cancellation.');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
