#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Kidstorte — Volume-Restore
# Liest ein Backup-Verzeichnis zurück in die Docker-Volumes.
#
# Usage:    ./scripts/restore.sh <backup-dir>
# Beispiel: ./scripts/restore.sh ./backups/20260529-153000
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Argumente ──
if [ $# -lt 1 ]; then
    echo "Usage: $0 <backup-dir>"
    echo
    echo "Verfügbare Backups:"
    if [ -d ./backups ]; then
        ls -1t ./backups | head -10 | sed 's/^/  ./backups\//'
    else
        echo "  (keine)"
    fi
    exit 1
fi

BACKUP_DIR="$1"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.local.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-kidstorte-longchain}"

if [ ! -d "${BACKUP_DIR}" ]; then
    echo "❌ Backup-Verzeichnis nicht gefunden: ${BACKUP_DIR}"
    exit 1
fi

echo "📂 Backup: ${BACKUP_DIR}"
[ -f "${BACKUP_DIR}/MANIFEST.txt" ] && cat "${BACKUP_DIR}/MANIFEST.txt" | head -10
echo

# ── Sicherheits-Abfrage ──
read -r -p "⚠️  Bestehende Daten werden ÜBERSCHRIEBEN. Fortfahren? (yes/NO) " confirm
if [ "${confirm}" != "yes" ]; then
    echo "Abgebrochen."
    exit 0
fi

# ── Container stoppen ──
echo
echo "⏸  Container stoppen…"
if docker compose -f "${COMPOSE_FILE}" ps --quiet 2>/dev/null | grep -q .; then
    docker compose -f "${COMPOSE_FILE}" stop 2>&1 | sed 's/^/   /'
fi

# ── Pro TAR.GZ in Volume zurückspielen ──
EXIT_CODE=0
for tar in "${BACKUP_DIR}"/*.tar.gz; do
    [ -f "${tar}" ] || continue
    name=$(basename "${tar}" .tar.gz)
    vol="${COMPOSE_PROJECT}_${name}"

    echo
    echo "📥 ${name}.tar.gz → ${vol}"

    # Volume neu erstellen (löscht alten Inhalt)
    docker volume rm -f "${vol}" >/dev/null 2>&1 || true
    docker volume create "${vol}" >/dev/null

    if docker run --rm \
        -v "${vol}:/data" \
        -v "$(pwd)/${BACKUP_DIR}:/backup:ro" \
        alpine:3.20 \
        sh -c "cd /data && tar xzf /backup/${name}.tar.gz"; then
        size=$(docker run --rm -v "${vol}:/data:ro" alpine:3.20 du -sh /data | awk '{print $1}')
        echo "   ✓ wiederhergestellt (${size})"
    else
        echo "   ✗ Restore fehlgeschlagen"
        EXIT_CODE=1
    fi
done

# ── .env optional zurückspielen ──
if [ -f "${BACKUP_DIR}/env.backup" ]; then
    echo
    read -r -p "🔑 .env aus Backup einspielen? (yes/NO) " env_confirm
    if [ "${env_confirm}" = "yes" ]; then
        cp .env .env.bak.$(date +%s) 2>/dev/null || true
        cp "${BACKUP_DIR}/env.backup" .env
        chmod 600 .env
        echo "   ✓ .env wiederhergestellt (alte → .env.bak.<ts>)"
    fi
fi

# ── Container wieder starten ──
echo
echo "▶  Container starten…"
docker compose -f "${COMPOSE_FILE}" up -d 2>&1 | sed 's/^/   /'

echo
echo "✅ Restore fertig. Status:"
docker compose -f "${COMPOSE_FILE}" ps
exit ${EXIT_CODE}
