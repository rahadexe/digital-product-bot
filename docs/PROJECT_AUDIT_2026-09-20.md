# Project audit — 20 September 2026

> এটি fixes শুরুর আগের audit snapshot। পরবর্তী পরিবর্তন, পরীক্ষার scope এবং deployment নির্দেশনা দেখুন [Reliability upgrade](RELIABILITY_UPGRADE_2026-09-20.md)। নিচের baseline ফলাফল বর্তমান implementation status নয়।

এই রিভিউয়ের সিদ্ধান্ত: PostgreSQL, transaction, row lock ও durable delivery outbox দিয়ে ভালো ভিত্তি তৈরি হয়েছে। কিন্তু payment correctness, stock allocation, অসম্পূর্ণ feature removal এবং multi-process operation-এর কিছু সমস্যা ঠিক করার আগে বড় আকারে চালানো উচিত নয়। পুরো প্রোজেক্ট নতুন করে লেখার প্রয়োজন দেখছি না।

## Scope ও যাচাইয়ের সীমা

- Backend services, bot handlers, API wiring, console settings, সব ২২টি SQL migration এবং সাম্প্রতিক/সংশ্লিষ্ট Git diff পরীক্ষা করা হয়েছে।
- শুরুতে HEAD ছিল `cf73284`; রিভিউ চলাকালে অন্য কাজ থেকে `846f657` এসেছে। নতুন commit শুধু instant-payment button presentation বদলায়। শুরুতে থাকা `app/bot/keyboards.py` পরিবর্তন এই audit থেকে করা হয়নি।
- লোকাল `.env` দিয়ে কনফিগার করা PostgreSQL database-এ explicit **read-only transaction** এবং ৮ সেকেন্ড statement timeout দিয়ে metadata ও aggregate query চালানো হয়েছে। এই database-ই deployed production-এর একমাত্র database কি না স্বাধীনভাবে নিশ্চিত করা হয়নি।
- কোনো live migration, payment API call, Telegram message, data update/delete বা load test করা হয়নি। এই রিপোর্ট ছাড়া application source পরিবর্তন করা হয়নি।
- ৭৪টি application Python file-এর syntax parse এবং console TypeScript typecheck পাস করেছে। Repository-তে automated test suite পাওয়া যায়নি। এগুলো business correctness প্রমাণ করে না।
- ছয়টি isolated mock-based probe এবং local ASGI route probe চালানো হয়েছে; নিচে ফলাফল আছে। Fresh PostgreSQL-এ migration replay এবং বাস্তব concurrent transaction test করা হয়নি।

## Database-এর বাস্তব অবস্থা

| বিষয় | Read-only পরীক্ষার ফল |
|---|---|
| User tables | ২৩টি, `schema_migrations`-সহ; দেখা application tables সব `public` schema-তে |
| Applied migrations | ২২টি; repository-এর সব migration stem applied |
| Exact row counts | users ৫, products ২৯, orders ১০, deposits ৫, inventory_items ৭১, outbox ৩২ |
| Duplicate stock content groups | একই product ও content-এর duplicate group ০ |
| User identity mismatch | orders/deposits-এর `user_id` বনাম `tg_user_id` mismatch ০ |
| Negative wallet / legacy duplicate deposit | উভয়ই ০ |
| Supplier-linked products / old referral-bonus orders | উভয়ই ০ |
| Stuck `created` invoice | ০ |
| Binance Pay method | ১টি |
| Removed banner data | `media_assets`, `home_banners`, `bot_welcome_banners`—তিনটিতেই ০ row |
| Duplicate indexes | `orders_inventory_item` এবং `idx_orders_inventory_user`: উভয়ের definition `(inventory_item_id, tg_user_id)`; প্রতিটি এখন ১৬ KiB |
| Expired inventory still marked available | ১টি row; runtime expiry filter থাকায় এটি নিজে overselling-এর প্রমাণ নয় |

