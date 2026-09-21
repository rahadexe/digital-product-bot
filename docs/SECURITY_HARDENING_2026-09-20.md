# Pre-production security hardening

The owner confirmed that local, Neon and Coolify environments are still test environments and existing orders are dummy data. This round changes application security behavior without resetting those environments or deleting their orders. Configured remote databases and Coolify deployments were not modified.

## Changes

- Migration `0027_request_limits` adds shared atomic request budgets. API requests are limited to 180 per IP per 60-second window across all replicas, with local flood protection before the database. OPTIONS requests do not consume the shared budget. Loopback/internal health checks remain available. Failure to check a shared budget returns 503 instead of permitting unlimited traffic.
- Authenticated reseller accounts receive separate budgets of 120 reads and 30 writes per minute. Rotating keys or changing IPs does not reset the account budget. Rejections include `Retry-After`; they happen before purchases. These are fixed windows, so bursts around a window boundary are possible. Reverse-proxy connection/flood limits remain appropriate for traffic that should not reach the application.
- Expired shared-budget rows are cleaned up by the payment worker. Keys hash their namespace and identity; raw IPs/API secrets are not stored in this table. Existing audit/login records have their own retention rules.
- Admin sessions expire after eight hours. Old 90-day tokens are rejected. Login and session responses no longer return a bearer token. The console uses HttpOnly session cookies plus an in-memory CSRF token and deletes credentials persisted by older builds. Loading the session endpoint does not misleadingly extend cookie life beyond JWT expiry. Password changes and logout still invalidate sessions. The console request cache is bounded to 256 entries.
- Request-body timeout now bounds the whole upload, preventing a client from keeping a request alive indefinitely with occasional chunks. The existing 2 MiB API-body ceiling remains.
- Repeated unsigned payment callbacks claim a shared 30-second invoice check window. They cannot independently trigger unlimited gateway checks; scheduled reconciliation remains the fallback after interruption.
- Payment redirect validation now accepts HTTPS `zinipay.com` and its subdomains, rejects lookalike domains/TLDs, credentials in URLs, nonstandard ports and malformed URLs. Invoice-only URL responses are accepted only through the expected `/payment/<id>` path. The provider's documented response uses `https://secure.zinipay.com/payment/INVOICE_ID`: [official ZiniPay documentation](https://zinipay.com/docs).
- Purchases hold a shared product lock until commit, allowing simultaneous buyers while preventing price edits/deletion from racing the charge. Product deletion acquires the product lock before touching order history.
- Readiness returns 503 when this release's migrations have not been applied, even if PostgreSQL itself responds.

## Verification results

- 40 PostgreSQL integration tests passed in 94.687 seconds, including shared rate budgets under concurrency, cross-app limits, account limits after key rotation, cookie-only login/CSRF/logout, upload timeout, callback coalescing, pending price edits and missing-migration readiness.
- Two isolated provider/redirect security tests passed, using HTTP mocks rather than real payments.
- Next.js production build passed after the cookie authentication changes.
- `pip-audit -r requirements.txt` checked 37 resolved packages with no known vulnerabilities reported. `npm audit` reported zero known vulnerabilities. These are advisory-database checks, not a proof that dependencies have no undiscovered bugs.
- A disposable local purchase-service benchmark completed 100 orders with concurrency 10, 100 stock allocations and the expected wallet totals. Wall time: 0.355 seconds; 282.08 orders/second; median active transaction latency 19.98 ms; p95 165.77 ms. This excludes waiting for the benchmark semaphore, HTTP, Telegram and real gateways. It is not a Neon/Coolify or production-capacity guarantee.

## Applying to test environments

Include all new modules and migration files in the release. Stop older processes, run `python -m app migrate` with the selected test environment's configuration, then start the updated application. The previous supplier/banner cleanup migrations must ship together with this code. No database reset is required. Sign in again after the session-security change.

For cross-origin local development, use matching hosts consistently (for example localhost for both console and API), include the console origin in configuration, and use credentialed requests. For Coolify, serve the console and API through the same HTTPS origin. Test manual and instant delivery plus a gateway sandbox payment before treating the environment as release-ready.

The separate [reliability upgrade notes](RELIABILITY_UPGRADE_2026-09-20.md) retain the deployment procedure and remaining limitations. This round does not claim exhaustive security certification or replace end-to-end testing on the actual deployment network.
