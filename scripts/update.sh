#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Kidstorte — Zero-Downtime Update
#
# Schritte:
#  1. Git pull
#  2. Backup vor Update
#  3. Neues Image bauen
#  4. Health-Test des neuen Image (im Test-Container)
#  5. Live-Container ersetzen (rolling restart)
#  6. Healthcheck — bei Fehler: Rollback
#  7. Altes Image aufräumen
#
# Usage:    ./scripts/update.sh
#           ./scripts/update.sh --no-pull       (überspringt git pull)
#           ./scripts/update.sh --no-backup     (überspringt Backup)
#           ./scripts/update.sh --branch=dev    (anderer Branch)
# ─────────────────────────────────────────────────────────────

set -euo pipefail

# ── Argumente ──
NO_PULL=0
NO_BACKUP=0
BRANCH=""
for arg in "$@"; do
    case $arg in
        --no-pull) NO_PULL=1 ;;
        --no-backup) NO_BACKUP=1 ;;
        --branch=*) BRANCH="${arg#--branch=}" ;;
        -h|--help)
            sed -n '3,15p' "$0"
            exit 0
            ;;
    esac
done

# ── Konfiguration ──
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.local.yml}"
IMAGE_NAME="${IMAGE_NAME:-kidstorte:local}"
SERVICE_NAME="${SERVICE_NAME:-kidstorte}"
CONTAINER_NAME="${CONTAINER_NAME:-kidstorte}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:5001/api/calendar/status}"
HEALTH_RETRIES="${HEALTH_RETRIES:-15}"
HEALTH_INTERVAL="${HEALTH_INTERVAL:-2}"

step() { printf "\n\033[1;34m▶ %s\033[0m\n" "$1"; }
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
warn() { printf "  \033[33m⚠\033[0m %s\n" "$1"; }
err()  { printf "  \033[31m✗\033[0m %s\n" "$1"; }

# ── 0. Pre-Flight ──
step "Pre-Flight-Checks"
[ -f "${COMPOSE_FILE}" ] || { err "Compose-File fehlt: ${COMPOSE_FILE}"; exit 1; }
[ -f .env ]              || { err ".env fehlt"; exit 1; }
command -v docker >/dev/null || { err "docker fehlt"; exit 1; }
ok "Compose, .env, docker da"

# Aktuelles Image-ID merken (für Rollback)
OLD_IMAGE_ID=$(docker images --no-trunc --quiet "${IMAGE_NAME}" | head -1)
if [ -n "${OLD_IMAGE_ID}" ]; then
    ok "Altes Image: ${OLD_IMAGE_ID:0:19}..."
else
    warn "Kein altes Image — erster Deploy"
fi

# ── 1. Git pull ──
if [ "${NO_PULL}" = "0" ]; then
    step "Git pull"
    if [ -d .git ]; then
        if [ -n "${BRANCH}" ]; then
            git checkout "${BRANCH}"
        fi
        git fetch --quiet
        BEFORE=$(git rev-parse HEAD)
        git pull --rebase --autostash 2>&1 | sed 's/^/   /'
        AFTER=$(git rev-parse HEAD)
        if [ "${BEFORE}" = "${AFTER}" ]; then
            ok "Schon aktuell (${AFTER:0:7})"
        else
            ok "Update: ${BEFORE:0:7} → ${AFTER:0:7}"
            echo
            git log --oneline "${BEFORE}..${AFTER}" | sed 's/^/   /'
        fi
    else
        warn "Kein git-Repo — skip pull"
    fi
else
    warn "Git pull übersprungen (--no-pull)"
fi

# ── 2. Backup ──
if [ "${NO_BACKUP}" = "0" ]; then
    step "Backup vor Update"
    if [ -x ./scripts/backup.sh ]; then
        ./scripts/backup.sh 2>&1 | tail -5 | sed 's/^/   /'
    else
        warn "scripts/backup.sh fehlt — überspringe"
    fi
else
    warn "Backup übersprungen (--no-backup)"
fi

# ── 3. Neues Image bauen ──
step "Image bauen"
BUILD_TS=$(date +%s)
docker compose -f "${COMPOSE_FILE}" build "${SERVICE_NAME}" 2>&1 | tail -6 | sed 's/^/   /'
NEW_IMAGE_ID=$(docker images --no-trunc --quiet "${IMAGE_NAME}" | head -1)
ok "Neues Image: ${NEW_IMAGE_ID:0:19}..."

if [ "${NEW_IMAGE_ID}" = "${OLD_IMAGE_ID}" ]; then
    ok "Image unverändert — kein Restart nötig"
    exit 0
fi

# ── 4. Health-Test (eigener Test-Container, keine Volumes) ──
step "Health-Test des neuen Image"
TEST_NAME="kidstorte-healthtest-${BUILD_TS}"
docker run -d --name "${TEST_NAME}" \
    --env-file .env \
    --network kidstorte-longchain_kidstorte-net \
    "${IMAGE_NAME}" >/dev/null

healthy=0
for i in $(seq 1 "${HEALTH_RETRIES}"); do
    sleep "${HEALTH_INTERVAL}"
    if docker exec "${TEST_NAME}" curl -fsS http://127.0.0.1:5001/api/calendar/status >/dev/null 2>&1; then
        healthy=1
        break
    fi
    echo -n "."
done
echo

if [ "${healthy}" = "1" ]; then
    ok "Neues Image antwortet"
    docker rm -f "${TEST_NAME}" >/dev/null
else
    err "Neues Image antwortet nicht"
    docker logs --tail 30 "${TEST_NAME}" 2>&1 | sed 's/^/   /'
    docker rm -f "${TEST_NAME}" >/dev/null
    err "Abbruch — Container bleibt unverändert"
    exit 1
fi

# ── 5. Live-Container ersetzen ──
step "Live-Container ersetzen"
docker compose -f "${COMPOSE_FILE}" up -d --no-deps "${SERVICE_NAME}" 2>&1 | sed 's/^/   /'

# ── 6. Healthcheck Live ──
step "Healthcheck Live"
healthy=0
for i in $(seq 1 "${HEALTH_RETRIES}"); do
    sleep "${HEALTH_INTERVAL}"
    status=$(docker inspect --format='{{.State.Health.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo "none")
    if [ "${status}" = "healthy" ]; then
        healthy=1
        break
    fi
    echo "   ${i}/${HEALTH_RETRIES}  status=${status}"
done

if [ "${healthy}" = "1" ]; then
    ok "Healthy"
else
    err "Container kommt nicht healthy hoch — ROLLBACK"
    if [ -n "${OLD_IMAGE_ID}" ]; then
        warn "Tag alt → ${IMAGE_NAME}"
        docker tag "${OLD_IMAGE_ID}" "${IMAGE_NAME}"
        docker compose -f "${COMPOSE_FILE}" up -d --no-deps "${SERVICE_NAME}"
    fi
    exit 1
fi

# ── 7. Aufräumen ──
step "Image-Aufräumen"
docker image prune -f --filter "label!=keep" 2>&1 | tail -3 | sed 's/^/   /'

echo
ok "Update erfolgreich — neues Image: ${NEW_IMAGE_ID:0:19}..."
docker compose -f "${COMPOSE_FILE}" ps --format 'table {{.Name}}\t{{.Status}}' | sed 's/^/   /'