**একই টেবিল বারবার তৈরি হচ্ছে কি?** এই database এবং বর্তমান migration code-এ তার প্রমাণ নেই। SQL files-এ ২২টি unique application table definition, runner আলাদাভাবে migration-history table তৈরি করে। `CREATE TABLE IF NOT EXISTS`, full filename stem দিয়ে migration tracking এবং advisory transaction lock আছে।

দুটি migration-এর numeric prefix `0008`, কিন্তু full stem আলাদা বলে দুটিই একবার করে চলে। এটি naming inconsistency; বর্তমানে duplicate execution নয়। ইতিমধ্যে applied file rename করলে runner সেটিকে নতুন migration ভাববে—তাই শুধু numbering সুন্দর করার জন্য rename করা উচিত নয়।

## Findings, অগ্রাধিকার অনুযায়ী

### F01 — P1: ZiniPay transaction consume হয় durable local record-এর আগে

**Source:** `app/services/zinipay.py:249`, `:266`; `app/services/deposits.py:254`।

`verify → confirm → create_request → approve` ক্রমে কাজ হয়। Gateway confirm সফল হওয়ার পর process crash, database outage, অন্য pending deposit, method disable বা rate change হলে local record/credit তৈরি নাও হতে পারে। Retry-তে provider transaction already used দেখাতে পারে। Approval-এর আগেও আলাদা committed pending state আছে, কিন্তু PaymentWatcher এই in-bot ZiniPay flow reconcile করে না।

Mock probe-এ `create_request` থেকে `PendingDepositError` দেওয়ার আগে confirm ইতিমধ্যেই একবার চলেছে। বাস্তবে customer money হারিয়েছে—এমন দাবি নয়; recovery gap নিশ্চিত। **করণীয়:** external confirm-এর আগে durable claim/attempt সংরক্ষণ, provider outcome ও local credit-এর explicit state machine, idempotent retry এবং reconciliation worker। Network request ধরে SQL transaction খোলা রাখাই সমাধান নয়।

### F02 — P1: Approval ব্যর্থ হলেও payment success বলা হয়

**Source:** `app/services/zinipay.py:275–294`।

`deposits.approve()` false ফিরলে শুধু log হয়; তারপরও `auto_verified=True, credited=True` ফেরত যায়। Mock-এ approval false দিয়ে এই ফল পুনরুৎপাদন হয়েছে। Admin reject ও auto-approve race, অথবা অন্য non-success outcome-এ ভুল success receipt হতে পারে। **করণীয়:** persisted deposit status অনুযায়ী outcome; rejection/failure-কে success না দেখানো এবং ambiguous ফল reconcile করা।

### F03 — P1: ZiniPay Auto-Verification switch কার্যকর নয়

**Source:** `app/services/zinipay.py:55`; `console/src/components/Settings.tsx`-এর `zinipay_autoverify` section; `app/bot/handlers/deposit.py:780`।

UI `zinipay_enabled` সংরক্ষণ করে, কিন্তু `is_enabled()` শুধু API key আছে কি না দেখে। Probe: switch `0`, key present → `True`। বন্ধ করার পরও provider verification/confirmation চলতে পারে। **করণীয়:** enabled flag এবং credentials দুটোই check; disabled হলে explicit manual path।

### F04 — P1: Multi-item order ও shared-stock schema পুরোপুরি সামঞ্জস্যপূর্ণ নয়

**Source:** `app/services/purchases.py:157–179`; `app/services/inventory.py:177–213`, `:251`; migration `0008_fulfillment_and_shared_stock.sql`।

এক অর্ডারে একাধিক item বিক্রি হয়, কিন্তু `orders.inventory_item_id` শুধু প্রথমটির ID রাখে। বিপরীত দিকে `inventory_items.order_id = COALESCE(order_id, ...)` শুধু প্রথম order ধরে। Shared item পরে অন্য multi-item order-এর দ্বিতীয়/তৃতীয় item হলে সেই allocation-এর পূর্ণ relational history থাকে না। Delivered text snapshot থাকে, কিন্তু সেটি allocation table-এর বিকল্প নয়। Quantity ও unit-price snapshot-ও আলাদা column-এ নেই; quantity title-এর `(xN)` text-এ থাকে।

