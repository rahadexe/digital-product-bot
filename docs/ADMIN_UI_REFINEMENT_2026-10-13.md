# Admin interface refinement — 2026-10-13

Implemented on top of the existing working tree, preserving existing actions and data APIs.

- Group desktop and mobile navigation into Workspace, Catalog, and Management.
- Unify dashboard and operational summaries into divided strips, with two columns on phones.
- Keep shared table surfaces, pagination, numeric alignment, filters, focus states, and mobile controls consistent.
- Open shared record details and order details in a right-side panel; full height on phones.
- Trap keyboard focus in modals, restore focus on close, and let only the top dialog handle Escape/Tab.
- Show order refresh state and selected filter semantics; improve empty-result copy and table header semantics.
- Stabilize the deposit pending-count callback, ignore stale requests, and show retryable load errors.
- Use an unknown-method placeholder rather than incorrectly identifying missing payment methods as bKash.

Validation:
- `npm --prefix console run typecheck` passed.
- Final `npm --prefix console run build` passed, including TypeScript and static export.
- Inspected the built export using isolated browser network fixtures at 1440 × 1000 and 390 × 844.
- Visually checked Dashboard, Orders, Deposits, and record details; corrected mobile refresh clipping, large summary figures, and detail-panel sizing.
- Verified focus enters the detail panel, Shift+Tab stays inside, Escape closes it, and focus returns to the trigger.
- Simulated a failed deposits request, verified the retry control, then retried successfully to an empty state.
- Changed tracked frontend files pass whitespace checks. Repository-wide checks report pre-existing whitespace issues in unrelated Python files.

Limits: other screens receive shared styling but have not each received a complete browser interaction audit. Real payment, fulfillment, refund, broadcast and supplier actions were not submitted. No new backend sorting/export/bulk-action APIs were introduced. Preview screenshots contain synthetic data. No deployment was performed.
