# Admin console browser checks

`admin-responsive.cjs` exercises the actual console with intercepted API responses.
All names, products, payments and balances are synthetic. It must never need admin
credentials or a production database.

The responsive sweep covers 21 pages/subpages at eight widths (320–1920px),
including a 1366×768 laptop. Desktop checks keep Sign out visible while navigation
scrolls, reject duplicate currency symbols, and exercise Product, Stock and Category
dialogs at three desktop sizes. Broadcast preview checks cover valid links, unsafe
protocols, injected elements and encoded attribute quotes.

Copy regressions also check that decorative page descriptions, repeated mobile
store names, tap instructions and third metadata lines stay removed. Shorter
notification labels keep their original keys; cancelling a toggle must not write.
Populated screens also reject decorative dash/bullet/arrow/checkmark text.
Parsing expressions, financial signs, dates, identifiers, URLs and secret masking
are intentionally not rewritten.

The optional browser-test environment needs `@playwright/test` available from the
console's Node resolution path and a Playwright Chromium installation. These are
test tools, not runtime dependencies. `CHROMIUM_PATH` can select a system browser.

1. Build the console: `cd console && npm ci && npm run build`.
2. Serve `console/out` locally, e.g. `python -m http.server 4173 --directory console/out`
   from the repository root.
3. Run `node tests/browser/admin-responsive.cjs` from the repository root.

Run `node tests/browser/payment-dialogs.cjs` as well. It checks all four payment
method forms at eight viewport sizes, including short landscape screens. It
verifies shared limits in BDT/USDT, minimum validation, stacked phone fields,
rounded modal footers, visible save controls, provider selection and save retry.
All writes are intercepted with synthetic responses.

`activity.cjs` verifies readable wallet/product/settings events, original log
disclosures, server-side action/search filters, error/empty states and cancelled
retries at five phone/tablet/desktop widths. No actual tasks are retried.

Also run `node tests/browser/layout-quality.cjs` against the same static build.
This checks 24 Home states (zero, one and five orders at eight widths), inline
header actions, two-column metrics, bounded row heights, exact-copy normal/long/
multiline customer input and direct Stock navigation. Deposits remains accessible
from More and from Home's pending-deposit action. `CAPTURE_BASELINE=1` captures the
previous layout without running the new-layout assertions.

The same suite holds the overview response until the loading state is inspected:
24 delayed-loading transitions at eight widths compare metric geometry, colors,
toolbar and recent-order header with the loaded page. Pending controls and the
number of order rows depend on the response; those can naturally change size.
It also checks reduced motion and that slow or failed refreshes retain loaded
figures instead of showing a different skeleton. Preview screenshots contain
synthetic data only.

Supplier API setup has one Add/Edit action per provider and opens a focused
dialog, not a second accordion. Checks cover cancel/reopen key clearing,
provider-specific save payloads, narrow dialog geometry and a single-line
filtered empty state.

Short-copy checks include the administrator empty state and mandatory notification
rows without repeated descriptions. Confirmation dialogs and one-time-key
warnings retain their consequences.

The Admin UI workflow runs both suites against the default production build on
matching pull requests and main-branch changes. Browser tooling is installed in
an isolated runner directory, not in production dependencies. Synthetic screenshots
and geometry results are retained as workflow artifacts for seven days.

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

Supplier checks cover visible Add API / Edit API actions, the correct provider's
configuration form, password-field clearing after save, catalog-error recovery,
local search without per-keystroke API calls, and ignoring delayed responses
from a previously selected supplier. Setup screenshots contain synthetic data
only and are captured after the key input has been cleared.

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