অন্যদিকে catalogue free seats যোগ করে stock দেখায়, কিন্তু `claim_seats()` distinct inventory row গোনে। একটি item-এ ৭টি free seat থাকলেও quantity ২ চাইলে `None` পাওয়া গেছে। একই credential-এর একাধিক seat একই buyer-কে দেওয়া ব্যবসায়িকভাবে নিষিদ্ধ হলে UI-তে buyable quantity সেই নীতিতে দেখাতে হবে; অনুমোদিত হলে allocator বদলাতে হবে।

**করণীয়:** `order_inventory_allocations(order_id, inventory_item_id, allocated_units, ...)` relation, quantity/unit-price snapshot এবং স্পষ্ট seat policy। পুরোনো allocation backfill সবক্ষেত্রে নিখুঁতভাবে recover করা যাবে—এমন নিশ্চয়তা নেই।

### F05 — P2: Binance payment amount ও rate-এর unit উল্টো ব্যবহার হচ্ছে

**Source:** `app/services/binance.py:303–305`, `:439–449`; `app/services/deposits.py:214`।

Binance claim USDT × BDT-per-USDT করে wallet amount বানায়। Generic quote আবার wallet amount × ওই rate করে `pay_amount` রাখে। Probe: ২ USDT × ১২৫ = ২৫০ BDT credit, কিন্তু persisted quote-এর `pay_amount = 31,250`; সঠিক paid amount ২ USDT। `_credit()` amount ও transaction ID ঠিক করলেও `pay_amount` ঠিক করে না। Wallet credit-এর এই উদাহরণে calculation সঠিক; ভুল হচ্ছে paid-amount record ও তার downstream presentation।

**করণীয়:** `paid_amount`, `paid_currency`, `wallet_amount`, `conversion_rate`-এর একমুখী সংজ্ঞা। Minimum-এর USDT বনাম BDT unit-ও service/UI-তে একই করা।

### F06 — P2: নতুন deposit error flow নিজেই crash করে

**Source:** `app/bot/handlers/deposit.py:725`, `:801`, `:987`; `app/services/settings.py:107`।

তিনটি branch `settings.get('support_contact')` ডাকে, কিন্তু declared key `support_username`। `SettingsService.get()` missing key-তে `KeyError` দেয়; probe-এ নিশ্চিত। Cooldown/duplicate-payment/error fallback-এ ব্যবহারকারী প্রত্যাশিত guidance পাবেন না।

অতিরিক্তভাবে purchases/deposits-এর admin-notification fallback `settings.get('webapp_url')` ডাকে; এটিও settings key নয়, environment config field। `WEBHOOK_BASE_URL` না থাকলে ওই notification path ব্যর্থ হবে।

### F07 — P2: Binance worker পুরোনো pending deposit অনির্দিষ্টকাল বাদ দিতে পারে

**Source:** `app/services/binance.py:252`, `:282`।

Newest-first ৫০টি নিয়ে প্রথম ২০টিই check করা হয়। ২০টি সাম্প্রতিক unresolved claim থাকলে তার আগের valid pending claim পরের pass-এও বাদ পড়ে; checked timestamp/rotation নেই। একাধিক worker একই candidate আবার check করবে। **করণীয়:** due-time ভিত্তিক fair scheduling, per-claim lease এবং bounded batch; provider history প্রতি deposit-এর বদলে যতটা সম্ভব প্রতি pass-এ reuse।

### F08 — P2: Binance UID matching payment ownership-এর শক্ত প্রমাণ নয়

**Source:** `app/services/binance.py`, `_match_pay()`।

