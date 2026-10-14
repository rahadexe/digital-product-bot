# Webhook and force-join release preparation — 14 October 2026

**Update:** The user subsequently authorized implementation. The patch has now been applied to the main working source; do not apply it again. See `docs/COOLIFY_DEPLOYMENT.md` and `docs/coolify.env.example` for the current deployment instructions. The separate-patch status below records the earlier audit phase.

## Delivery status

The fixes are in `changes.patch`, not in the running application's source. The user explicitly requested no restart and asked to keep fixes separate. No polling/webhook configuration was changed, no webhook was registered or deleted, and no live database migration was run by this audit.

`git apply --check release-prep/webhook-readiness-2026-10-14/changes.patch` passed against the working tree at packaging time. The patch is relative to the existing uncommitted work, not to Git HEAD. `manifest.json` records the original and tested file hashes. Check applicability again before release; other work is happening in this checkout.

## Fixed in the patch

- Removed a second membership cache in access middleware. `/start`, `/menu`, and `gate_verify` had been treated as a successful membership result for 60 seconds before actual verification. Subsequent buttons could bypass a failed check. Ban checks remain authoritative.
- Telegram verification errors no longer grant membership access or referral rewards. Users receive a temporary verification message and can retry; administrators receive a throttled alert. This deliberately replaces the old fail-open fallback.
- Concurrent checks for one customer share a single Telegram verification. Confirmed membership stays cached for five minutes; unsuccessful checks are reused for two seconds. Join/leave events clear both caches. In-flight results cannot repopulate an invalidated cache.
- Repeated blocked menu actions send at most one membership prompt per customer every two seconds, instead of flooding the chat with the same join message.
- Membership calls have a four-second deadline including semaphore waiting, and at most 32 such calls execute concurrently per process. Channel errors trigger a five-second cooldown; Telegram `retry_after` values are respected when longer. Verification errors never enter the success cache.
- Refreshed channel configuration invalidates previously cached membership. Active channel configuration is refreshed every 30 seconds.
- Removed permanent, process-local PostgreSQL FSM caches. Another webhook process's state/data updates and clears are visible on the next database read.
- Membership webhook events are queued under the affected customer ID, preserving ordering with that customer's other queued updates.
- Webhook startup retries transient bot configuration errors as well as webhook registration errors. Pending updates are preserved. Polling concurrency is bounded to avoid unbounded update tasks.
- Performance logs record message type instead of raw customer message text, which may contain payment details or credentials.
- Restored the legacy `/app/?payment=...` return redirect for already-issued payment links. The reference is URL-encoded and forwarded to `/api/payments/return`; the removed Mini App is not restored.

## Live, read-only observations

- Local health endpoint returned HTTP 200, `ready`, bot mode `polling`.
- Telegram reported no registered webhook, zero pending updates, and no last webhook error.
- Current configuration is development, polling enabled, no webhook base URL, no Redis, database pool size 10.
- Force-join is enabled but **there are no active required channels**. This currently means there is no membership requirement to enforce. Add the intended channels and make the bot an administrator before testing joining.
- During the audit, an unrelated edit to the original `app/bot/handlers/deposit.py` and a live child-process PID change were observed. This audit did not edit that file in the original checkout or restart the bot. Health returned ready/polling after that change.

## Verification

See `VALIDATION.md` for final results. Tests run in the isolated copy at `tmp/webhook-readiness`, with disposable local PostgreSQL schemas. Telegram, supplier and payment effects in tests are mocked. The real bot was used only for read-only health/webhook/channel status checks.

The concurrency regression sends 50 simultaneous checks and 20 subsequent checks for one customer. Both joined and unjoined cases make one underlying membership request. This demonstrates request coalescing; it is not a production latency or throughput measurement.

A separate synthetic inbox run processed 200 updates across 20 customers with four consumers in 0.277 seconds (720.8 updates/second). All 200 completed once, with no duplicate dispatch or per-customer ordering violation. This uses a local database and a stub handler; it excludes HTTP ingress, actual bot handlers, Telegram and suppliers. It must not be used as a production capacity claim.

The first integration run had 80 passing tests and one payment-return failure. The initial missing-build hypothesis was incorrect: the failure persisted after copying `console/out`. The full run established that the legacy payment-return route had been removed. The patch now restores that redirect, with a regression asserting both the destination and safe reference encoding.

## Deployment procedure — not executed

1. Preserve the current work and database backup. In a deployment checkout, verify the patch still applies with `git apply --check`, then apply it with `git apply`. Do not apply it to this running auto-reload checkout until a restart is authorized.
2. Run the tests and build the console for the exact release revision. Existing earlier audit release gates in `docs/PRODUCTION_READINESS_2026-10-14.md` still apply, including supplier-key rotation, backup restore, provider smoke tests and hosting verification.
3. Configure `APP_ENV=production`, `USE_POLLING=false`, `APP_RELOAD=false`, and `WEBHOOK_BASE_URL=https://your-real-domain`. Keep stable strong `SECRET_KEY`, `ADMIN_PASSWORD`, database settings and webhook secret; restrict trusted proxies to the actual proxy. Use `python -m app all --no-reload` for the initial single-process deployment. Do not copy the local `.env` unchanged.
4. Ensure HTTPS routes `/telegram/webhook` to the Python service and `/health/ready` is reachable. Apply migrations in the release environment. Configure required channels and bot administrator permissions.
5. During the authorized cutover, stop the old polling instance before the production instance registers its webhook. An old poller restarting can delete the new webhook. Do not drop pending updates.
6. Verify `getWebhookInfo` shows the intended URL, no fresh errors and a draining queue. Check HTTP 200 readiness with bot mode `webhook`. Exercise `/start`, joining, repeated Verify taps, leaving, purchases and deposits with controlled test accounts.

Start with one webhook application process. The durable inbox and database FSM support cross-process processing, but membership/throttle caches are process-local: a departure observed by another replica can leave a cached pass valid for up to five minutes. Shared membership invalidation and production-like load testing remain prerequisites if immediate enforcement across multiple replicas is required.

External Telegram/network latency and slow supplier requests can still delay responses. A successful local test suite cannot certify live production speed, real payment behavior, TLS/proxy configuration or backup recovery.
