# Telegram Bot Notification Registry & Architecture Standard

> **MANDATORY SYSTEM RULE FOR ALL AGENTS AND DEVELOPERS**
> Every single notification in this system—whether sent to the Admin, Customer, or a Telegram Channel—**MUST be registered and visible in the Admin Console** (`Settings > Notifications`).
> 
> **Core Principles:**
> 1. **Zero Hidden Notifications:** No message may be sent by the bot or backend in the background without being represented in `Settings > Notifications`.
> 2. **Mandatory Alerts (`ALWAYS ON`):** If a notification is essential to business operations (such as manual order alerts, gateway payment failures, or customer product delivery receipts), it **MUST NOT** be turn-offable. It must remain hardcoded active, and displayed in the Admin Console with an `[ALWAYS ON]` badge and a disabled (locked-on) switch so the admin has 100% visibility.
> 3. **Configurable Alerts:** Any notification that can be muted to reduce noise must have a corresponding setting key in `app/services/settings.py` and a toggle in `console/src/components/AdminNotifications.tsx`.
> 4. **Future Extensions:** Whenever adding a new notification feature to this project, **YOU MUST IMMEDIATELY UPDATE:**
>    - `app/services/settings.py` (add `SettingSpec` if togglable)
>    - `app/services/notifications.py` (or caller service)
>    - `console/src/components/AdminNotifications.tsx` (render row in the appropriate section)
>    - This file (`.agents/NOTIFICATION_REGISTRY.md`)

---

## Complete Notification Inventory

### 1. 🔔 Admin Operational Alerts (Dispatched to configured Admin Telegram IDs)

| # | Alert Name | Setting Key / Trigger | Mode | Description |
|---|---|---|---|---|
| 1 | **Manual Delivery Orders** | `purchases.py` (`event="waiting_order"`) | **ALWAYS ON** (Locked) | Triggered when a customer buys a manual product. Admin must fulfill credentials manually. |
| 2 | **Payment & Gateway Errors** | `payments.py` (`event="payment_error"`) | **ALWAYS ON** (Locked) | Triggered when Binance Pay, ZiniPay, or auto-verification API fails or times out. |
| 3 | **Instant Stock Purchases** | `notify_admin_orders` (`event="order"`) | Configurable (Default: 1) | Triggered when an order is automatically delivered from inventory stock. |
| 4 | **Manual Deposit Requests** | `notify_admin_deposits` (`event="deposit"`) | Configurable (Default: 1) | Triggered when a customer submits bKash/Nagad/Rocket TrxID for manual review. |
| 5 | **Automatic Gateway Deposits** | `notify_admin_payments` (`event="payment"`) | Configurable (Default: 1) | Triggered when automated deposit via Binance Pay or ZiniPay is confirmed. |
| 6 | **Stock Updates & Alerts** | `notify_admin_restock` (`event="restock"`) | Configurable (Default: 1) | Triggered when inventory items are added, or when stock reaches 0 (Out of Stock). |
| 7 | **Price Change Alerts** | `notify_admin_price_change` (`event="price_change"`) | Configurable (Default: 1) | Triggered when product prices or discounts are updated in the catalog. |
| 8 | **New Customer Joined** | `notify_admin_new_user` (`event="new_user"`) | Configurable (Default: 0) | Triggered when a new Telegram user starts the bot and creates an account. |
| 9 | **Security: Group Invites Blocked** | `admin.py` (`on_bot_chat_member_updated`) | **REQUIRED (ALWAYS ON)** | Dispatched when bot is added to any group. Bot auto-leaves without responding. |
| 10 | **Security: Unauthorized Channels Blocked** | `admin.py` (`on_bot_chat_member_updated`) | **REQUIRED (ALWAYS ON)** | Dispatched when bot is added to an unconfigured channel. Bot auto-leaves immediately. |

> **Security Standard: Group & Channel Isolation:**
> 1. **Zero Group Participation:** The bot is strictly prohibited from participating in any Telegram group or supergroup. If added to any group, the bot immediately leaves (`bot.leave_chat`), sends zero messages, and dispatches a security alert to the shop admins.
> 2. **Message Gate (`StoreAccess`):** The bot rejects all customer and admin commands (`/start`, `/buy`, wallet balance, credentials) in non-private chats (`chat.type != "private"`).
> 3. **Unauthorized Channel Protection:** If the bot is added to an unauthorized channel, it automatically leaves immediately to prevent misuse and alerts shop admins.
> 4. **Channel Whitelist:** Only public channels explicitly configured in `announcement_channel` or gate channels are authorized. Channels ONLY receive public marketing announcements (Restock & Price Drop). Zero customer or order data is ever sent to channels.

