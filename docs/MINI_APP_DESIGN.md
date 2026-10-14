# Mini App — design preview

Approved direction: off-white paper, emerald actions, Manrope typography, compact mobile storefront. New customer surface at `/shop/`; existing operator routes remain intact.

- Audience: Telegram customers purchasing digital subscriptions, on a phone.
- Mode: greenfield customer storefront alongside the existing console.
- Visual language: quiet editorial retail. Variance 4/10, motion 2/10, density 3/10, asset dependence 5/10, brand fidelity 5/10.
- Roles: short introduction, product discovery, focused product detail, orders, account.
- Palette: paper `#f8f9f5`, ink `#192d27`, emerald `#17684d`, muted `#69756e`.
- Typography: locally bundled Manrope Variable, 43px main heading, 13–14px body, compact secondary labels.
- Spacing: 8px rhythm with optical adjustments; cards 19–20px radius, inner art 13px, 6px inset.
- Elevation: restrained shadows; borders organize controls and cards.
- Motion: 150ms state transitions, respects reduced motion.
- Existing product logos: `console/public/images/brands/*.png`; no new remote dependencies or invented logos.

## Preview scope

Explicit sample catalog and sample Stars prices. Search, categories, sorting, product navigation, Orders and Account work locally. Checkout is disabled. No real profile, payment, stock, or order data is fabricated. No payment or deployment occurs.

## Next implementation after visual review

Validate Telegram initData on the server with freshness checks; expose a limited customer catalog; authenticate and scope all order reads to the verified Telegram user. Add explicit configured Stars prices (never infer a conversion from fiat), durable invoice records, server-side pre-checkout validation and idempotent successful-payment fulfillment. Connect Telegram launch and safe-area/theme behavior. Test auth tampering, cross-user access, duplicate payment updates, stock exhaustion, and fulfillment recovery before enabling checkout.

References: https://core.telegram.org/bots/webapps and https://core.telegram.org/bots/payments-stars

## Compact header revision

User requested direct access over promotional copy. Removed the welcome hero, AI banner, brand masthead, top preview ribbon and decorative footer. Header now has a profile/avatar placeholder leading to Account and an explicitly labeled demo store balance. Search, categories and products immediately follow. Sample catalog label remains beside Shop; this is still a preview with no live identity or payment integration. Real profile photos will replace the neutral avatar after authenticated Telegram integration; the demo store balance is not the user's Telegram Stars balance.

## Product list revision

Approved by the user after research: replace the two-column cards with compact product rows. Each row contains a small brand logo, product name, duration/category and explicit Stars price. Keep profile and clearly labeled demo store balance above search. Product details use a compact summary rather than oversized artwork. Preserve catalog filters, scroll position and keyboard focus when returning from a product. Add system dark-mode styling and reduced-motion support. This remains a design preview: Telegram theme integration, verified profile/balance and live checkout are not yet connected.

Verification: TypeScript typecheck passed. HTTP preview returned 200 with the new product-list markup and no previous product-grid markup. Live Telegram behavior and visual browser testing remain unverified.

## Unified home revision

Reduced competing header emphasis, combined search and sort into one control, changed category pills to underlined tabs, removed the redundant catalog heading, and removed the enclosing list card. Rows now share a single edge and consistent separators, with name/duration on the left and Stars price on the right. Demo disclosure moved to a quiet catalog footer; demo balance remains explicitly labeled. Bottom navigation uses color and weight rather than a large selection tile. Typecheck passed and HTTP preview returned 200. Browser visual inspection was attempted but its tool transport was unavailable.
