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
ADMIN_TG_ID=your_telegram_id_here

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

---

## 3. Reverse Proxy (Nginx or Caddy)

### Option A: Nginx

Create `/etc/nginx/sites-available/customer-bot`:

```nginx
server {
    server_name yourdomain.com;

    client_max_body_size 10M;

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

## 5. Verification

Check the health status endpoint:

```bash
curl https://yourdomain.com/health/ready
```

Expected response:
```json
{"status": "ready", "database": true, "bot": "webhook"}
```
