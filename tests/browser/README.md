# Admin console browser checks

`admin-responsive.cjs` exercises the actual console with intercepted API responses.
All names, products, payments and balances are synthetic. It must never need admin
credentials or a production database.

The optional browser-test environment needs `@playwright/test` available from the
console's Node resolution path and a Playwright Chromium installation. These are
test tools, not runtime dependencies. `CHROMIUM_PATH` can select a system browser.

1. Build the console: `cd console && npm ci && npm run build`.
2. Serve `console/out` locally, e.g. `python -m http.server 4173 --directory console/out`
   from the repository root.
3. Run `node tests/browser/admin-responsive.cjs` from the repository root.

Optional environment variables: `BASE_URL` (default `http://127.0.0.1:4173`),
`CHROMIUM_PATH`, `ARTIFACT_DIR` (default `/tmp/dpb-admin-design`).

The suite checks 14 screens at six widths (320, 390, 760, 768, 1024 and 1440px),
populated mobile record cards, drawer focus containment and Escape, tablet resize,
long store/customer names, product form validation and save/retry, dashboard error
recovery, empty states and narrow-screen sign-in. Screenshots and a JSON report
are written to `ARTIFACT_DIR`.
