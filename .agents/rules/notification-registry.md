# Agent Rule: Telegram Bot Notification Architecture & Registry

Whenever modifying or adding notifications to this bot codebase, follow the rules defined in `../NOTIFICATION_REGISTRY.md`:

1. **Never send silent/hidden notifications:** Every background alert must be listed in `console/src/components/AdminNotifications.tsx`.
2. **Critical/Fulfillment alerts are ALWAYS ON:** They must be hardcoded active and displayed with an `[ALWAYS ON]` badge and locked switch.
3. **Optional alerts must have settings keys:** Add them to `app/services/settings.py` `SPECS` and `AdminNotifications.tsx`.
4. **Update `.agents/NOTIFICATION_REGISTRY.md`:** Any time a new notification is introduced, register it in the inventory table.
