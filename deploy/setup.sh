#!/bin/bash
# Run once on a fresh Ubuntu 22.04/24.04 VPS as root or with sudo.
# Replace DOMAIN with your actual subdomain (e.g. api.yourdomain.com).

set -euo pipefail
DOMAIN="api.yourdomain.com"
REPO_DIR="/home/ubuntu/axl"

# ── System packages ───────────────────────────────────────────────────────────
apt-get update -q
apt-get install -y git curl nginx certbot python3-certbot-nginx ufw

# ── uv (Python package manager) ───────────────────────────────────────────────
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.cargo/bin:$PATH"

# ── Clone repo ────────────────────────────────────────────────────────────────
git clone https://github.com/YOUR_ORG/YOUR_REPO.git "$REPO_DIR"
chown -R ubuntu:ubuntu "$REPO_DIR"

# ── Python deps ───────────────────────────────────────────────────────────────
cd "$REPO_DIR/agenc-api" && uv sync
cd "$REPO_DIR"           && uv sync   # root-level deps (workers, worker_tools)

# ── Firewall ──────────────────────────────────────────────────────────────────
ufw allow OpenSSH
ufw allow 'Nginx Full'
ufw --force enable

# ── nginx ─────────────────────────────────────────────────────────────────────
cp "$REPO_DIR/deploy/nginx.conf" /etc/nginx/sites-available/agenc
sed -i "s/api.yourdomain.com/$DOMAIN/g" /etc/nginx/sites-available/agenc
ln -sf /etc/nginx/sites-available/agenc /etc/nginx/sites-enabled/agenc
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx

# ── SSL ───────────────────────────────────────────────────────────────────────
certbot --nginx -d "$DOMAIN" --non-interactive --agree-tos -m admin@yourdomain.com

# ── systemd services ──────────────────────────────────────────────────────────
cp "$REPO_DIR/deploy/agenc-api.service" /etc/systemd/system/
cp "$REPO_DIR/deploy/worker1.service"   /etc/systemd/system/
cp "$REPO_DIR/deploy/worker2.service"   /etc/systemd/system/
systemctl daemon-reload
systemctl enable agenc-api worker1 worker2
systemctl start  agenc-api worker1 worker2

echo ""
echo "✓ Done. Check status with: systemctl status agenc-api worker1 worker2"
echo "✓ Logs: journalctl -fu agenc-api"