User-submitted reference sender UID/counterparty ID/order ID/transaction ID-এর যেকোনোটির সঙ্গে মিললেই latest uncredited incoming payment গ্রহণ করে। Telegram account-এর সঙ্গে sender identity বা unique payment intent-এর binding নেই। স্থায়ী UID জানা অন্য account legitimate sender-এর unclaimed payment দাবি করতে পারে। এটি code-level design risk; কোনো live exploitation করা হয়নি। **করণীয়:** customer-bound payment intent বা trusted sender binding; ambiguous UID-only claim-এ manual review।

### F09 — P2: Duplicate data ঠেকানোর কিছু নিয়ম শুধু application-এ আছে

**Source:** `app/services/inventory.py:60–76`; `app/services/deposits.py:127–174`; `app/services/supplier.py:274–349`।

- Stock upload প্রথমে SELECT, পরে INSERT; একই product/content-এর concurrent upload দুটিই absent দেখতে পারে। Database uniqueness বা product-level serialization নেই।
- Binance get-or-create absent row-তে `FOR UPDATE` দিয়ে ভবিষ্যৎ row lock করা যায় না; concurrent first creation-এ duplicate method হতে পারে। Broad `name LIKE '%binance%'` matching পুরোনো on-chain/custom method-কে Pay method-এ পরিবর্তনও করতে পারে।
- Supplier sync retained হলে `supplier_product_id` uniqueness/upsert প্রয়োজন; concurrent sync duplicate product তৈরি করতে পারে।

বর্তমান inspected database-এ এ ধরনের duplicate stock/method পাওয়া যায়নি। **করণীয়:** domain identity স্থির করে constraints/upsert/transaction lock; stock content বড় text হতে পারে, তাই অন্ধভাবে wide-text unique B-tree যোগ না করে key/hash collision policy বিবেচনা করা।

### F10 — P2: Telegram webhook durable acceptance-এর আগে 200 দেয়

**Source:** `app/api/telegram.py:74–88`।

Update কেবল `asyncio.create_task()` ও in-memory set-এ রেখে 200 দেওয়া হয়। Process restart/crash-এর আগে unfinished update durable কোথাও নেই। Background tasks-এর global concurrency bound-ও নেই। **করণীয়:** durable inbox/job queue, unique update ID, processing lease ও bounded consumers; অথবা bounded synchronous processing-এর উপযোগী design। Existing purchase request uniqueness রাখা জরুরি।

### F11 — P2: Broadcast retention pending delivery-ও মুছে দেয়

**Source:** `app/services/delivery.py:123–130`; migration `0016_broadcast_text_and_retention.sql`।

Latest ৩০টির বাইরের broadcast সরাসরি delete হয়; FK cascade তার pending/sending outbox-ও মুছে দেয়। পুরোনো broadcast পাঠানো শেষ হওয়ার আগে নতুন ৩০টি job এলে delivery চুপচাপ হারাবে। **করণীয়:** completed job-এ retention প্রয়োগ, pending/sending job রাখা, cancel-কে explicit action করা।

### F12 — P2: Removed Mini App-এর payment return URL রয়ে গেছে

**Source:** `app/services/payments.py:254`, `:335`; `app/api/app.py`; `app/services/notifications.py:25–47`; `app/core/config.py`।

Hosted checkout এখনও `/app/?payment=...`-এ ফেরায়; বর্তমান app-এ storefront route/static app নেই। Local ASGI probe-এ URL 404 হয়েছে। Payment webhook/worker থাকায় এই 404 নিজে credit বন্ধ হওয়ার প্রমাণ নয়, কিন্তু customer return journey ভাঙা। `WEBAPP_URL` দিলে bot menu-তেও পুরোনো app link তৈরি হতে পারে; inspected local config-এ এটি unset। **করণীয়:** কার্যকর payment-result page বা bot deep link এবং obsolete Mini App configuration cleanup।

### F13 — P2: Invoice creation-এর interrupted state reconcile হয় না

**Source:** `app/services/payments.py:323–372`, `:391`, `:417`।

