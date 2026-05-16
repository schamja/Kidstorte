# Kidstorte Deployment

Docker-basiertes Deploy mit nginx + Let's Encrypt TLS.

## Voraussetzungen

- Linux-Server (Ubuntu/Debian 22.04+ empfohlen)
- Docker + Docker Compose installiert
- Domain die auf den Server zeigt (A-Record)
- Ports 80 + 443 offen

```bash
# Docker installieren (falls noch nicht da)
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER       # neu einloggen!
```

## 1) Code holen

```bash
git clone <repo-url> /opt/kidstorte
cd /opt/kidstorte
```

## 2) `.env` anlegen

```bash
cp .env.example .env
nano .env       # OPENAI_API_KEY und ADMIN_PASSWORD setzen!
chmod 600 .env
```

## 3) Domain in nginx-Config eintragen

```bash
# "kidstorte.example.com" überall ersetzen
sed -i 's/kidstorte.example.com/DEINE-DOMAIN.de/g' deploy/nginx.conf
```

## 4) Referenzbilder ins `Bilder/`-Verzeichnis

```bash
# Auf dem Dev-Rechner:
rsync -av Bilder/ user@server:/opt/kidstorte/Bilder/
```

## 5) Erstes Zertifikat holen

Beim ersten Mal muss nginx OHNE TLS starten, damit Certbot die ACME-Challenge ausliefern kann:

```bash
# Provisorische nginx-Config nur mit HTTP für die Challenge
docker compose up -d kidstorte
docker run --rm \
    -v $(pwd)/deploy/certbot/conf:/etc/letsencrypt \
    -v $(pwd)/deploy/certbot/www:/var/www/certbot \
    -p 80:80 \
    certbot/certbot certonly --standalone \
    --email DEINE-EMAIL@example.com \
    --agree-tos --no-eff-email \
    -d DEINE-DOMAIN.de

# Jetzt nginx (mit TLS) + alle Services hochfahren
docker compose up -d
```

## 6) Smoke-Test

```bash
curl -I https://DEINE-DOMAIN.de/
curl https://DEINE-DOMAIN.de/api/calendar/status
docker compose ps               # alle Container "healthy"?
docker compose logs -f kidstorte
```

## Updates einspielen

### Variante A — Manuell

```bash
cd /opt/kidstorte
git pull
docker compose pull kidstorte         # Image aus ghcr.io
docker compose up -d kidstorte        # rolling restart, ~5s Downtime
```

### Variante B — Auto-Deploy via GitHub Actions (empfohlen)

Bei jedem `git push origin main` baut GitHub Actions ein neues Image,
pusht es zu `ghcr.io/<owner>/<repo>:latest` und SSH't auf den Server,
um es zu pullen und zu restarten. Workflow-Datei: `.github/workflows/deploy.yml`.

**Setup (einmalig):**

1. **Deploy-User auf dem Server anlegen** (sicherer als root):
   ```bash
   sudo adduser --disabled-password --gecos "" deploy
   sudo usermod -aG docker deploy
   sudo mkdir -p /home/deploy/.ssh && sudo chmod 700 /home/deploy/.ssh
   ```

2. **SSH-Key generieren** (lokal, NICHT mit Passphrase):
   ```bash
   ssh-keygen -t ed25519 -f kidstorte_deploy -N ""
   # → Public Key auf den Server:
   ssh-copy-id -i kidstorte_deploy.pub deploy@DEIN-SERVER
   # → Test:
   ssh -i kidstorte_deploy deploy@DEIN-SERVER 'docker ps'
   ```

3. **GitHub-Secrets setzen** (Repo → Settings → Secrets and variables → Actions):

   | Secret | Wert | Pflicht |
   |---|---|---|
   | `SSH_HOST` | `1.2.3.4` oder `kidstorte.example.com` | ✓ |
   | `SSH_USER` | `deploy` | ✓ |
   | `SSH_PRIVATE_KEY` | Inhalt der Datei `kidstorte_deploy` (kompletter Block) | ✓ |
   | `SSH_PORT` | `22` (nur wenn anderer Port) | ✗ |
   | `DEPLOY_PATH` | `/opt/kidstorte` (nur wenn anderer Pfad) | ✗ |
   | `PUBLIC_URL` | `https://kidstorte.example.com` (für Post-Deploy Smoke-Test) | ✗ |

4. **Server vorbereiten** (einmalig, damit `git reset --hard` funktioniert):
   ```bash
   sudo chown -R deploy:deploy /opt/kidstorte
   sudo -iu deploy
   cd /opt/kidstorte
   git config --global --add safe.directory /opt/kidstorte
   # ghcr.io-Image erstmals manuell pullen (CI hat es noch nicht gepusht):
   docker login ghcr.io     # mit GitHub-User + Personal-Access-Token (read:packages)
   docker compose pull kidstorte
   docker compose up -d
   ```

