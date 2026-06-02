# 🎬 Loom-Video-Skript — Kidstorte-Demo (3 Min)

> **Ziel:** Recruiter in 3 Minuten überzeugen, dass du Production-AI-Engineering kannst.
> **Format:** Screen-Recording + dein Gesicht in der Ecke (Loom macht beides automatisch).

---

## 🎯 Vor der Aufnahme

### Setup (3 Min Vorbereitung)

```bash
# 1. Container hochfahren
cd /Users/schamjashahag/Kidstorte-longchain
docker compose -f docker-compose.local.yml up -d

# 2. Im Browser: 2 Tabs vorbereiten
#    Tab 1: http://localhost:8080        ← Chat-App
#    Tab 2: http://localhost:8080/admin/login  ← Admin (schon eingeloggt!)

# 3. Browser-Zoom auf 110-125 % stellen (CMD + +)
#    → Schrift gut lesbar im Video
```

### Vor dem Aufnehmen
- ☕ Wasser trinken, Stimme räuspern
- 📱 Handy stumm, Slack/Discord-Sounds aus
- 🪞 Webcam-Position checken (du im oberen Drittel)
- 🎤 Kein Echo, kein Lüfter-Lärm

### Loom-Einstellungen
- **Screen + Cam** (du siehst dich in der Ecke)
- **HD 720p oder 1080p**
- **Aufnahme starten** → 3-2-1-Countdown

---

## 📝 Das Skript — Wort für Wort

> **Lege das Skript auf den zweiten Monitor (oder Handy daneben).**
> **Sprich frei**, nicht ablesen — die Stichpunkte sind nur Anker.
> **Gesamtdauer: 3:00 Min**

---

### 🎬 [0:00 — 0:20] · INTRO

**👤 Du siehst in die Kamera (kein Bildschirm)**

> „Hi, ich bin **[Schamja]**.
>
> Das ist Kidstorte — ein **AI-Bestellassistent für eine Konditorei**, den ich als Production-Projekt aufgebaut habe.
>
> In 3 Minuten zeig ich dir drei Sachen:
> erstens den **Conversational Flow** mit Multi-Agent-Architektur,
> zweitens die **DALL-E-Bild-Generierung** als Vorschau,
> und drittens die Production-Engineering-Schicht — also wie ich dafür gesorgt hab, dass das **nicht nur ein Demo bleibt**."

**🎬 Aktion:** Wechsel zu Tab 1 (`http://localhost:8080`)

---

### 🎬 [0:20 — 1:20] · CONVERSATIONAL FLOW

**🖥 Screen: Chat-App offen**

> „So sieht der Kunde die App. Ich tippe einfach natürlich los:"

**⌨️ Tippe in den Chat** (sprich währenddessen):

```
Ich hätte gerne eine Schokoladentorte für 12 Personen,
Geburtstag meiner Tochter nächsten Samstag.
```

**⏸ Bot antwortet — du erklärst während er rendert:**

> „Was hier im Hintergrund passiert: meine **LangGraph-Pipeline** klassifiziert zuerst die Intention — `order`, nicht `info` oder `greeting` — extrahiert dann die Bestellfelder.
>
> Du siehst — er hat schon `Schokolade`, `12 Personen` und das `Datum` rausgelesen.
> Und er fragt jetzt nach dem fehlenden Feld."

**⌨️ Antwort auf Bot-Frage tippen** (z.B. Form/Farbe):

```
Rund, mit lila Verzierung
```

**⏸ Bot rendert die nächste Antwort:**

> „Und genau hier ist der **kritische Punkt** an dem ich abweich vom Standard-LLM-Pattern: für den **Preis** würde GPT mir gerne irgendeinen Wert ausgeben — der könnte halluziniert sein.
>
> Stattdessen hab ich einen **deterministischen Regel-Engine** gebaut: Gewicht × Stundensatz × Aufschlag für Spezial-Wünsche.
> Der LLM macht das Sprachverständnis, mein Code macht die Mathematik."

---

### 🎬 [1:20 — 2:00] · DALL-E IMAGE GENERATION

**🖥 Screen: Chat zeigt jetzt generierte Torte**

> „Bevor der Kunde verbindlich bestellt, kriegt er eine **DALL-E-3-Vorschau** seiner Torte.
>
> Das hat zwei Gründe: erstens **Conversion** — viel höhere Abschlussrate wenn man sieht was man bekommt.
>
> Zweitens **Kosten-Optimierung** — jedes Bild kostet mich vier Cent.
> Deshalb hab ich eine **Response-Cache-Schicht** gebaut: gleiche Konfiguration → kein neuer API-Call.
> Spart in Production rund **40 Prozent** der OpenAI-Kosten."

**🎬 Aktion:** Wechsel zu Tab 2 (Admin-Dashboard)

---

### 🎬 [2:00 — 2:30] · ADMIN DASHBOARD

**🖥 Screen: Admin-Übersicht mit Bestellungen + Cost-Monitoring**

