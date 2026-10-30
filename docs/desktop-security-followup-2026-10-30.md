# Desktop and security follow-up — 30 October 2026

## Fixed findings

| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| Medium | console/src/app/(panel)/studio.css | The entire sidebar scrolled, pushing Sign out below laptop viewports. | Only the navigation list scrolls; the brand and account control remain visible. | Progressive disclosure: navigation can scroll without hiding account controls. |
| Medium | console/src/components/Deposits.tsx, Products.tsx, Suppliers.tsx | Some money displays added a dollar sign to an already formatted amount, producing `$$125.00`. | Use the formatter's currency symbol once in lists, details and previews. | Consistent and unambiguous financial information. |
| Medium | console/src/components/ui.tsx | Future stock expiry was rendered as “just now”. | Future times show “in …” or their date. | Correct state and time feedback. |
| Medium | console/src/components/Broadcast.tsx, console/src/lib/telegram-preview.ts | The link-preview matcher expected escaped quotes but the transformer did not escape quotes, so links were not rendered. | Escape text and attributes, restore only supported tags and allow only HTTP, HTTPS and Telegram link protocols. | Accurate preview with explicit protection against executable links and attribute injection. This was a rendering defect and hardening opportunity, not evidence of an exploited XSS. |
| Low | console/src/app/(panel)/studio.css | Pagination backgrounds covered the card's rounded lower corners. | Pagination inherits the card's bottom radii. | Consistent nested surfaces without clipping dropdowns. |

## Dependency security

The initial local Python environment scan reported advisories across six packages.
Runtime dependencies are now explicitly pinned to patched versions in `requirements.txt`:

- aiohttp 3.14.4
- certifi 2026.10.19
- multidict 6.9.1

The local environment's additional development/tool packages were also updated:
filelock 4.2.1, Pillow 13.0.0 and pip 26.2. They are not added as application runtime requirements.

After updating, `pip check` passed and `pip-audit` reported no known vulnerabilities
in the installed environment. `npm audit --omit=dev` reported zero vulnerabilities.
These scans reflect known advisories at the time of this review, not proof of absence
of every vulnerability. Running deployments need the updated requirements installed
and their processes restarted; this review did not deploy or restart the live bot.

## Reviewed security boundaries

Inspected admin session signing/revocation, cookie/CSRF enforcement, protected admin
router composition, request size/origin/rate boundaries, Telegram webhook secret
checks, reseller authentication and broadcast rendering. The existing backend
regression suite includes wallet/payment, ownership and authentication scenarios.
No additional confirmed authentication or wallet-credit bypass was found in the
reviewed paths.

## Verification

- TypeScript check and production build passed.
- 168 populated page/viewport cases across eight widths, plus interaction regressions.
- Nine desktop Product/Stock/Category dialog cases at 1024×600, 1366×768 and 1920×1080.
- 32 payment dialog cases, provider selection, minimum validation and save retry.
- 24 Home states, 24 delayed-loading transitions, two refresh cases, reduced motion,
  24 exact-copy input cases and Stock/Deposits navigation passed.
- Backend after dependency changes: 467 passed, 207 skipped, seven subtests passed.
- Synthetic browser screenshots: `scratch/desktop-review/`.

Not verified: PostgreSQL integration tests (no disposable database), live gateway
payments, production deployment, physical mobile browsers, Firefox/Safari and every
hover/animation state at reduced playback speed. Browser checks used Edge with
synthetic API responses and the local production export. Wide data tables retain
horizontal scrolling on smaller desktop widths.

UI verdict: Approve for the inspected and tested scope; no remaining high-severity
UI finding was identified within that scope.
