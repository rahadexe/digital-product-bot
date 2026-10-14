# VPS Deployment Guide (Production Webhook Setup)

This guide walks you through deploying the SubsMarket bot to your Linux VPS (Ubuntu/Debian) for maximum speed and 24/7 reliability.

---

## 1. System Requirements & Setup

On your VPS, install Python 3.12 and required build tools:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3.12 python3.12-venv python3.12-dev git curl
```

Clone the repository and set up a virtual environment:

```bash
git clone <YOUR_REPO_URL> /opt/customer-bot
cd /opt/customer-bot

python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

Install Node.js 22 LTS and build the admin console before starting the Python service:

```bash
npm --prefix console ci
npm --prefix console run build
test -f console/out/index.html
```

The Python server serves `console/out`; deploying source without this build can serve an old UI or no console.
The Dockerfile performs this build automatically. Keep the lockfile with the release.

*(Note: On Linux, `uvicorn[standard]` automatically uses `uvloop` and `httptools` for sub-millisecond C-level event loop performance.)*

---

## 2. Production `.env` Configuration

Create `/opt/customer-bot/.env`:

```env
APP_ENV=production
HOST=127.0.0.1
PORT=8000

# Database (Neon PostgreSQL or local PostgreSQL)
DATABASE_URL=postgresql://user:password@host:5432/dbname?sslmode=require
AUTO_MIGRATE=true
DB_POOL_SIZE=10
DB_STATEMENT_CACHE_SIZE=0

# Telegram Bot Credentials
BOT_TOKEN=your_bot_token_here

# Security
ADMIN_PASSWORD=your_strong_admin_password_12+chars
SECRET_KEY=generate_with_openssl_rand_hex_32

# Domains & Hosts (replace with your real domain)
ALLOWED_HOSTS=yourdomain.com,127.0.0.1,localhost
ALLOWED_ORIGINS=https://yourdomain.com
TRUSTED_PROXY_IPS=127.0.0.1

# Telegram Webhook
WEBHOOK_BASE_URL=https://yourdomain.com
WEBHOOK_SECRET=your_32_to_256_character_secret_token
```

This file holds only what the process needs to start. Admin Telegram IDs, the ZiniPay and Binance
credentials, prices, payment methods and the rest of the store's behaviour are set in the admin
console after the first start and take effect without a redeploy. See
[.env.example](.env.example) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## 3. Reverse Proxy (Nginx or Caddy)

### Option A: Nginx

Create `/etc/nginx/sites-available/customer-bot`:

```nginx
server {
    server_name yourdomain.com;

    client_max_body_size 2M;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Enable the site and obtain SSL via Let's Encrypt:

```bash
sudo ln -s /etc/nginx/sites-available/customer-bot /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d yourdomain.com
```

### Option B: Caddy (Automatic SSL)

Add to `/etc/caddy/Caddyfile`:

```caddy
yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
```

Then reload Caddy:

```bash
sudo systemctl reload caddy
```

---

## 4. Systemd Service (Auto-restart & 24/7 Uptime)

Create `/etc/systemd/system/customer-bot.service`:

```ini
[Unit]
Description=SubsMarket Telegram Bot & Web API
After=network.target

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/customer-bot
ExecStart=/opt/customer-bot/.venv/bin/python -m app all
Restart=always
RestartSec=5s
EnvironmentFile=/opt/customer-bot/.env

[Install]
WantedBy=multi-user.target
```

Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable customer-bot
sudo systemctl start customer-bot
```

To view live logs:

```bash
sudo journalctl -u customer-bot -f
```

---

## 5. Coolify Deployment (1-Click Docker Webhook Setup)

If you are using **Coolify**:

1. **Create New Resource:**
   - In Coolify, choose **Add Resource** → **Git Repository**.
   - Select your repository and branch.
   - Build Pack: Select **Dockerfile** (or **Docker Compose**).
2. **Ports & Domain Configuration:**
   - **Domains**: Enter your public domain with HTTPS (e.g., `https://customer.bmdigital.bd`). Coolify handles automatic SSL with Let's Encrypt / Traefik.
   - **Exposed Port**: `8000`.
3. **Environment Variables:**
   - Copy the variables from [`.env.coolify`](.env.coolify) into Coolify's Environment Variables tab:
     ```env
     APP_ENV=production
     HOST=0.0.0.0
     PORT=8000
     AUTO_MIGRATE=true
     USE_POLLING=false
     TRUSTED_PROXY_IPS=127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16
     DATABASE_URL=postgresql://...
     BOT_TOKEN=your_telegram_bot_token
     ADMIN_TG_ID=your_telegram_numeric_id
     ADMIN_PASSWORD=your_strong_admin_password
     SECRET_KEY=generate_random_secret_at_least_32_chars
     WEBHOOK_BASE_URL=https://your-domain.com
     WEBHOOK_SECRET=your_random_secret_token_32_chars
     ALLOWED_HOSTS=your-domain.com
     ALLOWED_ORIGINS=https://your-domain.com
     ```
4. **Deploy:**
   - Click **Deploy**. Coolify builds the Next.js static console and Python container, runs database migrations automatically, and registers the Telegram Webhook!

---

## 6. Verification

Before enabling sales, complete the release gates in [the production audit](docs/PRODUCTION_READINESS_2026-10-14.md): rotate the exposed supplier credential, verify proxy/firewall settings, restore a backup into an isolated environment and run a controlled live payment/reconciliation smoke test. Apply migration 0046 before starting the new code. The supplier journal uses up to two additional database connections per process. Build and test the exact revision being deployed.

Check the health status endpoint:

```bash
curl https://yourdomain.com/health/ready
```

Expected response:
```json
{"status": "ready", "database": true, "bot": "webhook"}
```
