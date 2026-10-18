# Admin console browser checks

`admin-responsive.cjs` exercises the actual console with intercepted API responses.
All names, products, payments and balances are synthetic. It must never need admin
credentials or a production database.

Copy regressions also check that decorative page descriptions, repeated mobile
store names, tap instructions and third metadata lines stay removed. Shorter
notification labels keep their original keys; cancelling a toggle must not write.

The optional browser-test environment needs `@playwright/test` available from the
console's Node resolution path and a Playwright Chromium installation. These are
test tools, not runtime dependencies. `CHROMIUM_PATH` can select a system browser.

1. Build the console: `cd console && npm ci && npm run build`.
2. Serve `console/out` locally, e.g. `python -m http.server 4173 --directory console/out`
   from the repository root.
3. Run `node tests/browser/admin-responsive.cjs` from the repository root.

Optional environment variables: `BASE_URL` (default `http://127.0.0.1:4173`),
`CHROMIUM_PATH`, `ARTIFACT_DIR` (default `/tmp/dpb-admin-design`).

The suite checks 21 populated screens/subpages at six widths (320, 390, 760,
768, 1024 and 1440px): **126 layout checks**. It covers every main screen, all
four Settings tabs, instant deposits, customer detail, supplier configuration
and the live catalog explorer. Checks include independent mobile lists,
drawer focus containment and Escape, tablet resize,
long store/customer names, product form validation and save/retry, dashboard error
recovery, empty states and narrow-screen sign-in. Screenshots and a JSON report
are written to `ARTIFACT_DIR`.

Mobile app regressions also verify a single app-bar title, bottom-sheet navigation,
independent semantic lists (not restyled tables), compact row geometry and no
title/price overlap. Product rows open the existing edit form; secondary actions
are available in a sheet and deletion still requires confirmation. Bulk selection,
order details with customer input, filter expansion and delivery-failure states
are covered. Orders/products preview screenshots use multiple synthetic records.

Tap-through checks cover deposit details and approve/reject confirmation,
instant-payment details, customer profiles, stock editing/removal, category
editing, protected linked validities, reseller review and broadcast detail.
Emoji deletion cancellation, synced/remote supplier details and bulk-selection
controls, plus payment-method and ZiniPay configuration dialogs, are checked
on a 320px phone as well.
Cancelling these actions must send **zero write requests**. Five list empty states
and deposit load-error/retry recovery are tested. Supplier tests include connected
status, a synced product and a remote catalog product. Full-page audit screenshots,
mobile viewport previews and the JSON report are generated from the real build.
