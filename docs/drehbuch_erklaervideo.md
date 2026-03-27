# Erklaervideo Drehbuch: Kidstorte - KI-Bestellassistent
## Dauer: ca. 2 Minuten

---

### SZENE 1: Einfuehrung (0:00 - 0:15)
**[Zeige: Logo + Chat-Oberflaeche]**

> "Kidstorte ist ein KI-gestuetzter Bestellassistent fuer eine Konditorei.
> Der Kunde schreibt im Chat was er moechte - und die KI fuehrt ihn
> Schritt fuer Schritt durch die komplette Bestellung bis zum fertigen Vorschaubild.
> Das Ganze basiert auf dem LangGraph-Prinzip - einer State-Machine-Architektur
> bei der jeder Schritt ein eigener Knoten ist."

---

### SZENE 2: Die Dateien und ihre Aufgaben (0:15 - 0:55)
**[Zeige: Dateistruktur / Architektur-Diagramm]**

> "Das System besteht aus mehreren Dateien, die wie Abteilungen in einer Baeckerei zusammenarbeiten."

**[Zeige nacheinander jede Datei, z.B. als Karte/Box]**

> "**main.py** ist der Empfang - er nimmt die Kundennachricht entgegen
> und leitet sie an die richtige Stelle weiter.
>
> **graph.py** ist der Dirigent - er implementiert das LangGraph-Muster:
> Eine State Machine, die den Kundenwunsch durch verschiedene Knoten routet.
> Soll die KI begrueessen? Bestelldaten sammeln? Oder ein Bild generieren?
> graph.py entscheidet das anhand des erkannten Intents.
> Das Besondere: Das LangGraph-Muster wurde selbst gebaut - ohne die externe Bibliothek.
> Gleiche Architektur, eigener Code.
>
> **nodes.py** ist das Herzstueck - hier passiert die eigentliche Arbeit:
> 14 Knoten fuer Intent erkennen, Daten extrahieren, Preise berechnen und Bilder erzeugen.
> Jeder Node ist ein Spezialist fuer eine Aufgabe.
>
> **state.py** ist das Klemmbrett - der AgentState speichert alle Informationen
> die waehrend des Gespraechs gesammelt werden: Chatverlauf, Bestelldetails,
> fehlende Felder und den erkannten Intent.
>
> **config.py** liefert die Einstellungen - API-Keys, Prompts
> und die Bot-Persoenlichkeit. Alles aenderbar ohne Server-Neustart dank Hot-Reload."

---

### SZENE 3: Der LangGraph-Ablauf (0:55 - 1:20)
**[Zeige: Flussdiagramm / Animation des Graphen]**

> "Wenn ein Kunde schreibt, durchlaeuft seine Nachricht den LangGraph:
>
> Zuerst prueft der **Guardrail-Node** ob die Nachricht erlaubt ist -
> Beleidigungen oder Jailbreak-Versuche werden blockiert.
>
> Dann erkennt **classify_and_extract** in einem einzigen LLM-Aufruf
> was der Kunde will UND welche Bestelldaten er genannt hat.
> Das spart 50 Prozent API-Kosten.
>
> Jetzt kommt das Routing - die Conditional Edge im Graphen:
> Bei 'order' werden Daten gesammelt und fehlende Felder nachgefragt.
> Bei 'price' werden Dokumente per RAG durchsucht.
> Bei 'image' wird ein Vorschaubild generiert.
> Bei 'offtopic' wird hoeflich zurueck zum Thema gelenkt.
>
> Am Ende wird die Antwort zurueckgeschickt und der State in ChromaDB gespeichert."

---

### SZENE 4: ChromaDB - Das Gedaechtnis (1:20 - 1:40)
**[Zeige: ChromaDB-Diagramm mit zwei Schubladen]**

> "ChromaDB ist das Gedaechtnis des Systems - wie ein Aktenschrank mit zwei Schubladen.
>
> **Schublade 1: Sessions.**
> Hier wird der komplette AgentState jedes Kunden gespeichert -
> Chatverlauf, Bestelldaten und welche Fragen schon gestellt wurden.
> Das ist der Checkpointer im LangGraph-Muster - er macht den Agenten zustandslos,
> weil der State extern verwaltet wird.
> Nach 24 Stunden wird die Session automatisch geloescht.
>
> **Schublade 2: Wissensbasis fuer RAG.**
> Hier liegen Preislisten und Produktinfos als Zahlen-Vektoren.
> Wenn ein Kunde fragt 'Was kostet das?', sucht die KI den passenden Textabschnitt
> und antwortet mit echten Fakten statt zu halluzinieren.
>
> Abgeschlossene Bestellungen gehen in eine separate SQLite-Datenbank -
> die bleibt fuer immer."

---

### SZENE 5: Bildgenerierung + LangSmith (1:40 - 1:55)
**[Zeige: Referenzbild → Vision-Analyse → generiertes Bild → LangSmith-Dashboard]**

> "Das Besondere: die KI kann Bilder verstehen.
> Sie durchsucht das Referenzbilder-Portfolio, findet die beste Vorlage
> per GPT-4o Vision, beschreibt sie auf Englisch -
> und generiert ein neues Bild das Vorlage und Kundenwuensche kombiniert.
> Bei Figuren wie Elsa oder Ronaldo wird automatisch auf HuggingFace umgeschaltet.
>
> Alle diese Schritte werden ueber **LangSmith** getrackt -
> jeder Node, jeder LLM-Call und jede Bildgenerierung erscheint
> als Trace im LangSmith-Dashboard. Dazu gibt es 5 automatisierte Test-Suites
> die Guardrail, Intent-Erkennung, Extraktion, Bild-Prompts und Antwortqualitaet pruefen.
> So wird die Qualitaet der KI kontinuierlich ueberwacht."

---

### SZENE 6: Abschluss (1:55 - 2:00)
**[Zeige: Zusammenfassung mit allen Technologien]**

> "Fuenf Saeulen machen Kidstorte aus:
> RAG fuer Faktenwissen, ein selbst gebautes LangGraph-Muster fuer den Gespraechsfluss,
> ChromaDB als Session-Gedaechtnis, Multimodale Vision fuer die Bildgenerierung
> und LangSmith fuer Tracing, Monitoring und Evaluations.
> Das ist Kidstorte."

---

## Technische Stichpunkte fuer Einblendungen

| Zeitpunkt | Einblendung |
|-----------|-------------|
| 0:10 | `LangGraph-Prinzip: Nodes + Edges + State` |
| 0:20 | `main.py → graph.py → nodes.py` |
| 0:30 | `graph.py = CakeDreamsGraph (selbst gebautes LangGraph)` |
| 0:40 | `state.py = AgentState (TypedDict)` |
| 0:55 | `guardrail() → classify_and_extract() → Conditional Edge` |
| 1:05 | `Intent: greeting / order / price / image / info / offtopic` |
| 1:25 | `ChromaDB: sessions/ (Checkpointer) + cake_chunks/ (RAG)` |
| 1:32 | `Embedding: "Schoko 35EUR" → [0.23, -0.84, ...]` |
| 1:45 | `_find_best_reference() → gpt-image-1 / HuggingFace FLUX` |
| 1:50 | `LangSmith: @trace_node → Traces + Evals` |
| 1:55 | `RAG + LangGraph + ChromaDB + Vision + LangSmith` |
