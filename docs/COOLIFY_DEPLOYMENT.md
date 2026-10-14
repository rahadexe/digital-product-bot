# Coolify production deployment

The audited webhook/force-join patch has been applied to the working source. Do not apply the archived patch again. Deployment itself has not been executed. Commit/push all required application files, migrations, dependency lockfiles and Dockerfile changes to the branch Coolify builds; uncommitted local files are not deployed from Git.

## Application settings

| Setting | Value |
| --- | --- |
| Source | This Git repository and the intended release branch |
| Build pack / strategy | Dockerfile |
| Base directory | `/` (repository root) |
| Dockerfile location | `/Dockerfile` |
| Build stage / target | Empty; use the final Python stage |
| Custom install/build/start commands | Empty; Dockerfile handles them |
| Ports Exposes | `8000` |
| Port Mappings / host published port | Empty |
| Domain | HTTPS, e.g. `bot.example.com` |
| Domain internal/target port | `8000` |
| Replicas | `1` initially |
| HTTP Basic Authentication | Disabled; otherwise Telegram and payment callbacks are blocked |
| Persistent app storage | None required; PostgreSQL holds persistent data |

In newer Coolify versions use Domains → Add domain, HTTPS, your hostname, internal port 8000. Older versions may present one Domains field; use the HTTPS origin and the single exposed port 8000. Visitors use `https://bot.example.com`, not public port 8000. Do not put `:8000` or `/telegram/webhook` in WEBHOOK_BASE_URL.

The Dockerfile builds the static admin console and runs bot/API/workers together using `python -m app all --no-reload`. No separate Node server, port 3000, worker application or custom startup command is required for this initial setup.

## DNS and networking

Point the hostname's DNS A record at the VPS address. Use an AAAA record only if IPv6 is actually configured. Let Coolify's proxy issue HTTPS certificates and redirect HTTP to HTTPS. Public web traffic needs ports 80/443; the application container's 8000 and PostgreSQL's 5432 do not need public host mappings. Keep existing SSH/Coolify administrative access intact.

The application must have outbound access to Telegram, payment/supplier APIs and its PostgreSQL server. Do not place a browser challenge, access-login page or HTTP Basic Auth in front of webhook/payment callback paths.

## Environment Variables

Copy `docs/coolify.env.example` into the application's **production Environment Variables** and replace the placeholders. Runtime: enabled. Build time: disabled for these backend values. The frontend uses same-origin APIs and does not need any Telegram/payment secrets or NEXT_PUBLIC variables.

Use Literal interpolation for passwords containing `$`, or use generated hex secrets. Saving the bulk Developer view replaces the listed set of variables, so preserve any existing required values.

Required values:

- `DATABASE_URL`: the existing store's PostgreSQL connection URL to retain its users, balances, stock and settings. A new empty database creates an empty store. For a Coolify PostgreSQL resource use its internal hostname/connection URL and the same network, not `localhost`. Keep the database volume/backups persistent. For hosted PostgreSQL use the provider's URL/TLS parameters, typically `sslmode=require`.
- `BOT_TOKEN`: the BotFather token for this bot.
- `WEBHOOK_BASE_URL`: the public HTTPS origin, e.g. `https://bot.example.com`.
- `ADMIN_PASSWORD`: a strong console password, at least 12 characters.
- `SECRET_KEY`: preserve the current persistent key when reusing the store database; encrypted stored credentials and sessions depend on it. For a genuinely new store generate once with `python -c "import secrets; print(secrets.token_hex(32))"` and save it. Do not regenerate it on every deploy.

Set `ADMIN_TG_ID` to your numeric Telegram user ID if needed for initial bootstrap. Saved administrator IDs in the admin console take precedence. Add the correct IDs under Settings → Store after login.

`AUTO_MIGRATE=true` makes startup apply pending migrations, including those already in this working tree. The health-check grace period is 120 seconds. Back up the existing database before first deployment. If your operational policy requires a separate migration step, run `python -m app migrate` with the release image/environment and use `AUTO_MIGRATE=false` afterward; do not leave migrations unapplied.

Leave `DB_STATEMENT_CACHE_SIZE=100` for direct PostgreSQL or a compatible pooler. Use `0` if your provider's transaction pooler does not support prepared statements. Start with `DB_POOL_SIZE=10`; the supplier-attempt journal can use two additional connections per process.

`TRUSTED_PROXY_IPS` must cover the actual Coolify proxy IP/subnet. The template includes the usual Docker 172.16.0.0/12 range; replace it with the exact network where possible and include a different custom subnet if your setup uses one. Do not use `*`.

Optional variables can be omitted: `WEBHOOK_SECRET` derives from SECRET_KEY, ALLOWED_HOSTS/ALLOWED_ORIGINS derive from the webhook origin, secure cookies are automatic in production, and Redis is unnecessary for this single-instance setup. If an existing deployment explicitly sets WEBHOOK_SECRET, preserve that value. Do not set a stale WEBAPP_URL.

## Cutover and verification

1. Save the ENV and domain settings; build/deploy the actual release branch.
2. Coordinate the first start with stopping the old local polling instance. Do not run the old poller and production webhook bot simultaneously. A restarted old poller can delete the production webhook. The code preserves pending Telegram updates.
3. The production process automatically registers `https://YOUR_DOMAIN/telegram/webhook`; no manual setWebhook command is needed.
4. Health check: HTTP, port `8000`, path `/health/ready`, expected `200`, interval 30 seconds, timeout 5 seconds, initial grace 120 seconds, retries 3. The Dockerfile already provides this; if Coolify overrides health settings, match them. Public `/health/ready` should report `ready`, `database: true`, `bot: webhook`.
5. Open the HTTPS domain to log into the console. Set administrator IDs, supplier credentials and payment gateways there. Revoke/replace the supplier key identified in the earlier production audit if that has not already been done.
6. Add active force-join channels with valid chat IDs/usernames and invite links; make the bot an administrator. The last audit found force-join enabled but zero active channels. Check join, Verify, leave and retry behavior with a non-admin account.
7. Verify a controlled real deposit/purchase and review webhook errors before unattended sales. Provider behavior, DNS/TLS and backups cannot be certified by local code tests alone.

Use one webhook replica initially. Membership and throttling caches are process-local; immediate membership invalidation across multiple replicas still requires shared invalidation. The durable queue and PostgreSQL conversation state already persist across restarts.

## References

- https://coolify.io/docs/applications/configuration/general
- https://coolify.io/docs/applications/configuration/environment-variables
- https://coolify.io/docs/applications/how-applications-work

Earlier detailed test evidence remains in `release-prep/webhook-readiness-2026-10-14/VALIDATION.md`. Its patch-only status is historical: the patch has now been applied to the main working source at the user's request.