Local `created` invoice insert এবং external create request-এর পরে `pending` update আলাদা ধাপ। মাঝখানে crash হলে row `created` অবস্থায় থাকে; refresh এবং worker শুধু pending নিয়ে কাজ করে। Current DB-তে stuck row ০। **করণীয়:** stale-created recovery, provider reference দিয়ে reconciliation এবং explicit creation timeout state।

### F14 — P2, historical-data dependent: Balance constraint পুরোনো refund policy-র বিরোধী

**Source:** `app/db/migrations/0020_performance_indexes.sql:23`; `app/services/purchases.py:314–320`।

Refund code পুরোনো referral bonus ফেরত নেয়, referrer আগে টাকা খরচ করলে negative balance/debt রাখতে চায়। নতুন `CHECK(balance >= 0)` সেটি reject করে পুরো refund rollback করবে। আগের database-এ negative balance থাকলে migration deploy-ও fail করবে। Inspected DB-তে legacy referral-bonus order এবং negative balance দুটোই ০—তাই এখন active incident নয়। **করণীয়:** debt/recovery policy স্থির করে আলাদা record বা supported accounting treatment; ইতিহাস না দেখে refund branch/columns drop নয়।

### F15 — P2: Dashboard expired stock-কে available দেখায়

**Source:** `app/services/dashboard.py:16` বনাম `app/services/catalog.py:19`।

Dashboard available-stock total-এ expiry filter নেই, catalogue/allocator-এ আছে। Database-এ এমন expired available row ১টি আছে। **করণীয়:** একই reusable availability predicate দিয়ে metrics ও purchase path চালানো। Expired row physically delete করার প্রয়োজন নেই।

### F16 — P2/P3: Exact duplicate index এবং migration maintenance সমস্যা

**Source:** `0008_fulfillment_and_shared_stock.sql:13`, `0020_performance_indexes.sql:13`, `app/db/migrations.py`।

`orders_inventory_item` ও `idx_orders_inventory_user` একই definition-এর আলাদা index; live metadata-তেও নিশ্চিত। নাম আলাদা হওয়ায় `IF NOT EXISTS` এটি ঠেকায় না। Storage ও insert/update maintenance বাড়ে; current data size-এ খরচ ছোট। **করণীয়:** নতুন forward migration দিয়ে একটি redundant index বাদ দেওয়া।

Runner-এ applied-file checksum নেই; applied SQL edit করলে database drift শনাক্ত হবে না। `0011` ও `0021`-এ constraint-existence test শুধু `conname` দেখে, target table/schema দেখে না—একই database-এ isolated test schema বানালে প্রয়োজনীয় constraint skip হতে পারে। সব pending migration এক transaction-এ চলে; বড় table-এ blocking index/constraint build-এর deployment পরিকল্পনা প্রয়োজন।

## সরানো বনাম লুকানো: কোন অংশ কী অবস্থায়

