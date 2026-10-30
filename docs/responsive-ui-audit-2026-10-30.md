# Responsive admin UI review — 2026-10-30

## Findings and fixes

| Severity | Root cause | Fix |
| --- | --- | --- |
| Medium | Legacy selector specificity kept payment fields in two columns on phones. | Scoped responsive selectors now stack fields through 760px, with shrinkable desktop columns. |
| Medium | Payment method editing did not explain the shared deposit ceiling or reject a minimum above it. | Show the saved global ceiling in the method's payment currency and validate the minimum before submission. |
| Medium | Saving had no busy state and failures appeared outside the dialog. | Disable repeated submission and dismissal during saving; show errors inline and allow retry. |
| Low | Modal footer did not inherit rounded corners. | Match footer corners to the dialog. |
| Low | Settings tabs retained a teal accent inconsistent with the purple theme. | Use shared accent tokens. |
| Low | USDT input suffix and provider choices could crowd narrow layouts. | Increase suffix clearance and allow provider choices to wrap. |

## Deposit limit decision

Keep one maximum per deposit in Settings / General / Limits & Rules. Each method retains its own minimum. The method dialog displays the saved shared maximum in BDT for local payments and USDT for Binance. This avoids two competing maximum settings. No new per-method maximum is stored and no backend accounting rules change in this review.

## Verification

- TypeScript check and production build passed.
- Responsive suite: 126 populated page/viewport cases and interactions passed.
- Payment suite: 32 method/viewport cases passed, including short landscape screens, visible footer actions, currency labels, validation, failed save and retry.
- Layout suite: Home states, delayed loading, refresh success/failure, reduced motion, 24 exact-copy input cases and navigation passed with no browser errors.
- Fixed a test fixture navigation race by giving each customer input case a fresh document; geometry assertions remain intact.
- Added the payment dialog suite to admin UI CI.

Browser checks used local production output, Microsoft Edge and synthetic API fixtures. Live payment processing, physical mobile devices, Safari and Firefox were not verified in this review.
