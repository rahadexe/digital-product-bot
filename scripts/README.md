# Operator scripts

Run from the repository root with the project's environment loaded. Each one reads `.env` through
`app.core.config`, so it acts on whichever database and bot that file points at — check it first.

```bash
python -m scripts.<name> [arguments]
```

| Script | What it does | Safe to re-run |
| --- | --- | --- |
| `seed_defaults` | Inserts the starting payment methods and sample products into an empty store. | Yes, it skips what already exists |
| `apply_emojis` | Applies the built-in custom emoji ids to categories and products by name. | Yes |
| `set_product_emojis` | Matches product titles against the emoji table and sets their ids. | Yes |
| `send_emoji_catalog` | Sends the built-in emoji catalogue to an operator so the ids can be checked visually. | Yes, it only sends messages |
| `send_all_sample_notifications` | Sends one live preview of every notification the bot can produce. | Yes, it only sends messages |

The two that send Telegram messages take the recipient as their first argument and fall back to
`ADMIN_TG_ID`. They send to a real account, so point them at your own.

One-off data migrations do not belong here. Schema and data changes ship as numbered files in
`app/db/migrations/`, which run once and are recorded with a checksum.
