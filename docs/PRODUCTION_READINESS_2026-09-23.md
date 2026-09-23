# Production readiness review — 23 September 2026

## Follow-up release fixes

The user subsequently authorized fixes and a push, prioritizing important issues over additional scope. This release fixes wallet-adjustment replay (persistent operation IDs), stale outbox completion/cancellation (lease tokens), admin-alert Retry-After handling, readiness health checking, session network-error presentation, Orders response ordering, Activity refresh caching, force-join outage messages, and bounded cleanup of completed admin notification jobs. Existing 30-day secure sessions and earlier queued-alert/mobile fixes are included.

Migration 0033 is required before running the updated backend. Deploy frontend and backend together: wallet adjustment now requires an operation ID. Automatic startup migration remains available; `.env` and credentials are not changed.

Deferred to keep this release bounded: durable customer decision notifications, catalog pagination beyond 500 products, bot identity fallback, distributed bot throttle/membership invalidation, and cross-process worker heartbeat monitoring. These remain limitations; this release is not a claim that every audit finding is resolved. Docker readiness now detects local dependency problems, but does not replace external worker monitoring.

The original findings below are retained as audit history, not a statement that all remain unfixed.

Verdict: **hold unrestricted production launch** until the money-adjustment and delivery reliability findings below are resolved. This phase is an audit; no application fixes or new features were made after the request to inspect only. Earlier edits remain in the workspace. Files were changing during inspection, so this is a point-in-time review, not certification of a frozen release.

## Findings

| Priority | Finding and concrete impact | Evidence | Required correction |
|---|---|---|---|
| P1 | Admin wallet adjustment has no operation ID. If the server commits but the response is lost, repeating the same adjustment changes the balance twice. | `app/api/admin/users.py:adjust_balance`, `app/services/users.py:adjust_balance`. Reproduced in an isolated local schema: starting 100, repeating +10 with the same reason resulted in 120. | Persist a unique adjustment operation ID atomically with the wallet change; reuse it on retries. A disabled UI button alone does not solve lost responses. |
| P1 | Outbox completion is not fenced by the current lease. After a lease expires, an older worker can overwrite a newer worker's successful result. | `app/services/delivery.py:claim_next`, `finish`, `cancel`. Reproduced: worker B marked sent, then stale worker A changed the same row to pending. | Unique claim token, conditional completion/cancellation, bounded send duration; update order delivery status only when the matching claim succeeds. |
| P1 | Admin notification retries discard Telegram's requested cooldown. A temporary long flood limit can exhaust all five attempts and leave a deposit/order alert failed. | `app/services/notifications.py:send` catches every exception and returns False; `app/workers/admin_notifications.py` retries on its own short exponential schedule. | Preserve Retry-After and defer appropriately, distinguishing temporary throttling from permanent errors. |
| P2 | Docker health check verifies only that HTTP is alive. Database/worker failure can leave the container marked healthy. Separate `web` deployments also cannot prove a separate worker is running. | `Dockerfile:HEALTHCHECK`, `app/api/health.py:ready`, `app/runtime.py`. | Use readiness for traffic admission plus worker heartbeat/backlog monitoring; keep liveness separate. Actual Coolify health-check overrides were not inspected. |
| P2 | Session network failures are presented as signed out. Two failed requests lead to the login screen even if the cookie is valid. | `console/src/app/(panel)/page.tsx:check`. | Distinguish offline/server-unavailable from an explicit unauthenticated response; provide retry without discarding the screen. |
| P2 | Orders filtering still has an asynchronous response race. A slow previous search/date/status response may overwrite the latest selection. Initial fetch errors can leave Loading visible with only a temporary toast. | `console/src/components/Orders.tsx:load`; Inventory has a request-version guard but Orders does not. | Apply latest-request guards/cancellation and persistent error/retry state. |
| P2 | Activity Refresh can reuse the same cached response for 20 seconds. Failed-job recovery can therefore appear stale immediately after an external worker changes status. | `console/src/components/Activity.tsx` increments revision; `console/src/lib/api.ts` caches audit/failed-jobs GETs. | Explicit cache invalidation or uncached refresh. |
| P2 | Force-join outage copy is inconsistent. The explanatory message says verification is unavailable, but Joined still says the user has not joined. Access middleware has the same misleading popup. | `app/bot/handlers/start.py:handle_gate_verify`, `app/bot/middlewares.py:StoreAccess`. | Propagate unavailable versus genuinely missing membership to every response. |
| P2 | Refund, deposit decision and wallet-adjustment customer notices remain best effort. A crash or transient Telegram failure can lose the notice after the financial transaction commits. | `app/services/purchases.py`, `deposits.py`, `users.py` still call `in_background` for these messages. | Queue financially meaningful customer notices transactionally. The balance/order history remains authoritative; this finding is about notification loss. |
| P2 | Reseller catalog silently stops at 500 products, without a pagination contract. | `app/services/reseller.py:get_reseller_products` requests `limit=500`; reseller products route has no offset/cursor. | Add bounded pagination and accurate total/continuation information before catalog grows past the limit. |
| P2 | Completed admin notification jobs and recipient markers have no cleanup policy. Their count grows with orders/deposits. | Migration `0032_admin_notification_jobs`; hourly cleanup in `app/workers/payments.py` does not cover these tables. | Retain useful diagnostic history for a defined period, then prune completed jobs in bounded batches. |
| P2 | Bot identity lookup falls back to a hardcoded unrelated username. On getMe failure, referral/deep links can point at the wrong bot. | `app/services/notifications.py:FALLBACK_USERNAME`, `bot_username`. | Use a validated configured/cached identity, or fail gracefully until identity is known. |
| P2 | Force-join membership invalidation and bot throttling are process-local. Multiple webhook replicas do not share immediate membership invalidation or a single bot request budget. | `app/services/gate.py` caches membership for 300 seconds; `app/bot/middlewares.py:Throttle` keeps local buckets. | Shared invalidation/budgets where required before scaling replicas; documented bounded cache behavior otherwise. This is not a demonstrated wallet-authentication bypass. |

