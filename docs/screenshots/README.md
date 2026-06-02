# 📸 Screenshots-Anleitung

So machst du die 3 wichtigsten Screenshots für die README in ~10 Minuten.

## 1️⃣ `01-chat.png` — Conversational Flow

**Was zeigen:** Eine echte Chat-Konversation, die zeigt wie der Agent eine Bestellung aufnimmt.

**Schritte:**
1. Mac: Container muss laufen → `docker compose -f docker-compose.local.yml up -d`
2. Browser öffnen → `http://localhost:8080`
3. Eine kleine Demo-Konversation tippen:
   ```
   User: "Ich hätte gerne eine Schokoladentorte für 12 Personen, Geburtstag meiner Tochter nächsten Samstag."
   Bot:  → fragt nach Form, Farbe, etc.
   User: "Rund, mit lila Verzierung"
   Bot:  → bestätigt + zeigt Bild
   ```
4. Screenshot aufnehmen mit **CMD + Shift + 4** (Bereich auswählen)
5. Datei umbenennen → `01-chat.png` → in diesen Ordner kopieren

## 2️⃣ `02-cake.png` — DALL·E Generation

**Was zeigen:** Eine generierte Torte im UI.

**Schritte:**
1. Im gleichen Chat: lass den Bot die Torte rendern
2. Screenshot vom Bild **mit Beschreibung** daneben
3. → `02-cake.png`

## 3️⃣ `03-admin.png` — Admin Dashboard

**Was zeigen:** Bestellungsübersicht + Kosten-Monitoring.

**Schritte:**
1. Browser → `http://localhost:8080/admin/login`
2. ADMIN_PASSWORD aus deiner `.env` eintragen
3. Zur Bestellungs-Seite oder Cost-Dashboard
4. Screenshot
5. → `03-admin.png`

## 4️⃣ (Optional) `04-grafana.png`

Wenn du Grafana wieder anmachst und schicke Graphen hast:
```bash
docker compose -f docker-compose.monitoring.yml up -d
# Warten 30s, http://localhost:3000 öffnen, admin/kidstorte-admin
```

## 💡 Tipps für gute Screenshots

- **Browser-Fenster auf 1280×800** (CMD + +/- zum Zoomen)
- **Dark-Mode auf**, falls die App das hat → wirkt edler
- **Echte Werte** statt Lorem Ipsum (z.B. echte Preise, echter Bot-Text)
- **Konsole-Tab schließen** falls offen
- **Mauszeiger weg** von wichtigen Stellen
- Datei-Format: **PNG** (besser als JPG bei UI)

## 🎯 Quick-Variante (wenn du keine Zeit hast)

Statt der echten App-Screenshots: Open-Source-**Mockup-Generator** nutzen:
- https://shots.so — wirft die Screenshots in einen Browser-Frame
- https://screenshot.rocks — fügt Mac-Window-Chrome dazu

So sehen die Screenshots automatisch professioneller aus.

## 📤 Hochladen zu GitHub

```bash
# Wenn die 3 Dateien in docs/screenshots/ liegen:
cd /Users/schamjashahag/Kidstorte-longchain
git add docs/screenshots/*.png README.md
git commit -m "docs: add README screenshots + architecture diagrams"
git push
```

GitHub rendert das Mermaid-Diagramm und zeigt die Bilder automatisch.
