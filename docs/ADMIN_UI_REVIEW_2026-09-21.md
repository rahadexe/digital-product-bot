# Admin panel cleanup — 2026-09-21

## Clear hierarchy and accurate labels

| Severity | Location | Before | After | Why |
| --- | --- | --- | --- | --- |
| HIGH, fixed | console/src/components/Products.tsx:96 | Manual products counted as out of stock and empty duration displayed Instant. | Manual delivery included in Available; stock warnings only apply to stock delivery; duration is not invented. | Accurate state prevents incorrect fulfillment decisions. |
| MEDIUM, fixed | console/src/components/Settings.tsx:16 | Store, notifications, channels and access shared a long page. | Five focused tabs; existing controls retained. | Group related controls and reduce scanning. |
| MEDIUM, fixed | console/src/app/(panel)/page.tsx:222 | Flat navigation and hidden mobile page heading. | Workspace, Catalog and Manage groups; visible page titles. | Make location and reading order clear. |
| MEDIUM, fixed | console/src/components/Overview.tsx:91 | Large repeated alerts and redundant navigation cards. | Compact actionable alerts; redundant cards and their CSS removed. | Prioritize daily tasks and remove duplication. |
| LOW, fixed | console/src/components/Products.tsx:115 | Four summary cards repeated filter counts. | Filter counts retained, stock units shown in toolbar. | Preserve information with less clutter. |
| LOW, fixed | console/src/app/(panel)/console.css:3350 | Heavy surfaces and weak secondary text. | Softer shadows, stronger muted text, consistent grouped navigation. | Visual hierarchy and readable secondary text. |
| HIGH, fixed | console/src/app/(panel)/page.tsx:169 | Skip link changed the hash route to Dashboard. | Focus main content without changing the screen. | Keyboard navigation must preserve the current task. |

## Verification

- TypeScript check and optimized Next.js production build passed.
- Browser review used isolated local PostgreSQL fixtures, no production data or outgoing bot messages.
- Visually reviewed desktop Products, Dashboard and Settings; mobile Dashboard, Store settings and Payments at 390 px.
- Mobile drawer navigation and Settings tab switching worked.
- Manual and stock delivery remain available; payment controls were retained.
- Not verified: every page/modal, every hover/focus/error state, full keyboard accessibility audit, animation replay at 10% speed, real payment/notification submissions.

Approve for the inspected layout and copy changes only; this is not a full UI accessibility or production certification.
