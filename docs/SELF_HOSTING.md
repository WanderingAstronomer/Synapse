# Self-Hosting Deployment Guide

**Target Environment:** Home network with MikroTik router + DDNS  
**Expected Scale:** 1 Discord server, <500 users, <1000 messages/day  
**Monthly Cost:** ~$2-5 electricity (vs. $50+ Azure managed services)

---

## Network Topology

```
                    Internet
                       ↓
          ┌────────────────────────┐
          │   MikroTik Router      │
          │   DDNS: synapse.ddns   │
          │   NAT: 80→Host:80      │
          │        443→Host:443    │
          └────────────────────────┘
                       ↓
              192.168.x.0/24 LAN
                       ↓
          ┌────────────────────────┐
          │   Docker Host          │
          │   IP: 192.168.x.10     │  (example)
          │                        │
          │   ┌────────────────┐   │
          │   │ Nginx Proxy    │   │  :80, :443 (external)
          │   │ + Let's Encrypt│   │
          │   └────────────────┘   │
          │          ↓              │
          │   ┌──────────────────┐ │
          │   │  FastAPI (8000)  │ │
          │   │  SvelteKit (3000)│ │
          │   │  Postgres (5432) │ │
          │   │  Discord Bot     │ │
          │   └──────────────────┘ │
          └────────────────────────┘
```

---

## MikroTik Router Configuration

### 1. DDNS Setup

If not already configured, set up dynamic DNS (example uses Cloudflare):

```routeros
# MikroTik RouterOS CLI
/ip cloud
set ddns-enabled=yes update-time=yes

# Or use external DDNS provider (Cloudflare, DuckDNS, No-IP)
/system script
add name=ddns-update source={
  :local ip [/ip address get [find interface=ether1] address];
  :local ip [:pick $ip 0 [:find $ip "/"]];
  /tool fetch mode=https url="https://api.cloudflare.com/..." keep-result=no;
}

/system scheduler
add name=ddns-scheduler interval=5m on-event=ddns-update
```

**Result:** Your public IP resolves to `synapse.yourdomain.com` (or `your-name.ddns.net`)

---

### 2. Port Forwarding (NAT)

Forward HTTP/HTTPS traffic to your Docker host:

```routeros
# Get your Docker host's local IP first
# Example: 192.168.88.10

/ip firewall nat

# HTTP (for Let's Encrypt ACME challenge)
add chain=dstnat action=dst-nat \
    protocol=tcp dst-port=80 \
    to-addresses=192.168.88.10 to-ports=80 \
    comment="Synapse HTTP"

# HTTPS (encrypted traffic)
add chain=dstnat action=dst-nat \
    protocol=tcp dst-port=443 \
    to-addresses=192.168.88.10 to-ports=443 \
    comment="Synapse HTTPS"
```

**Verification:**
```routeros
/ip firewall nat print
```

---

### 3. Firewall Rules (Security)

**Option A: Minimal (Allow all established + new HTTP/HTTPS)**
```routeros
# Allow established/related
/ip firewall filter
add chain=input connection-state=established,related action=accept \
    comment="Allow established"

# Allow ICMP (ping)
add chain=input protocol=icmp action=accept \
    comment="Allow ping"

# Allow SSH from LAN only (CRITICAL)
add chain=input src-address=192.168.88.0/24 protocol=tcp dst-port=22 \
    action=accept comment="SSH from LAN only"

# Allow HTTP/HTTPS from anywhere (forwarded to Docker host)
add chain=input protocol=tcp dst-port=80,443 action=accept \
    comment="Allow HTTP/HTTPS"

# Drop everything else (external)
add chain=input in-interface=ether1 action=drop \
    comment="Drop external"
```

**Option B: Whitelist-Only (Recommended for paranoia)**
```routeros
# Same as above, but restrict HTTP/HTTPS to specific countries or IPs
# Use /ip firewall address-list for allowed IPs

/ip firewall address-list
add list=allowed-countries address=1.2.3.0/24 comment="Your ISP range"

/ip firewall filter
add chain=input protocol=tcp dst-port=80,443 \
    src-address-list=allowed-countries action=accept
add chain=input protocol=tcp dst-port=80,443 action=drop \
    comment="Block non-whitelisted HTTP/HTTPS"
```

---

### 4. Static DHCP Lease (Docker Host)

