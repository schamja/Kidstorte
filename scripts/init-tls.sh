#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Kidstorte — Let's Encrypt TLS-Initialisierung
#
# Holt das erste TLS-Zertifikat für deine Domain über Certbot.
# Danach läuft das Production-Setup mit HTTPS.
#
# Usage:
#   DOMAIN=deine.de EMAIL=du@beispiel.de ./scripts/init-tls.sh
#
# Voraussetzungen:
#  - DNS A-Record deiner Domain zeigt auf diesen Server
#  - Port 80 + 443 von außen erreichbar
#  - kidstorte-Container läuft schon
# ─────────────────────────────────────────────────────────────

set -euo pipefail

DOMAIN="${DOMAIN:-}"
EMAIL="${EMAIL:-}"
STAGING="${STAGING:-0}"   # STAGING=1 für Test-Zertifikat (kein Rate-Limit)

if [ -z "${DOMAIN}" ] || [ -z "${EMAIL}" ]; then
    cat <<'EOF'
❌ DOMAIN und EMAIL müssen gesetzt sein.

Beispiel:
  DOMAIN=kidstorte.de EMAIL=admin@kidstorte.de ./scripts/init-tls.sh

Für Test-Zertifikat (keine Rate-Limits):
  STAGING=1 DOMAIN=test.kidstorte.de EMAIL=... ./scripts/init-tls.sh
EOF
    exit 1
fi

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m⚠\033[0m %s\n" "$1"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$1"; }

CERT_DIR="./deploy/certbot/conf"
WEB_ROOT="./deploy/certbot/www"

# ── 1. Verzeichnisse ──
step "Verzeichnisse anlegen"
mkdir -p "${CERT_DIR}" "${WEB_ROOT}"
ok "${CERT_DIR}"
ok "${WEB_ROOT}"

# ── 2. nginx.conf Domain ersetzen ──
step "nginx.conf für Domain konfigurieren"
if [ -f deploy/nginx.conf ]; then
    cp deploy/nginx.conf deploy/nginx.conf.bak
    sed -i.tmp "s/kidstorte\.example\.com/${DOMAIN}/g" deploy/nginx.conf && rm deploy/nginx.conf.tmp
    ok "Domain in deploy/nginx.conf eingesetzt (Backup: nginx.conf.bak)"
else
    err "deploy/nginx.conf fehlt"
    exit 1
fi

# ── 3. DNS-Check ──
step "DNS-Check"
resolved_ip=$(host "${DOMAIN}" 2>/dev/null | awk '/has address/ {print $4; exit}' || echo "")
public_ip=$(curl -s ifconfig.me 2>/dev/null || echo "?")
if [ "${resolved_ip}" = "${public_ip}" ]; then
    ok "${DOMAIN} → ${resolved_ip} ✓"
elif [ -z "${resolved_ip}" ]; then
    err "${DOMAIN} ist nicht aufzulösen"
    warn "DNS-Eintrag setzen und 5–30 Min warten"
    exit 1
else
    warn "${DOMAIN} → ${resolved_ip}  ABER Server-IP: ${public_ip}"
    warn "DNS-Eintrag prüfen, dann erneut starten"
    read -r -p "  Trotzdem fortfahren? (yes/NO) " confirm
    [ "${confirm}" = "yes" ] || exit 1
fi

# ── 4. Dummy-Zertifikat für nginx-Start ──
# nginx braucht *irgendein* Zertifikat um zu starten — wir machen ein temp self-signed
step "Dummy-Zertifikat (für nginx-Boot)"
DUMMY_DIR="${CERT_DIR}/live/${DOMAIN}"
mkdir -p "${DUMMY_DIR}"
if [ ! -f "${DUMMY_DIR}/fullchain.pem" ]; then
    docker run --rm -v "$(pwd)/${CERT_DIR}:/etc/letsencrypt" \
        --entrypoint sh certbot/certbot:latest -c "
        openssl req -x509 -nodes -newkey rsa:2048 -days 1 \
            -keyout '/etc/letsencrypt/live/${DOMAIN}/privkey.pem' \
            -out '/etc/letsencrypt/live/${DOMAIN}/fullchain.pem' \
            -subj '/CN=${DOMAIN}'
    "
    ok "Dummy-Zertifikat angelegt"
else
    ok "Bestehende Zertifikate gefunden"
fi

# ── 5. Production-Compose hochfahren ──
step "Production-Compose starten (nginx + certbot)"
docker compose up -d 2>&1 | tail -10 | sed 's/^/   /'
sleep 5

# ── 6. Echtes Zertifikat anfordern ──
step "Let's Encrypt anfragen"
rm -rf "${DUMMY_DIR}"     # Dummy weg, damit Certbot eigenes anlegt
STAGE_FLAG=""
if [ "${STAGING}" = "1" ]; then
    STAGE_FLAG="--staging"
    warn "STAGING-Modus — Zertifikat ist nicht öffentlich vertrauenswürdig"
fi

docker compose run --rm --entrypoint "
    certbot certonly --webroot -w /var/www/certbot \
        ${STAGE_FLAG} \
        --email ${EMAIL} \
        --agree-tos \
        --no-eff-email \
        --force-renewal \
        --non-interactive \
        -d ${DOMAIN}
" certbot 2>&1 | tail -15 | sed 's/^/   /'

# ── 7. nginx reload ──
step "nginx neu laden mit echtem Zertifikat"
docker compose exec nginx nginx -s reload 2>&1 | sed 's/^/   /'

# ── 8. Test ──
step "HTTPS-Test"
sleep 3
if curl -sS -o /dev/null -w "HTTP %{http_code}\n" "https://${DOMAIN}/api/calendar/status"; then
    ok "https://${DOMAIN} antwortet!"
else
    warn "HTTPS noch nicht erreichbar — gib's noch 30 Sek"
fi

cat <<EOF

✅ TLS-Init fertig.

Status:
  Production:    https://${DOMAIN}
  Cert-Renewal:  automatisch (certbot-Container läuft im Hintergrund)
  nginx-Logs:    docker compose logs -f nginx
  App-Logs:      docker compose logs -f kidstorte

Vor Production-Go-Live noch checken:
  • Backup eingerichtet (cron für scripts/backup.sh)
  • Monitoring eingerichtet (docker-compose.monitoring.yml)
  • Update-Pipeline getestet (scripts/update.sh)
  • Admin-Passwort in .env stark genug
  • Firewall: nur Port 80, 443 (+ SSH) offen
EOF