| অংশ | যা পাওয়া গেছে | Cleanup সিদ্ধান্ত |
|---|---|---|
| Banner/media | `e89c095`, `9e12d8a`, `a7bbb68` UI/routes/sending সরিয়েছে; `app/services/media.py`, empty `app/api/media.py`, `Services.media=None`, `notice_banner`, তিনটি table রয়ে গেছে | বর্তমান code-এ service unwired এবং তিনটি table খালি। Unused code/settings বাদ দেওয়ার উপযুক্ত candidate; target deployment/backup যাচাই করে নতুন migration-এ tables drop |
| Supplier | Console control নেই, কিন্তু authenticated `/api/admin/supplier/*`, service construction, settings/env, sync, stock formula সক্রিয়; purchase path supplier fulfillment করে না | শুধু hidden নয়, অসম্পূর্ণ integration। Supplier stock দেখিয়ে local stock না থাকলে purchase ব্যর্থ হতে পারে। Feature বাদ দেওয়ার সিদ্ধান্ত হলে route→service→catalog formula→config→schema dependency order-এ remove |
| Supplier history | Order detail সবসময় `supplier_attempts: []` ফেরায়; table query করে না | পুরোনো attempts থাকলে history আড়াল হবে। Inspected table খালি, অন্য deployment/backup ধরে নেব না |
| BDT-only | `3bbebc4` currency inputs সরিয়েছে; backend `currency`, `currency_symbol`, `zinipay_rate` এখনও configurable | UI removal BDT-only invariant enforce করেনি। Current DB-তে explicit currency override নেই, rate 1। আগে persisted values audit/normalize, পরে server-side invariant এবং UI alignment |
| পুরোনো referral percent | setting ও purchase-এর unused read আছে; নতুন flat referral system সক্রিয় | Unused percentage read/setting cleanup করা যায়; historical refund fields আলাদাভাবে migrate করতে হবে |
| Emoji sources | `bot_settings.custom_emojis` default JSON আছে; বর্তমান API/picker custom table ও system presets ব্যবহার করে | এই নামের দুটি table নয়। পুরোনো JSON setting unused হলে remove; intentional built-in presets রাখা যায় |
| Product deletion | `delete_product()` orders-এর FK null করে inventory ও product সত্যিই delete করে | এটি শুধু hide নয়। Historical credential/title/price snapshots আছে; product identity link হারানোর tradeoff আছে |
| Partially used stock removal | `remove_available()` ব্যবহৃত item-কে sold করে; unused item delete করে | এটি যুক্তিসংগত retirement: পুরোনো order/seat history বাঁচায়। সব ক্ষেত্রে permanent delete চাপানো ঠিক হবে না |
| Payment-method deletion | System Binance Pay method delete নিষিদ্ধ; অন্য method delete-এর আগে deposits link null করা হয় | Historical name থাকে; pending auto-verified method বাদ দিলে checker dependency হারাতে পারে। Active pending claims থাকা অবস্থায় retire/block policy প্রয়োজন |

Supplier routes public নয়—local probe-এ unauthenticated request 401 হয়েছে। Cleanup finding-কে authentication bypass হিসেবে পড়া উচিত নয়।

## Scale ও schema design-এর বাকি গুরুত্বপূর্ণ বিষয়

1. **Wallet ledger নেই।** Balance, total_spent, deposits, orders, referral_rewards এবং free-text audit log আলাদাভাবে থাকে। Financial reconciliation-এর জন্য typed immutable wallet entries, operation idempotency key, amount/currency এবং balance-change linkage দরকার। `users.balance` transactionally maintained projection হিসেবে থাকতে পারে। এটি এখন balance corrupt হয়েছে এমন প্রমাণ নয়।
2. **NUMERIC থেকে float।** `app/db/database.py:47` exact database NUMERIC-কে float বানায়; application `round()` ব্যবহার করে। বড় scale/financial reconciliation-এর আগে Decimal বা smallest-unit integer policy এক করা উচিত। কোনো rounding-related live loss মাপা হয়নি।
3. **Relational integrity gaps।** Orders/deposits/invoices-এ internal user ID ও Telegram ID independently stored; schema একই user হওয়া enforce করে না। `referral_rewards`-এর দুই user reference, `users.referred_by`, `outbox.about_order_id`-এ FK নেই। Snapshot fields ইচ্ছাকৃত হতে পারে; lifecycle policy অনুযায়ী constraints যোগ করতে হবে। বর্তমান orders/deposits mismatch ০।
4. **Process-local state।** Local config-এ Redis নেই; FSM `MemoryStorage` fallback। RedisStorage option থাকলেও Throttle, verification failure counter এবং caches process-local-ই থাকবে। Replicas-এ shared rate limit/cooldown, FSM event isolation ও cache invalidation দরকার। `_USER_VERIFY_FAILS` inactive users-এর entries globally expire করে না।
5. **Pool exhaustion।** Local pool override ১০, code default ২৫, প্রতি process-এ আলাদা pool। শুধু pool size বাড়ানো throughput guarantee নয়। কিছু transaction-এর ভেতরে settings lookup অন্য connection নিতে পারে; cold-cache concurrent traffic-এ nested acquisition এড়ানো দরকার। Pool acquire/query timeout নেই। মোট connection budget, query latency ও transaction duration মাপতে হবে।
6. **Growing queries।** Dashboard ও list summaries বারবার COUNT/SUM করে; OFFSET pagination ও `%term%` search বড় table-এ ব্যয় বাড়াবে। Chart-এর `DATE(created_at)` predicate সাধারণ created_at index-এর range lookup ব্যবহারকে বাধা দেয়। Production-size staging data-এ EXPLAIN/measurement করে date range, keyset pagination, selected search indexes, precomputed summaries ঠিক করা উচিত।
7. **Outbox scale।** প্রতি broadcast-এ প্রতিটি user-এর জন্য full text copy হয়; latest ৩০ রাখলেও storage user count-এর সঙ্গে বাড়ে। Claim query priority CASE দিয়ে sort করে; waiting-order notice-এর `about_order_id` priority একইভাবে বাড়ানো হয়নি। Shared payload + recipient state, targeted due-job indexes এবং notification priority যাচাই প্রয়োজন।
8. **Unbounded growth/retention।** Orders, deposits ও audit logs-এর intentional archival policy নেই। Financial history না মুছে partition/archive/backup policy দরকার; sent outbox retention-এ idempotency/recovery logic বাঁচাতে হবে।
9. **Deployment reproducibility।** Console lockfile নেই এবং Dockerfile `npm install` করে; কিছু dependency range floating। Python dependencies pinned। Frontend lockfile ও deterministic install প্রয়োজন। Repository-তে disaster-recovery drill বা load-test evidence নেই; backup বাস্তবে configured নয়—এমন সিদ্ধান্ত নেওয়া হয়নি।