Ensure your Docker host always gets the same IP:

```routeros
/ip dhcp-server lease
add address=192.168.88.10 mac-address=AA:BB:CC:DD:EE:FF \
    comment="Synapse Docker Host" server=defconf
```

(Replace `AA:BB:CC:DD:EE:FF` with your actual host's MAC address)

---

## Docker Compose Updates

### Updated `docker-compose.yml`

Replace your existing `docker-compose.yml` with this production-ready version:

```yaml
version: '3.8'

services:
  # --- Reverse Proxy (SSL Termination) ---
  nginx:
    image: nginx:alpine
    container_name: synapse-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./certs:/etc/letsencrypt:ro
      - ./certbot-webroot:/var/www/certbot:ro
    depends_on:
      - api
      - dashboard
    restart: unless-stopped
    networks:
      - synapse-network

  # --- SSL Certificate Management ---
  certbot:
    image: certbot/certbot:latest
    container_name: synapse-certbot
    volumes:
      - ./certs:/etc/letsencrypt
      - ./certbot-webroot:/var/www/certbot
    entrypoint: "/bin/sh -c 'trap exit TERM; while :; do certbot renew --webroot -w /var/www/certbot; sleep 12h & wait $${!}; done;'"
    restart: unless-stopped
    networks:
      - synapse-network

  # --- Database ---
  db:
    image: postgres:16-alpine
    container_name: synapse-db
    environment:
      POSTGRES_DB: synapse
      POSTGRES_USER: synapse
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U synapse"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - synapse-network

  # --- Automated Backups ---
  backup:
    image: prodrigestivill/postgres-backup-local:latest
    container_name: synapse-backup
    environment:
      POSTGRES_HOST: db
      POSTGRES_DB: synapse
      POSTGRES_USER: synapse
      POSTGRES_PASSWORD: ${DB_PASSWORD}
      BACKUP_KEEP_DAYS: 7
      BACKUP_KEEP_WEEKS: 4
      BACKUP_KEEP_MONTHS: 3
      SCHEDULE: "@daily"
      HEALTHCHECK_PORT: 8080
    volumes:
      - ./backups:/backups
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - synapse-network

  # --- Discord Bot ---
  bot:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: synapse-bot
    environment:
      DATABASE_URL: postgresql://synapse:${DB_PASSWORD}@db:5432/synapse
      DISCORD_TOKEN: ${DISCORD_TOKEN}
      JWT_SECRET: ${JWT_SECRET}
    volumes:
      - ./config.yaml:/app/config.yaml:ro
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - synapse-network

  # --- FastAPI Backend ---
  api:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: synapse-api
    command: ["uvicorn", "synapse.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
    environment:
      DATABASE_URL: postgresql://synapse:${DB_PASSWORD}@db:5432/synapse
      JWT_SECRET: ${JWT_SECRET}
      DISCORD_CLIENT_ID: ${DISCORD_CLIENT_ID}
      DISCORD_CLIENT_SECRET: ${DISCORD_CLIENT_SECRET}
      OAUTH_REDIRECT_URI: https://synapse.yourdomain.com/auth/callback
    depends_on:
      db:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - synapse-network

  # --- SvelteKit Dashboard ---
  dashboard:
    build:
      context: ./dashboard
      dockerfile: Dockerfile
    container_name: synapse-dashboard
    environment:
      NODE_ENV: production
      API_BASE_URL: http://api:8000
    depends_on:
      - api
    restart: unless-stopped
    networks:
      - synapse-network

  # --- Uptime Monitoring (Optional) ---
  uptime-kuma:
    image: louislam/uptime-kuma:1
    container_name: synapse-monitoring
    ports:
      - "127.0.0.1:3001:3001"  # Only accessible from localhost
    volumes:
      - uptime-kuma-data:/app/data
    restart: unless-stopped
    networks:
      - synapse-network

volumes:
  postgres-data:
  uptime-kuma-data:

networks:
  synapse-network:
    driver: bridge
```

---

### Nginx Configuration

Create `nginx.conf` in your project root:

```nginx
events {
    worker_connections 1024;
}

http {
    # Rate limiting (prevent abuse)
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;
    limit_req_zone $binary_remote_addr zone=general_limit:10m rate=30r/s;

    # Logging
    access_log /var/log/nginx/access.log;
    error_log /var/log/nginx/error.log warn;

    # MIME types
    include /etc/nginx/mime.types;
    default_type application/octet-stream;

    # Performance
    sendfile on;
    tcp_nopush on;
    tcp_nodelay on;
    keepalive_timeout 65;
    types_hash_max_size 2048;

    # Security headers
    add_header X-Frame-Options "SAMEORIGIN" always;
    add_header X-Content-Type-Options "nosniff" always;
    add_header X-XSS-Protection "1; mode=block" always;
    add_header Referrer-Policy "no-referrer-when-downgrade" always;

    # HTTP → HTTPS redirect
    server {
        listen 80;
        server_name synapse.yourdomain.com;  # CHANGE THIS

        # ACME challenge for Let's Encrypt
        location /.well-known/acme-challenge/ {
            root /var/www/certbot;
        }

        # Redirect everything else to HTTPS
        location / {
            return 301 https://$host$request_uri;
        }
    }

    # HTTPS server
    server {
        listen 443 ssl http2;
        server_name synapse.yourdomain.com;  # CHANGE THIS

        # SSL certificates
        ssl_certificate /etc/letsencrypt/live/synapse.yourdomain.com/fullchain.pem;  # CHANGE THIS
        ssl_certificate_key /etc/letsencrypt/live/synapse.yourdomain.com/privkey.pem;  # CHANGE THIS

        # SSL configuration (Mozilla Intermediate)
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;
        ssl_prefer_server_ciphers off;
        ssl_session_cache shared:SSL:10m;
        ssl_session_timeout 1d;

        # API endpoints
        location /api/ {
            limit_req zone=api_limit burst=20 nodelay;
            
            proxy_pass http://api:8000/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # WebSocket support (if needed later)
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection "upgrade";
        }

        # Health check (no rate limit)
        location /health {
            proxy_pass http://api:8000/health;
            access_log off;
        }

        # Dashboard (SvelteKit)
        location / {
            limit_req zone=general_limit burst=50 nodelay;
            
            proxy_pass http://dashboard:3000/;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }
}
```

**Important:** Replace all instances of `synapse.yourdomain.com` with your actual domain.

---

## SSL Certificate Acquisition

### Initial Certificate Request

**Before starting the full stack**, get your first SSL certificate:

```bash
# 1. Create directories
mkdir -p certs certbot-webroot

# 2. Start temporary Nginx for ACME challenge
docker run -d --name nginx-temp \
  -p 80:80 \
  -v $(pwd)/certbot-webroot:/var/www/certbot \
  nginx:alpine

# Verify port 80 is accessible from outside
# Visit http://synapse.yourdomain.com/ (should show Nginx welcome)

# 3. Request certificate
docker run --rm \
  -v $(pwd)/certs:/etc/letsencrypt \
  -v $(pwd)/certbot-webroot:/var/www/certbot \
  certbot/certbot certonly \
  --webroot \
  -w /var/www/certbot \
  -d synapse.yourdomain.com \
  --email your-email@example.com \
  --agree-tos \
  --no-eff-email

# 4. Stop temporary Nginx
docker stop nginx-temp && docker rm nginx-temp

# 5. Verify certificate
ls -la certs/live/synapse.yourdomain.com/
# Should see: cert.pem, chain.pem, fullchain.pem, privkey.pem
```

**Certificate auto-renewal:** The `certbot` service in docker-compose will renew automatically every 12 hours (only renews when <30 days until expiry).

---

## Environment Variables

Create `.env` in project root (ensure it's in `.gitignore`):

```bash
# --- Database ---
DB_PASSWORD=your-secure-password-here-min-32-chars

# --- Discord ---
DISCORD_TOKEN=your-bot-token-from-discord-developer-portal
DISCORD_CLIENT_ID=your-oauth-app-id
DISCORD_CLIENT_SECRET=your-oauth-secret

# --- Security ---
# Generate with: python -c "import secrets; print(secrets.token_urlsafe(64))"
JWT_SECRET=your-jwt-secret-min-64-chars
```

**Generate secure secrets:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(64))"
```

---

## Deployment Steps

### 1. Prepare Docker Host

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER
newgrp docker

# Enable Docker on boot
sudo systemctl enable docker
```

### 2. Clone Repository

```bash
cd /opt  # or wherever you want to host it
git clone https://github.com/WanderingAstronomer/Synapse.git
cd Synapse
```

### 3. Configure Environment

```bash
# Create .env file
cp .env.example .env
nano .env  # Fill in your secrets

# Update nginx.conf with your domain
sed -i 's/synapse.yourdomain.com/your-actual-domain.com/g' nginx.conf
```

### 4. Acquire SSL Certificate

Follow **SSL Certificate Acquisition** steps above.

### 5. Start Services

```bash
# Build and start
docker compose up -d --build

# Verify services are running
docker compose ps

# Check logs
docker compose logs -f --tail=100

# Verify health
curl https://synapse.yourdomain.com/health
```

### 6. Database Initialization

```bash
# Run migrations
docker compose exec bot uv run alembic upgrade head

# Verify tables exist
docker compose exec db psql -U synapse -d synapse -c '\dt'
```

### 7. Test End-to-End

1. **Discord bot:** Send message in your server → bot should respond
2. **Dashboard:** Visit `https://synapse.yourdomain.com` → homepage loads
3. **API:** Visit `https://synapse.yourdomain.com/api/docs` → Swagger UI loads
4. **Health:** `curl https://synapse.yourdomain.com/health` → `{"status":"healthy"}`

---

## Backup Strategy

### Automated Daily Backups

Already configured in `docker-compose.yml`. Backups are stored in `./backups/`:

```bash
ls -lh backups/
# daily/synapse-2026-02-14.sql.gz
# weekly/synapse-week-7.sql.gz
# monthly/synapse-2026-02.sql.gz
```

### Offsite Sync (Recommended)

**Option A: Rsync to Another Machine**
```bash
# Add to crontab: crontab -e
0 4 * * * rsync -az /opt/Synapse/backups/ backup-server:/backups/synapse/
```

**Option B: Cloud Storage (Backblaze B2, ~$0.50/month for 100GB)**
```bash
# Install rclone
curl https://rclone.org/install.sh | sudo bash

# Configure B2
rclone config
# Follow prompts for Backblaze B2

# Add to crontab
0 4 * * * rclone sync /opt/Synapse/backups/ b2:synapse-backups/
```

### Manual Backup

```bash
# Create immediate backup
docker compose exec db pg_dump -U synapse synapse | gzip > manual-backup-$(date +%F).sql.gz
```

### Restore from Backup

```bash
# Stop services
docker compose down

# Restore database
gunzip < backups/daily/synapse-2026-02-14.sql.gz | \
  docker compose exec -T db psql -U synapse -d synapse

# Restart services
docker compose up -d
```

---

## Monitoring & Maintenance

### Uptime Kuma Setup

Access at `http://localhost:3001` (only from Docker host):

1. Create admin account
2. Add monitor:
   - **Type:** HTTP(s)
   - **URL:** `https://synapse.yourdomain.com/health`
   - **Interval:** 60 seconds
3. Add notification:
   - **Type:** Discord Webhook
   - **Webhook URL:** (from your Discord server settings)
4. Test notification

### Log Rotation

Docker handles log rotation automatically, but verify config:

```bash
# Check Docker daemon logs config
cat /etc/docker/daemon.json
```

If missing, create:
```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

Then restart Docker:
```bash
sudo systemctl restart docker
docker compose up -d
```

### Updates

```bash
# Monthly update routine
cd /opt/Synapse

# Pull latest code
git pull

# Update Docker images
docker compose pull

# Rebuild and restart
docker compose up -d --build

# Verify health
docker compose logs -f --tail=50
curl https://synapse.yourdomain.com/health
```

---

## Security Hardening

### 1. Firewall on Docker Host (UFW)

```bash
sudo apt install ufw

# Allow SSH from LAN only
sudo ufw allow from 192.168.88.0/24 to any port 22

# Allow HTTP/HTTPS from anywhere (proxied by MikroTik)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# Enable firewall
sudo ufw enable

# Verify
sudo ufw status
```

### 2. Disable SSH Password Auth

```bash
# Edit SSH config
sudo nano /etc/ssh/sshd_config

# Set these values:
PasswordAuthentication no
PermitRootLogin no
PubkeyAuthentication yes

# Restart SSH
sudo systemctl restart sshd
```

### 3. Auto-Security Updates

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### 4. Fail2Ban (Optional)

```bash
sudo apt install fail2ban

# Create Nginx jail
sudo nano /etc/fail2ban/jail.local
```

Add:
```ini
[nginx-http-auth]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log

[nginx-limit-req]
enabled = true
port = http,https
logpath = /var/log/nginx/error.log
```

```bash
sudo systemctl restart fail2ban
```

---

## Troubleshooting

### Port 80/443 Not Accessible from Outside

```bash
# On MikroTik, verify NAT rules
/ip firewall nat print

# On Docker host, verify nginx is listening
docker compose ps nginx
netstat -tlnp | grep :80

# Check firewall
sudo ufw status
```

### SSL Certificate Renewal Fails

```bash
# Check certbot logs
docker compose logs certbot

# Manual renewal test (dry-run)
docker compose exec certbot certbot renew --dry-run
```

### Database Connection Issues

```bash
# Check DB is healthy
docker compose exec db pg_isready -U synapse

# Check API can connect
docker compose exec api uv run python -c "
from synapse.database.engine import create_db_engine
engine = create_db_engine()
with engine.connect() as c:
    result = c.execute('SELECT 1').scalar()
    print('DB connected' if result == 1 else 'DB failed')
"
```

### Bot Not Responding in Discord

```bash
# Check bot logs
docker compose logs bot --tail=100

# Verify bot is in guild
docker compose exec bot uv run python -c "
import asyncio
from synapse.bot.core import SynapseBot
# Token from .env
bot = SynapseBot()
# Check guild count (should be > 0)
"
```

---

## Cost Breakdown

| Component | One-Time | Monthly |
|-----------|----------|---------|
| **Raspberry Pi 4 (4GB)** | $55 | — |
| **MicroSD Card (64GB)** | $12 | — |
| **Power supply** | $8 | — |
| **Electricity (3W 24/7)** | — | $0.30 |
| **Domain (optional)** | — | $1 (Cloudflare) |
| **Backblaze B2 (100GB)** | — | $0.50 |
| **Total** | **$75** | **$0.80** |

**vs. Azure:** $50/month → **60× more expensive**

**Break-even:** 1.5 months

---

## Summary Checklist

### Pre-Deployment
- [ ] MikroTik DDNS configured
- [ ] MikroTik port forwarding: 80, 443 → Docker host
- [ ] Docker host assigned static IP (DHCP reservation)
- [ ] Domain name points to your public IP
- [ ] `.env` file created with all secrets

### Deployment
- [ ] SSL certificate acquired via Certbot
- [ ] `docker compose up -d --build` successful
- [ ] Database migrations applied
- [ ] Health endpoint returns 200
- [ ] Bot responds in Discord

### Monitoring
- [ ] Uptime Kuma configured with Discord webhook
- [ ] Daily backups running (check `./backups/`)
- [ ] Offsite backup sync configured
- [ ] Log rotation configured

### Security
- [ ] UFW enabled with restricted SSH
- [ ] SSH password auth disabled
- [ ] Unattended upgrades enabled
- [ ] `.env` in `.gitignore` (secrets not committed)

---

## Notes for Network Config Repo

If you maintain a MikroTik config repo, add these sections:

**File: `firewall/nat.rsc`**
```routeros
# Synapse Discord Bot - HTTP/HTTPS
/ip firewall nat
add chain=dstnat action=dst-nat protocol=tcp dst-port=80 \
    to-addresses=192.168.88.10 to-ports=80 comment="Synapse HTTP"
add chain=dstnat action=dst-nat protocol=tcp dst-port=443 \
    to-addresses=192.168.88.10 to-ports=443 comment="Synapse HTTPS"
```

**File: `dhcp/static-leases.rsc`**
```routeros
# Synapse Docker Host
/ip dhcp-server lease
add address=192.168.88.10 mac-address=XX:XX:XX:XX:XX:XX \
    comment="Synapse Docker Host" server=defconf
```

**File: `scripts/ddns-update.rsc`**
```routeros
# DDNS update script (if using external provider)
:local ip [/ip address get [find interface=ether1] address];
:local ip [:pick $ip 0 [:find $ip "/"]];
/tool fetch mode=https url="https://your-ddns-provider.com/update?ip=$ip" keep-result=no;
```

Good luck with deployment! Let me know if you want me to implement the `/health` endpoint and the critical technical debt fixes now.
