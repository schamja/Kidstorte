#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Kidstorte — Volume-Backup
# Sichert alle persistenten Daten (ChromaDB, SQLite, Bilder, PDFs)
# in einen Timestamp-Ordner.
#
# Usage:    ./scripts/backup.sh [/optional/backup-dir]
# Cron:     0 3 * * * cd /opt/kidstorte && ./scripts/backup.sh /backups/kidstorte
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Konfiguration ──
BACKUP_ROOT="${1:-./backups}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.local.yml}"
COMPOSE_PROJECT="${COMPOSE_PROJECT:-kidstorte-longchain}"
KEEP_DAYS="${KEEP_DAYS:-14}"   # alte Backups nach X Tagen löschen

# Volumes (project-prefixed)
VOLUMES=(
    "${COMPOSE_PROJECT}_chroma_data"
    "${COMPOSE_PROJECT}_sqlite_data"
    "${COMPOSE_PROJECT}_generated_images"
    "${COMPOSE_PROJECT}_generated_pdfs"
)

# ── Vorbereitung ──
TIMESTAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}"
mkdir -p "${BACKUP_DIR}"

echo "🗂  Backup nach: ${BACKUP_DIR}"
echo "📦 Compose-Projekt: ${COMPOSE_PROJECT}"
echo

# ── App-Container kurz pausieren für konsistenten DB-Stand ──
if docker compose -f "${COMPOSE_FILE}" ps --quiet kidstorte 2>/dev/null | grep -q .; then
    echo "⏸  App pausieren (für konsistente DB-Snapshots)…"
    docker compose -f "${COMPOSE_FILE}" pause kidstorte 2>&1 | sed 's/^/   /'
    RESUME_NEEDED=1
else
    echo "ℹ️  App läuft nicht — Skip pause"
    RESUME_NEEDED=0
fi

# ── Pro Volume ein TAR.GZ ──
EXIT_CODE=0
for vol in "${VOLUMES[@]}"; do
    name="${vol#${COMPOSE_PROJECT}_}"
    target="${BACKUP_DIR}/${name}.tar.gz"

    if ! docker volume inspect "${vol}" >/dev/null 2>&1; then
        echo "  ⚠  ${vol} — Volume existiert nicht, überspringe"
        continue
    fi

    echo "  📤 ${vol} → ${name}.tar.gz"
    # Mount Volume in Helper-Container, tar erstellen
    if docker run --rm \
        -v "${vol}:/data:ro" \
        -v "$(pwd)/${BACKUP_DIR}:/backup" \
        alpine:3.20 \
        sh -c "cd /data && tar czf /backup/${name}.tar.gz . 2>/dev/null"; then
        size=$(du -h "${target}" | awk '{print $1}')
        echo "     ✓ ${size}"
    else
        echo "     ✗ Backup fehlgeschlagen"
        EXIT_CODE=1
    fi
done

# ── App wieder freigeben ──
if [ "${RESUME_NEEDED}" = "1" ]; then
    echo
    echo "▶  App fortsetzen…"
    docker compose -f "${COMPOSE_FILE}" unpause kidstorte 2>&1 | sed 's/^/   /'
fi

# ── .env mitsichern (ohne ins Git!) ──
if [ -f .env ]; then
    cp .env "${BACKUP_DIR}/env.backup"
    chmod 600 "${BACKUP_DIR}/env.backup"
    echo
    echo "  📤 .env → env.backup (chmod 600)"
fi

# ── Manifest schreiben ──
cat > "${BACKUP_DIR}/MANIFEST.txt" <<EOF
Kidstorte Backup
================
Timestamp: ${TIMESTAMP}
Datum:     $(date '+%A, %d.%m.%Y %H:%M:%S')
Host:      $(hostname)
User:      $(whoami)
Compose:   ${COMPOSE_FILE}
Project:   ${COMPOSE_PROJECT}

Volumes:
$(for vol in "${VOLUMES[@]}"; do
    name="${vol#${COMPOSE_PROJECT}_}"
    if [ -f "${BACKUP_DIR}/${name}.tar.gz" ]; then
        size=$(du -h "${BACKUP_DIR}/${name}.tar.gz" | awk '{print $1}')
        echo "  ✓ ${name}.tar.gz (${size})"
    else
        echo "  ✗ ${name}.tar.gz (FEHLT)"
    fi
done)

Restore mit:
  ./scripts/restore.sh ${BACKUP_DIR}
EOF

echo
echo "📋 Manifest:"
cat "${BACKUP_DIR}/MANIFEST.txt" | sed 's/^/   /'

# ── Alte Backups bereinigen ──
if [ "${KEEP_DAYS}" -gt 0 ] && [ -d "${BACKUP_ROOT}" ]; then
    echo
    echo "🧹 Backups älter als ${KEEP_DAYS} Tage löschen…"
    deleted=$(find "${BACKUP_ROOT}" -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" | wc -l | tr -d ' ')
    if [ "${deleted}" -gt 0 ]; then
        find "${BACKUP_ROOT}" -maxdepth 1 -type d -mtime "+${KEEP_DAYS}" -exec rm -rf {} +
        echo "   ${deleted} alte Backup-Ordner gelöscht"
    else
        echo "   Nichts zu löschen"
    fi
fi

# ── Zusammenfassung ──
echo
total_size=$(du -sh "${BACKUP_DIR}" | awk '{print $1}')
echo "✅ Backup fertig: ${BACKUP_DIR} (${total_size})"
exit ${EXIT_CODE}
