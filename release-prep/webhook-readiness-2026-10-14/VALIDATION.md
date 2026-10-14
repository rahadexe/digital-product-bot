# Validation evidence

All backend checks run against `tmp/webhook-readiness`, the isolated source copy. Integration data lives in random schemas in local PostgreSQL on port 55432. The application database and real payment providers were not used for tests.

## Completed checks

- Final focused checks: **36 passed**, two dependency deprecation warnings, 6.75 seconds. Command: `python -m pytest tests/test_webhook_readiness.py tests/test_production_regressions.py -q --timeout=30` from the isolated copy.
- Those checks include 13 new force-join/webhook regressions: request coalescing, join/leave invalidation, invalidated in-flight checks, cancelled waiters, bounded timeouts, channel cooldown after Telegram rate limiting, start/menu/Verify bypass prevention, verification failures withholding access/referral rewards, join-prompt flood suppression, and retrying webhook setup after a transient failure.
- Earlier integrated run: **80 passed, 1 failed**. The missing-console-build hypothesis was disproven by the full rerun with the build present. The real defect was the removed legacy payment-return redirect, now restored in the release patch.
- Python critical checks: `ruff check ... --select E9,F63,F7,F82` passed. Python compilation of the staged application passed.
- Current admin console: `node node_modules/typescript/bin/tsc --noEmit --incremental false` passed. No frontend source changes were made by this audit.
- Patch applicability: `git apply --check release-prep/webhook-readiness-2026-10-14/changes.patch` passed. Original source hashes for all patched existing files were unchanged when the patch was finalized.
- Synthetic local inbox: **200/200 updates completed**, 20 customers, four consumers, no duplicate dispatch, per-customer order preserved. See `inbox-benchmark.json`. This is not a real Telegram/bot-handler load test.

## Full suite

Completed full run: **333 passed, 1 failed, 9 subtests passed**, two dependency deprecation warnings, 879.31 seconds. It used `--timeout=180 --junitxml=full-suite.xml`. The one failure was `test_payment_return_and_removed_routes`: `/app/?payment=...` returned 404 instead of the expected compatibility redirect. The final patch restores the route and strengthens the regression to verify URL encoding and the exact redirect destination.

Final focused rerun after this correction is recorded below. The 15-minute full suite is not rerun for this isolated route restoration; the failed case and adjacent webhook regression checks are rerun instead. Do not present the earlier complete run as entirely green or add overlapping focused counts to the full-suite count.

**Final correction verification: 39 passed**, two dependency deprecation warnings, 20.96 seconds. This includes the restored payment-return route and encoded reference, durable webhook deduplication/restart processing, membership-event customer ordering, all 13 new webhook/force-join regressions, and the existing production regression module. See `final-regressions.log`. The complete run's one failing case is now passing; no known failing check remains in this audit. `full-suite-final.log` and `full-suite.xml` retain the pre-correction failure transparently.

The first complete-suite attempt was interrupted by the test runner's 60-second timeout during a test that traverses every menu label from inside a conversation prompt. No assertion failure had been reported before interruption. The larger per-test limit is for this broad navigation test, not a change to the application's request deadlines.

## Limits

No production deployment, real webhook registration, real payment/purchase, external provider latency benchmark or backup restore was performed. Runtime caches remain process-local; see the single-process deployment guidance and multi-replica caveat in `README.md`. Existing release gates from the earlier production audit remain open.