> „Das ist die Admin-Seite — hier sieht der Konditor seine **Bestellungen**, **Bewertungen**, und für mich am wichtigsten: das **Cost-Dashboard**.
>
> Du siehst Token-Verbrauch live, Tageskosten, und der **Daily-Budget-Cap** schaltet automatisch auf ein **billigeres Fallback-Modell** wenn das Limit erreicht ist.
>
> Plus: **LangSmith-Integration** — jede Konversation ist im Tracing-Tool sichtbar, ich kann jeden Halluzinations-Fall reproduzieren."

---

### 🎬 [2:30 — 3:00] · PRODUCTION ENGINEERING

**🎬 Aktion:** Kurz auf den Code-Editor wechseln (z.B. README mit Tree)
**🖥 Screen: README.md oder Tree der Projekt-Struktur**

> „Was das hier von einem Demo unterscheidet:
>
> Multi-Stage **Docker** mit Non-Root-User, 250 MB Runtime-Image,
> ein **Zero-Downtime-Update-Skript** das vor dem Live-Swap das neue Image gegen einen Healthcheck testet und bei Fehlern automatisch zurückrollt,
> ein **Backup-Skript** das den Container pausiert für konsistente DB-Snapshots,
> und Production-TLS via Let's Encrypt mit Auto-Renewal.
>
> Stack ist **FastAPI**, **LangGraph**, **RAG via ChromaDB**, **GPT-4o-mini** und **DALL-E** — getraced mit **LangSmith**.
>
> Code ist auf meinem GitHub — Link in der Beschreibung.
> Danke fürs Anschauen!"

**👤 Letzte 2 Sekunden: in die Kamera schauen, kurz lächeln**

**🛑 Loom-Aufnahme stoppen**

---

## 🎨 Loom-Bearbeitung (nach Aufnahme)

Loom erlaubt ein paar einfache Verbesserungen:

| Feature | Wo | Wann nutzen |
|---|---|---|
| **Trim** | Bearbeiten-Modus | Anfang/Ende abschneiden wo du noch nichts sagst |
| **Title** | „Edit details" | „Kidstorte — AI Cake-Ordering Agent (3 min demo)" |
| **Description** | „Edit details" | GitHub-Link + Tech-Stack + dein LinkedIn |
| **Custom thumbnail** | „Edit details" | Screenshot der App + dein Gesicht |
| **CTAs** | „Edit details" | „View on GitHub →" mit Repo-Link |

---

## 📤 Loom-URL in deine Bewerbungen

Nach der Aufnahme kriegst du eine URL wie:
```
https://loom.com/share/a1b2c3d4e5...
```

Hier einbauen:

### 1. README am Anfang
Suche in `README.md` die Zeile:
```
🎥 Video walkthrough: *(add Loom link)*
```
Ersetzen mit:
```
🎥 [Video walkthrough (3 min)](https://loom.com/share/DEINELOOMID)
```

### 2. In LinkedIn-Featured-Section
- LinkedIn-Profil → „Featured" → „Add" → Link → Loom-URL
- Dein Profil zeigt das Video direkt ohne Klick

### 3. In Bewerbungs-E-Mails
```
[…]
Im Anhang finden Sie meinen CV.
Eine 3-minütige Demo meines Kidstorte-Projekts:
👉 [Loom-Link]
[…]
```

---

## ⚠️ Häufige Anfänger-Fehler

| Fehler | Was stattdessen |
|---|---|
| Zu schnell sprechen | Pausen sind OK — wirken souverän |
| Sich entschuldigen („das ist nur eine kleine Demo…") | Nie! Auftritt: „Das ist Kidstorte — das hab ich gebaut." |
| In Floskeln verlieren | Nutze das Skript als Anker |
| Zu viel auf einmal | 3 Punkte reichen — Conversational, Bild, Production |
| Geräusch-Hintergrund | Türen zu, Fenster zu, Lüfter aus |
| Tipp-Fehler korrigieren | Lass sie drin → wirkt echt |

---

## 🎯 Wenn du noch besser sein willst

**Zweite Version mit besseren Punkten:**
1. Erst diese 3-Min-Variante aufnehmen → Recruiter-tauglich
2. Wenn du Zeit hast: eine **6-Min-Tech-Variante** für Tech-Leads die mehr wissen wollen
3. Pinne beide auf dein LinkedIn-Profil

**Beispiel-Tech-Erweiterung (3 zusätzliche Min):**
- LangSmith-Trace zeigen (echter Request)
- Code-Snippet vom Pricing-Engine (`services/cost_optimizer.py`)
- Docker-Compose `down` + `up -d` → Container kommt healthy hoch

---

## ✅ Checkliste vor der Aufnahme

- [ ] Container läuft: `docker ps | grep healthy`
- [ ] Browser-Tabs offen (Chat + Admin)
- [ ] Mikrofon-Test (Loom hat einen)
- [ ] Webcam-Frame ok (du oben rechts/links)
- [ ] Skript daneben offen
- [ ] Wasserglas in Reichweite
- [ ] Notifications/Sounds aus
- [ ] Sauberer Desktop (keine privaten Sachen)
- [ ] Browser-Lesezeichen-Leiste leer/aufgeräumt

**Wenn alle Häkchen drin: 🎬 Aufnahme starten.**

Viel Erfolg!