---

### 2. 👥 Customer Notifications (Sent directly to the user in the Telegram Bot)

| # | Notification Name | Handler / Service | Mode | Description |
|---|---|---|---|---|
| 1 | **Order Delivery & Credentials** | `delivery.py` (`enqueue_order`) / Durable Outbox | **ALWAYS ON** (Locked) | Delivers purchased account logins, license keys, or credentials immediately. |
| 2 | **Manual Order Acknowledgment** | `delivery.py` (`enqueue_waiting_notice`) / Outbox | **ALWAYS ON** (Locked) | Acknowledges receipt of payment for manual products; explains admin will deliver shortly. |
| 3 | **Deposit Approved & Balance Added** | `deposits.py` (`_notify_customer`) | **ALWAYS ON** (Locked) | Receipt and new balance sent when deposit request is approved manually or via gateway. |
| 4 | **Deposit Rejected Notification** | `deposits.py` (`_notify_customer`) | **ALWAYS ON** (Locked) | Notice with admin explanation sent if a fake or invalid TrxID deposit is rejected. |
| 5 | **Manual Balance Adjustments** | `users.py` (`_notify_adjustment`) | **ALWAYS ON** (Locked) | Receipt sent when an admin adjusts customer balance directly from the Customers tab. |
| 6 | **Order Refund Notification** | `purchases.py` (`refund`) | **ALWAYS ON** (Locked) | Instant notification and wallet refund receipt sent when an admin refunds an order. |
| 7 | **Referral Bonus Alerts** | `users.py` (`process_referral_reward`) / `notify_user_referral` | Configurable (Default: 1) | Notifies referrer when their invited friend joins and bonus is credited to wallet. |

---

### 3. 📢 Public Channel Auto-Posts (Dispatched to `announcement_channel`)

> Supports single or multiple channels separated by commas (e.g. `-1004331909607, @SecondChannel`).
> **Zero Customer Data Leakage:** ONLY public marketing announcements (Restock & Price Drop) are ever sent to announcement channels. Customer receipts, order details, and wallet data are strictly prohibited and architecturally excluded from public channels.

| # | Announcement Name | Setting Key | Mode | Description |
|---|---|---|---|---|
| 1 | **Auto-post on Restock** | `auto_restock_alerts` | Configurable (Default: 1) | Posts restock announcements with 1-click Buy button directly to all configured channels. |
| 2 | **Auto-post on Price Drop** | `auto_price_drop_alerts` | Configurable (Default: 1) | Posts discount announcements to all configured announcement channels when price drops. |

---

### 4. 🛠️ Administrative & Diagnostic Notifications

| # | Name | Trigger | Description |
|---|---|---|---|
| 1 | **Admin Notification Test** | `POST /api/admin/settings/test-admin-notification` | Sends a diagnostic test message to all registered admin Telegram IDs. |
| 2 | **Mass Broadcasts** | `delivery.py` (`enqueue_broadcast`) | Admin-composed broadcast messages sent to all active customers. |

---

## Technical Implementation Guide

### Dispatching Notifications:
- **Admin Alerts:** Use `await self.notifier.send_admin(text, event="<event_name>")`.
- **Customer Deliveries (Durable):** Use `await self.delivery.enqueue_order(...)` or `enqueue_waiting_notice(...)` to ensure persistence in Postgres `outbox` table even across restarts.
- **Customer Background Alerts:** Use `self.notifier.in_background(self.notifier.send(tg_user_id, text))` for non-blocking asynchronous notifications.
- **Channel Posts:** Use `await self.notifier.send(channel_id, text, keyboard=button)`.

### Adding a New Notification:
1. Choose whether the notification is **Mandatory** or **Configurable**.
2. If configurable:
   - Add `"notify_<name>": SettingSpec("1", _flag, 1)` to `SPECS` in `app/services/settings.py`.
   - Check `await self.settings.flag("notify_<name>")` before dispatching.
   - Add `<FlagRow label="..." hint="..." on={isOn('notify_<name>', '1')} onChange={(next) => void flip('notify_<name>', next)} />` in `console/src/components/AdminNotifications.tsx`.
3. If mandatory:
   - Dispatch without suppression.
   - Add `<div className="mandatory-row">...<span className="mandatory-badge warn">ALWAYS ON</span>...<Switch label="..." on={true} disabled={true} /></div>` in `console/src/components/AdminNotifications.tsx`.