## Session status

The latest source has a **30-day persistent admin session**, replacing the earlier 8-hour duration read at the beginning of this review. Cookies are HttpOnly, SameSite=Lax, and Secure in production. Logout records revocation in PostgreSQL; changing the configured password invalidates signatures. A persistent SECRET_KEY is required in production.

Existing cookies retain their original expiry; changing the constant does not extend already-issued sessions. The running release must include the change, and the next successful sign-in issues the new duration. The cookie does not renew on activity. Shared-password sessions identify a session, not a named human administrator. The network-error behavior above still needs correction.

## Webhook and database observations

- `.env.coolify` validates as production, polling disabled, HTTPS webhook configured, Secure cookies enabled, explicit secret present. Secrets were not printed.
- A read-only Telegram getWebhookInfo call for the Coolify bot returned a registered webhook, **0 pending updates**, and no last error. This is an operational snapshot, not a load or failover test.
- The configured public deployment returned HTTP 200 for both `/health/live` and `/health/ready`; readiness reported database available and bot mode `webhook`. This does not establish that every current local edit is deployed.
- Local development and Coolify use different bot tokens. Local polling therefore does not itself establish a conflict with that Coolify bot.
- The configured Neon database had **30 public tables** and **no pending migration filenames**, including migration 0032, at inspection time. No Neon business records were changed by this audit.
- Incoming webhook updates are persisted before HTTP acknowledgement, deduplicated by update ID, and processed with bounded workers and retry leases. Wrong secret headers are rejected.
- Supplier/banner compatibility migration history is not an active feature; deleting old applied migrations would break reproducibility. No new removal was performed in this audit.

## UI inspection and verification limits

- Inspected the actual signed-in admin Orders and Stock screens at 390×844 and Deposits navigation. Orders/Stock did not overflow horizontally; card actions were readable. Restored the browser viewport afterwards.
- Bot interface findings above come from handler/keyboard source and tests. No real Telegram messages, orders, balance changes, refunds or broadcasts were sent for this audit.
- Two failure scenarios were reproduced in a disposable local PostgreSQL schema; it was removed afterwards. No dummy financial operation was run on Neon.
- Earlier targeted payment/new-queue tests: **50 passed**. Next production build and TypeScript check passed before the audit-only phase. A prior full-suite run had three old immediate-notification expectations failing; targeted tests were subsequently corrected and passed. Do not label that old full-suite run as all green.
- Fresh audit-phase access/security and reliability run: **70 tests passed in 184 seconds**, including webhook persistence/deduplication, concurrent purchase/approval and reseller authorization scenarios. These regression tests do not cover away the separately reproduced findings.
- Production domain TLS/proxy behavior under load, mobile Safari, real payment-provider settlement, backup restoration, external monitoring, and deployed dependency vulnerability status remain unverified. These are release verification gaps, not claims that each is broken.

Approve the inspected mobile list layout only. Do not approve unrestricted production launch from this review alone.

Release verification: all 168 tests passed against disposable local PostgreSQL (510.681 seconds); ruff check app tests scripts passed; final Next.js production build including TypeScript passed. No production financial transactions were used for testing.
