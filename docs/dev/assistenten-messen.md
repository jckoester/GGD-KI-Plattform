# Schüler-Assistenten messen und ausliefern

Wie ein ausgelieferter Schüler-Assistent entsteht — Prompt, Szenarien, Messung, Seed — und wie
der Vorschlag im Chat vermessen wird (Päckchen C1, 10/2026). Muster sind die drei Assistenten
„stöchiometrische Berechnungen“, „Reaktionsgleichungen“ und „naturwissenschaftliche Aufgaben“.

## Bausteine

| Was | Wo |
|---|---|
| Prompt | `config/prompts/<name>_assistent.md` |
| Szenarien und Einrichtung | `backend/scripts/szenarien/<name>.yaml` — Kopf `assistent:` + `faelle:` |
| Messung im Chat | `backend/scripts/assistent_messung.py` (Hülle für Stöchiometrie: `stoechiometrie_messung.py`) |
| Auslieferung | `config/assistants.example.yaml` → `backend/scripts/seed_assistants.py` |
| Auslöser-Beispiele | Tabelle `assistant_trigger_examples`, gepflegt über API, Editor, YAML, Seed (`app/assistants/ausloeser.py`) |
| Prüfsatz Vorschlag | `backend/scripts/szenarien/assistent_vorschlag.yaml` → `assistent_vorschlag_messung.py` |

**Namensschema:** Der Name vervollständigt „Assistent für …“ („Reaktionsgleichungen“). Er ist
zugleich der Schlüssel von Seed und Messskript — nach dem Ausrollen nicht mehr ändern.

## Messen im Chat (`assistent_messung.py`)

```bash
cd backend
venv/bin/python scripts/assistent_messung.py --szenarien scripts/szenarien/reaktionsgleichung.yaml --selbsttest
venv/bin/uvicorn app.main:app --port 8001 &      # eigene Instanz, nicht production
venv/bin/python scripts/assistent_messung.py --szenarien scripts/szenarien/reaktionsgleichung.yaml \
    --basis http://localhost:8001 --konto <pseudonym-anfang> --lauf 1 --ziel "<Vault>/Plaene/Messungen-…"
```

Das Skript legt den Assistenten aus dem **Kopf der Szenariodatei** an oder bringt ihn auf den
Stand der Promptdatei (Name, Fach — `null` = fachübergreifend —, Klassenstufen, Modell,
abgeschaltete Augmentierungen), spielt jeden Fall als neue Konversation mit der Stufe des Falls
durch und schreibt ein Protokoll (`verlauf-<lauf>.md` zum Abhaken, `.json` zum Vergleichen). Die
Konversationen werden danach gelöscht.

Automatisch geprüft je Zug:

| Feld | Bedeutung |
|---|---|
| `verboten` (je Zug) | Werte, die die Schüler:in noch nicht genannt hat — **Vorgriff**. Normalisiert (LaTeX, mhchem, Dezimalkomma, Zahlen an Ziffergrenzen); der Selbsttest prüft das Instrument in beide Richtungen |
| `stufenfremd` (je Fall) | Begriffe, die in der Stufe noch nicht dran sind — **Stufenvorgriff**; ein Wort trifft seine Zusammensetzungen |
| `werkzeug` (je Zug, optional) | Soll-Werkzeug, z. B. `list_context_nodes`; Zusammenfassung „Operator nachgeschlagen: n von m“ |
| Kosten | Tokens und USD je Zug aus `messages` (wartet auf nachgetragene Kosten), Anteil des Prompts an den Eingabetokens (tiktoken) |

`muss`/`darf_nicht` prüft ein Mensch im Protokoll. Optionen: `--nur <fall>` (mehrfach), `--prompt`
(Variante außerhalb des Repos), `--ohne-augmentierung`, `--vorlauf <yaml>` (Standard-Chat-Züge
vorab, dann Wechsel zum Assistenten in derselben Konversation).

⚠️ **zsh teilt Variablen nicht an Leerzeichen.** `NUR="--nur A --nur B"; … $NUR` übergibt *ein*
Argument, und das Skript bricht ab. Mehrere `--nur` als bash-Array oder ausgeschrieben.