5. **Image-Sichtbarkeit** in GitHub auf "private" lassen — der Workflow nutzt
   `GITHUB_TOKEN` mit `packages: write` automatisch, am Server muss aber
   einmalig per `docker login ghcr.io` ein Token mit `read:packages` hinterlegt
   werden (siehe Schritt 4).

**Deploy auslösen:**
- Automatisch: `git push origin main`
- Manuell: GitHub UI → Actions → "Deploy" → "Run workflow"

## Rollback bei kaputtem Deploy

Wenn ein Deploy live geht und etwas kaputt ist — in **< 1 Minute** zurück zur letzten funktionierenden Version.

### Variante A — "previous" (häufigster Fall)

GitHub UI → **Actions → "Rollback" → Run workflow**:

| Feld | Wert |
|---|---|
| `tag` | `previous` |
| `reason` | z.B. "Bildgenerierung kaputt nach commit abc123" |

Der Workflow liest `.deploy-history` auf dem Server, findet den vorletzten
Deploy-Tag und rollt darauf zurück.

### Variante B — Spezifischer Tag

Wenn `previous` nicht reicht (z.B. die letzten 3 Deploys waren alle kaputt):

1. Tags anschauen: `https://github.com/<owner>/<repo>/pkgs/container/<repo>`
2. UI → "Rollback" → `tag` = z.B. `sha-a1b2c3d` oder `42` (Build-Nummer)

### Variante C — Manuell auf dem Server (ohne GitHub)

```bash
ssh deploy@kidstorte-server
cd /opt/kidstorte
cat .deploy-history | tail -10                # letzte Deploys anschauen
sed -i 's|^KIDSTORTE_IMAGE=.*|KIDSTORTE_IMAGE=ghcr.io/OWNER/REPO:sha-a1b2c3d|' .env
docker compose pull kidstorte
docker compose up -d --no-deps kidstorte
docker logs -f kidstorte
```

### Notfall-Modus

`skip_health_check: true` rollt zurück OHNE auf "healthy" zu warten — wenn der
Healthcheck-Endpoint selbst kaputt ist, du aber weißt dass die alte Version OK war.

### Was `.deploy-history` enthält

Eine Zeile pro Deploy / Rollback:

```
2026-05-16T13:14:01Z sha-a1b2c3d deploy by:schamja sha:a1b2c3d4e5f...
2026-05-16T15:22:45Z sha-9f8e7d6 deploy by:schamja sha:9f8e7d6c5b4...
2026-05-16T15:24:12Z sha-a1b2c3d rollback by:schamja reason:"Bildgen kaputt"
```

Letzte 50 Einträge werden behalten.

**Was passiert genau:**
1. CI-Job läuft (Lint + Build-Test) — siehe `ci.yml`
2. Deploy-Job baut Multi-Arch-Image, pusht zu `ghcr.io`
3. SSH → `git pull` (für `docker-compose.yml`/`nginx.conf`-Änderungen)
4. `docker compose pull` → neues Image
5. `docker compose up -d --no-deps kidstorte` → rolling restart
6. Wartet bis Container "healthy" (max 150s) — sonst Deploy gilt als failed
7. Optional: Smoke-Test auf `PUBLIC_URL`

## Backups

`chroma_db`, `sqlite_data`, `generated_images`, `generated_pdfs` sind Docker-Volumes — werden NICHT von `git pull` angefasst, aber auch nicht ohne Cron gesichert.

```bash
# /etc/cron.daily/kidstorte-backup
#!/bin/bash
BACKUP=/var/backups/kidstorte
mkdir -p $BACKUP
docker run --rm \
    -v kidstorte_chroma_data:/chroma \
    -v kidstorte_sqlite_data:/sqlite \
    -v kidstorte_generated_images:/imgs \
    -v $BACKUP:/backup \
    alpine tar -czf /backup/kidstorte-$(date +%F).tar.gz /chroma /sqlite /imgs
find $BACKUP -name "kidstorte-*.tar.gz" -mtime +14 -delete
```

## Troubleshooting

| Symptom | Ursache | Fix |
|---|---|---|
| Chat „hängt", Stream kommt erst am Ende | nginx-Buffering an | `proxy_buffering off` in `nginx.conf` prüfen |
| Container startet, dann "unhealthy" | OPENAI_API_KEY fehlt → ValueError | `docker compose logs kidstorte` lesen, `.env` prüfen |
| Bilder generiert aber 404 im Browser | Volume nicht gemountet | `docker compose down && up -d` (Volume neu binden) |
| 502 Bad Gateway | App-Container down | `docker compose ps`, dann `restart kidstorte` |
| TLS-Zert läuft ab | Certbot-Renewal kaputt | `docker compose logs certbot` lesen |

## Skalieren

Ein Worker pro Container ist hart (`_IMAGE_CACHE` ist in-process).
Mehr Last? Mehrere Container hinter nginx als Upstream-Pool — aber dann brauchst du Redis für gemeinsamen Cache + Session-Store.