বর্তমান dataset মাত্র কয়েকটি user/order-এর। এর latency বা successful typecheck থেকে ১০ হাজার/১ লাখ user সামলানোর capacity ঘোষণা করা যাবে না। PostgreSQL/service separation রেখে প্রয়োজনীয় সংশোধন করা সম্ভব; এখনই microservices/sharding দরকার—এমন প্রমাণ নেই।

## Verification evidence

| পরীক্ষা | ফল |
|---|---|
| Python AST parse | ৭৪ file pass |
| `npm run typecheck` | pass |
| ZiniPay disabled + stored key | `is_enabled=True`, bug reproduced |
| ZiniPay local insertion failure | external confirm আগে call হয়েছে, ordering gap reproduced |
| ZiniPay approve false | result `credited=True`, bug reproduced |
| Binance ২ USDT / rate ১২৫ quote | credit ২৫০, `pay_amount=31250`, unit mismatch reproduced |
| ৭ free seats in one item / buy ২ | `claim_seats=None`, policy mismatch reproduced |
| `support_contact` lookup | `KeyError`, reproduced |
| Local `/app/?payment=example` | 404 |
| Local unauthenticated supplier status | 401 |

এই mock probes শুধু সংশ্লিষ্ট branch/ordering পরীক্ষা করে; network/provider contract বা বাস্তব database concurrency প্রমাণ করে না। কোনো real transaction consume করা হয়নি।

## কাজের নিরাপদ ক্রম

1. Payment consume/recovery ordering, false-success result, disabled flag ও broken error setting ঠিক করা; Binance unit এবং ownership policy ঠিক করা।
2. Multi-item allocation schema ও quantity policy, duplicate-write constraints, fair pending-payment scheduling এবং durable webhook acceptance করা।
3. নতুন forward migration-এ redundant index ও confirmed obsolete banner tables/settings সরানো। Applied migration history rewrite/rename নয়। Supplier removal পুরো dependency chain ধরে করা; historical financial/order data blanket-delete নয়।
4. Ledger/reconciliation, shared state, connection budget, retention এবং reproducible build নিয়ে staging-এ concurrent purchase/deposit/refund/restart tests চালানো। এরপর representative load measurement করে capacity নির্ধারণ।
