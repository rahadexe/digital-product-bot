# Security review — 21 September 2026

A second pass over the whole application, weighted towards the paths that put
money into a wallet. Where the earlier rounds described what had been changed,
this one adds tests that attack those paths, so the claims below are executable
rather than asserted.

## Finding: a gateway receipt that stated nothing was accepted

**Where:** `app/services/zinipay.py`, `_matches_receipt`, used by both steps of
the in-bot transaction verification.

**What it did:** the check compared only the fields the provider's response
happened to carry.

```python
paid = Decimal(str(data.get('amount', amount)))          # absent -> equals itself
...
return all(str(data[key]).strip().upper() == transaction_id.upper()
           for key in ('trxID', 'transactionId') if data.get(key) is not None)
```

With no `amount`, the paid amount defaulted to the amount being claimed and
matched. With no `trxID` and no `transactionId`, the generator was empty and
`all([])` is `True`. So a body of `{"success": true, "data": {"id": 77}}` —
naming no amount and no transaction — agreed with every payment, and the
verification proceeded to consume the transaction and credit the wallet.

**Reach:** this needs control of the response, not of the request. A customer
cannot send it. A provider that changed its payload, a proxy or TLS
interception, or a compromised gateway could. It is the money path, and the
whole purpose of the function is to reject a receipt that does not match, so
accepting a silent one defeats it.

**Fix:** a receipt must state the amount and at least one transaction
identifier, and every identifier it does state must match. Anything else goes
to review with the deposit left pending, which is the existing safe path — the
customer is told their payment is saved and not to pay again.

Confirmed by `tests/test_payment_security.py::ReceiptMatching` and, end to end,
by `test_receipt_that_names_nothing_does_not_credit`, which asserts the wallet
stays at zero and the deposit stays `pending`.

## What was attacked and held

`tests/test_payment_security.py` drives the real services against a disposable
schema with the gateway mocked.

| Attack | Result |
| --- | --- |
| Forged unsigned callback claiming a payment | No credit. The callback only prompts a server-side check, and the gateway is asked directly |
| Gateway reports COMPLETED for a different invoice | Refused, invoice marked `failed` |
| Gateway reports COMPLETED for the wrong amount | Refused |
| Gateway reports COMPLETED naming no invoice | Refused |
| The same completion checked three times | Credited exactly once, one deposit row |
| The same transaction id claimed twice by one customer | Second claim refused |
| The same transaction id claimed by another customer | Refused, intruder's wallet untouched |
| Reading another customer's invoice | Returns nothing |
| Gateway returns a payment URL on a lookalike domain | Invoice creation refused |
| Editing or deleting a wallet ledger row | Rejected by the database |

`tests/test_access_security.py` covers the rest of the surface.

| Attack | Result |
| --- | --- |
| `'; DROP TABLE users; --` through every list and search | No rows, schema unchanged |
| A smuggled SQL fragment as a field name in an update | Dropped by the allowlist; the legitimate field still applied |
| An undeclared settings key | Refused |
| Reading another customer's order or delivered credentials | Returns nothing |
| Using a revoked reseller key | Refused |
| Using a key after losing the reseller rank | Refused |
| Using a key after being banned | Refused |
| Using the previous key after rotation | Refused |
| Minting a key without the reseller rank | Refused |
| Reading a secret setting back through the API | Masked; re-saving the masked form keeps the stored value |
| Buying while banned, while paused, or without the balance | Refused, no money moved |

Production configuration refuses to start on a short or default admin password,
a weak or absent `SECRET_KEY`, a missing database, or a plain-HTTP webhook, and
marks the session cookie `Secure`. The derived webhook secret is stable across
restarts, which replicas depend on.

## Checked against the running application

Against a local instance with seeded data:

- `/api/admin/*` and `/api/v1/reseller/*` answer 401 without credentials,
  including `POST /api/v1/reseller/orders` with a valid body.
- An invalid API key returns `Invalid or revoked API Key.` and nothing else.
- Six wrong admin passwords from one address: five 401s then 429.
- Every API response carries `x-content-type-options`, `referrer-policy`,
  `cache-control: no-store` and a Content-Security-Policy with
  `frame-ancestors 'none'`, `object-src 'none'` and `base-uri 'self'`.
- The session cookie is `HttpOnly; SameSite=lax; Max-Age=28800`, and `Secure` in
  production.
- The Telegram webhook refuses a request without its secret token.
- Nothing secret reaches the log.

## Static analysis

- `pip-audit` over the pinned requirements: no known vulnerabilities.
- `npm audit`, with and without dev dependencies: zero.
- `bandit -ll` over `app/`: 24 findings, all `B608` (SQL built as a string).
  Each was read. The interpolated part is always either a fixed fragment or a
  column name filtered through a module-level allowlist
  (`PRODUCT_FIELDS`, `METHOD_FIELDS`, `CHANNEL_FIELDS`); every value from a
  request is bound as `$n`. Two tests keep it that way: one smuggles SQL in as a
  field name, and one asserts every name in those allowlists is a plain
  identifier.
- `ruff` clean over `app`, `tests` and `scripts`.

## Known limits, accepted

- **`script-src 'unsafe-inline'`.** The console is a static Next.js export and
  hydrates from an inline script. Removing it needs per-response nonces, which a
  static export cannot produce. The console renders no third-party content, and
  every value interpolated into the served documentation page is escaped.
- **Binance Pay matching.** A claim is matched on the order id or transaction id
  from the payer's receipt, never on a payer UID alone, and only inside a 24
  hour window. Someone who learns a real order id before its payer claims it
  could claim it first. Narrowing that further needs a payment intent the
  customer is given up front, which is a product change.
- **Unsigned ZiniPay callbacks.** The provider does not sign them. They are
  treated as a hint to go and ask, never as evidence, and are coalesced so a
  flood cannot drive unlimited gateway calls.
- **Money as float in application code.** PostgreSQL and the wallet ledger hold
  exact `NUMERIC`; some formatting and arithmetic still round through
  four-decimal floats. See `docs/ARCHITECTURE.md`.
- Tests mock the gateways. They do not replace a sandbox transaction against
  ZiniPay and Binance before taking real money.

## Running it

```bash
TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres \
    python -m unittest discover -s tests
```

87 tests, all passing: 46 reliability, 17 payment security, 24 injection,
access and configuration.