⚠️ **Budget des Schülerkontos.** Ein Lauf mit 25 Fällen und `chat-komplex` kostet etwa 0,40 USD.
Restbudget per LiteLLM `/user/info` prüfen, aufstocken über `/user/update` (`max_budget`).

Der Messkanal `vorab_debug` (nur außerhalb der Produktion) liefert dem Skript angebotene Knoten,
Suchanfragen und die Aufrufe von `list_context_nodes` (Filter, `gesamt`, `geliefert`).

## Was die Messungen gezeigt haben (10/2026)

- **`chat-komplex`, nicht `chat-standard`.** Mit dem Standardmodell hielt „nichts vorsagen“ nicht;
  alle drei Assistenten sind fest gebunden.
- **Stufen über die Plattform, nicht über den Prompt.** Die Zeile mit der Klassenstufe und die
  Fassungen der Fachbegriffe reichen (0 Stufenvorgriffe in 551 Zügen der Assistenten für Reaktionsgleichungen und naturwissenschaftliche Aufgaben); keine Stoffverteilung in
  den Prompt schreiben.
- **Ein Assistent statt mehrerer je Stufe.** Der Prompt macht etwa 30–45 % der Eingabetokens aus;
  ein Aufteilen spart wenig.
- **Werkzeuge im Prompt erzwingen kostet.** „Operator immer nachschlagen“ hob die Kosten je Zug um
  68 % ohne messbaren Gewinn; der Assistent für naturwissenschaftliche Aufgaben schlägt daher nur
  bei Unsicherheit nach.
- **Wissensfragen sind Aufgaben.** „Welche Oxidationszahl hat …?“ wird ohne ausdrückliche Regel
  beantwortet statt begleitet.

## Ausliefern (`seed_assistants.py`)

Ein Eintrag in `config/assistants.example.yaml` trägt alles, was die Messung eingestellt hat —
Fach, Klassenstufen, Modell, abgeschaltete Augmentierungen, Dokumente, `suggest`,
`suggestion_text`, Beispiele, Gegenbeispiele, Rückfälle (mit Namen). Ein Unit-Test
(`test_assistenten_seed_datei.py`) hält Seed und Szenariokopf gleich: **gemessen wird, was
ausgeliefert wird.**

Der Seed ist idempotent nach Name. Bei einem vorhandenen Assistenten trägt er nur nach, was fehlt:
Beispiele (samt `suggest`, Vorschlagstext), wenn er keine hat, und Rückfälle, wenn keine gesetzt
sind. Prompt, Modell und Dokumente fasst er nicht an.

## Auslöser-Beispiele und Vorschlag

**Beispiele** sind typische *erste* Nachrichten in Schülersprache (5–15), **Gegenbeispiele**
klingen ähnlich, gehören aber nicht zum Assistenten (Aufgaben des Nachbarn, Begriffsfragen). Die
ersten Züge der Messszenarien gehören **nicht** zu den Beispielen — sie sind der zurückgehaltene
Prüfsatz; ein Unit-Test hält das fest (`test_assistent_vorschlag_pruefsatz.py`).

Die Vektoren haben keine feste Breite; gültig ist ein Vektor nur zusammen mit `embedding_model`.
Nach einem Modellwechsel bettet der nächtliche `embedding_backfill.py` neu ein.

```bash
cd backend && venv/bin/python scripts/assistent_vorschlag_messung.py --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf 1
```

misst nur Embeddings (Bruchteile eines Cents): je Prüftext das beste Beispiel und das beste
Gegenbeispiel je Kandidat, tastet die Schwellen für spezifische und Rückfall-Assistenten (mit und
ohne Gegenbeispiel-Regel) gegen das Kriterium K1–K5 im Kopf des Prüfsatzes ab und meldet
Fast-Dubletten (< 0,20 zu einem eingebetteten Text). **Stand 27.10.2026:** spezifisch nur in einem
Fenster von 0,01 erfüllt, Rückfall gar nicht — der Vorschlag (Päckchen C2) wird Embeddings als
Vorfilter und einen Klassifikator-Aufruf im Band kombinieren.
