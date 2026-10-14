# Mini App customer features

The customer storefront is `/shop/`. Home stays focused on products; Account contains Refer & earn, Balance history, Orders, Reseller & API, Language, Support, Guide and Channels.

## Connected features

- `/api/miniapp/info`: public store name, validated Telegram bot/support URLs and active HTTPS channel links. No private settings are returned.
- `/api/miniapp/account`: authenticated profile, store balance, reward settings, referral totals and the customer's actual referral link.
- `/api/miniapp/orders` and `/orders/{id}`: paginated customer-owned orders and copyable delivery content. Lists omit delivery credentials and upstream fields.
- `/api/miniapp/balance-history`: paginated deposit history, using the same service as the bot.
- `/api/miniapp/language`: validated English/Bengali preference saved to the bot account. Account feature screens support both languages; catalog demo copy is not yet fully translated.
- Reseller/API management and warranty actions open the existing bot using `mini_reseller` and `mini_orders` start parameters. These use the usual bot membership gate and existing handlers. API key handling has not been duplicated in the browser.
- Support and channel links use configured store values. Guide is accessible without sign-in.

## Authentication

The page loads Telegram's Web App SDK and forwards `initData` in `X-Telegram-Init-Data`. The server verifies the bot-token HMAC, rejects duplicate query fields, expired (>1 hour) and future (>30 seconds) data, and rejects missing/banned store accounts. Start the bot before opening the shop. User IDs are never accepted from browser request parameters. Authenticated responses receive the existing no-store API headers.

The `/shop/` page alone allows embedding by Telegram Web origins; admin pages retain `frame-ancestors 'none'`.

## Running

Run the existing Python API and console development server. Development requests default to `http://localhost:8000`; set `NEXT_PUBLIC_MINIAPP_API_URL` at build time if different. Production requests use the same origin. Deploy the exported console alongside FastAPI, use HTTPS, and configure the Telegram Mini App URL to `<public-origin>/shop/` in BotFather.

## Explicit limitations

Catalog and Stars prices remain sample fixtures; checkout is disabled. Wallet top-ups and Stars payment fulfillment are not implemented in this Mini App. Store balance is not a Telegram Stars balance. Without a verified Telegram launch, personal features show a sign-in state, not fabricated balances, referral statistics, orders, or links. Bot connection failures leave public links unavailable. Deployment and real Telegram payment/login tests have not been performed.

## Verification

23 tests passed across Mini App authorization/customer isolation, existing localization and menu tests; 8 database-dependent menu tests skipped without the disposable test database. TypeScript typecheck passed. Tests include altered signatures, duplicate auth fields, old/future timestamps, missing/banned accounts, scoped order lookups, response-field allowlists, pagination bounds and language validation.

Production build attempted: blocked by Google Fonts network fetches for existing admin-panel Inter/Manrope imports. The storefront uses the locally bundled Manrope font. Preview HTTP check returned 200.
