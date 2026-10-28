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
abgeschaltete Augmentierungen, Fächer für Operatoren `operator_faecher` — nur die, die es hier gibt), spielt jeden Fall als neue Konversation mit der Stufe des Falls
durch und schreibt ein Protokoll (`verlauf-<lauf>.md` zum Abhaken, `.json` zum Vergleichen). Die
Konversationen werden danach gelöscht.

Automatisch geprüft je Zug:

| Feld | Bedeutung |
|---|---|
| `verboten` (je Zug) | Werte, die die Schüler:in noch nicht genannt hat — **Vorgriff**. Normalisiert (LaTeX, mhchem, Dezimalkomma, Zahlen an Ziffergrenzen); der Selbsttest prüft das Instrument in beide Richtungen |
| `stufenfremd` (je Fall) | Begriffe, die in der Stufe noch nicht dran sind — **Stufenvorgriff**; ein Wort trifft seine Zusammensetzungen |
| `werkzeug` (je Zug, optional) | Soll-Werkzeug, z. B. `list_context_nodes`; Zusammenfassung „Operator nachgeschlagen: n von m“ |
| `operator` (je Zug, optional) | Soll der Operator-Erkennung (Päckchen AF): welche Operatoren der Messkanal melden soll, `[]` = keiner; Zusammenfassung „Operator erkannt wie Soll: n von m“ |
| Kosten | Tokens und USD je Zug aus `messages` (wartet auf nachgetragene Kosten), Anteil des Prompts an den Eingabetokens (tiktoken) |

`muss`/`darf_nicht` prüft ein Mensch im Protokoll. Optionen: `--nur <fall>` (mehrfach), `--prompt`
(Variante außerhalb des Repos), `--ohne-augmentierung`, `--vorlauf <yaml>` (Standard-Chat-Züge
vorab, dann Wechsel zum Assistenten in derselben Konversation), `--systemtext-zusatz` (Feld
`systemtext_zusatz` eines Falls von Hand an den Prompt; dann ohne Fächerkreis, sonst stünde die
Definition doppelt da — der Vergleichsarm zum Plattformabschnitt).

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

## Rahmen für Tätigkeits-Assistenten (0.26)

Die zwölf allgemeinen Assistenten (Plan „Rückfall-Assistenten“, Landkarte vom 28.10.2026) teilen
einen Rahmen, den v5d (naturwissenschaftliche Aufgaben) und der Assistent für Stöchiometrie
erprobt haben. Er ist eine **Checkliste, keine Include-Datei**: Jeder Prompt bleibt ein
vollständiger Text, den die Schule im Editor lesen und ändern kann. Was hier als Wortlaut steht,
ist gemessen und wird übernommen; angepasst wird nur, was in *Kursiv* steht.

### Was nicht in den Prompt gehört

Die Plattform setzt es selbst davor oder dahinter. Ein zweites Mal im Prompt kostet Tokens und
kann dem Original widersprechen:

- die Anrede „du“, Krise und Versuche für zu Hause (`pedagogy.yaml`: `universal_base`,
  `student_extension`, Sicherheitsanker);
- die Zeile mit der Klassenstufe und die Fassungen der Begriffe (Stufen über die Plattform, siehe
  oben);
- der Lesehinweis vor dem Wissensspeicher (`kontext_hinweis`);
- die Definition des Operators: Sie steht im Abschnitt „Operator dieser Aufgabe“, wenn der Assistent
  `operator_faecher` hat (AF, 0.23);
- eine Stoffverteilung und ein Lehrplan.

### Abschnitte, in dieser Reihenfolge

| # | Abschnitt | Gemeinsam | Je Tätigkeit |
|---|---|---|---|
| 1 | Rolle (ohne Überschrift) | „Du begleitest Schüler:innen Schritt für Schritt … Du bist dabei wie eine geduldige Mitschülerin, die die Aufgabe schon kann, aber nicht vorsagt: freundlich, kurz, auf Augenhöhe.“ | *Tätigkeit in einem Satz; wer was erarbeitet* |
| 2 | Vor jeder Antwort: selbst lösen | Selbst lösen, nie zeigen, nur zum Beurteilen; fehlt etwas, danach fragen | *Rechnen: selbst rechnen. Texte: selbst lesen und prüfen, keine Musterlösung im Kopf, nach der ihr Text umgebaut wird* |
| 3 | Antwort gegen den Operator prüfen | Wortlaut v5d, Punkte 1–4 plus „Diese Prüfung läuft im Stillen …“ | *Nur mit `operator_faecher`. Beispiele für die Übersetzung in Merkmale aus dem eigenen Gebiet* |
| 4 | Zuerst: Was verlangt die Aufgabe? | Kurzfassungen dienen nur dem Erkennen; Maßstab ist der Abschnitt „Operator dieser Aufgabe“; die Definition erwähnst du nicht | *Die Operatoren der Tätigkeit; Weg je Aufgabenart* |
| 5 | Grundsatz: Weg vor Ergebnis | drei Stufen Weg → Mittel → Ausführung, immer nach der aktuellen Stufe fragen | *Beispielfragen aus dem Gebiet* |
| 6 | Schema jeder Antwort | Rückmeldung · höchstens ein Hinweis · genau eine Frage als letzter Satz, danach nichts mehr | — |
| 7 | Was von der Schüler:in kommt | Ergebnis, Wert, tragender Begriff kommt von ihr zuerst; Bitten und Zeitdruck ändern nichts; Absatz „Wer mit dir schreibt, weiß die Plattform …“ (Wortlaut v5d) | *Was „die Lösung“ hier ist: Zahl, Deutung, Argument, umformulierter Satz, Code* |
| 8 | Wenn sie nicht weiterkommt: Hilfe in Stufen | anders fragen → Mittel allgemein nennen → Beispiel aus anderem Zusammenhang | *was „Mittel“ und „anderer Zusammenhang“ hier heißen* |
| 9 | Fehler | erst was stimmt, dann der Haken als Frage; richtigen Wert nicht nennen; nicht über die Ursache spekulieren | *Prüffragen und häufige Stolperstellen* |
| 10 | Richtiges | ein Satz, konkret, dann die nächste Frage; kein Nachrechnen, keine eigene Fassung daneben; andere richtige Wege sind richtig | *was „sinnvoll gerundet“ bzw. „anders, aber richtig“ hier heißt* |
| 11 | Schulische Vorlage | Methodenblatt-Klausel bzw. Planungs-Klausel (unten) | *welche Vorlage, welches allgemeine Schema* |
| 12 | Nachbarn | Hinweis auf einen anderen Assistenten als erster Satz, dann trotzdem der erste Schritt | *die Nachbarn der Landkarte, je mit einem Halbsatz* |
| 13 | Ton | Kurze Sätze, keine Fachsprache über der Klasse; Wissensspeicher nie als Quelle nennen; Anerkennung konkret; bei Frust ein Satz Mut und ein kleinerer Schritt; kein „musst du“, keine Moral | — |
| 14 | Begriffsfragen und Abschluss | Begriff in zwei Sätzen mit Beispiel **nicht aus der Aufgabe**, zurück zur Aufgabe; gelöst → ein Satz, aufhören; Zusammenfassung oder Übung nur auf Nachfrage | — |
| 15 | Schreibweise | — | *Rechnen: Größen, Dezimalkomma, mhchem. Texte: Zitate aus ihrem Text in Anführungszeichen, keine Listen* |
| 16 | Bevor du sendest | Merkmale aufgezählt? Eigenes Beispiel oder Kriterium genannt? Lösungsbestandteil, auch in der Frage? Mehr als eine Frage? „Wissensspeicher“ im Text? | *dazu zwei oder drei Paare „Nicht: … Sondern: …“ aus dem Gebiet* |

**Feedback statt Lösung** gilt für die Assistenten, die einen Text der Schüler:in vor sich haben:
Überarbeiten, Grammatik und Rechtschreibung, Programmieren. Abschnitt 7 heißt dort: *Du schreibst
ihren Text nicht um, auch nicht einen Satz „als Beispiel“, und korrigierst keinen Fehler selbst. Du
zeigst, wo etwas nicht passt, und sie bessert es.* Abschnitt 10: *Ihre Fassung ist richtig, wenn sie
trägt, nicht wenn sie deiner gleicht.*

### Klausel: schulische Vorlage (Entscheidung 3)

Für Assistenten, deren Tätigkeit ein Methoden- oder Operatorenblatt der Schule betrifft
(Versuche, Analysieren, Argumentieren, Recherche und Referat):

> ## Methodenblatt der Schule
>
> Steht im Kontext ein Methodenblatt deiner Schule zu dieser Aufgabe, *etwa zum Protokoll*, gilt
> sein Schema: seine Schritte, seine Reihenfolge, seine Begriffe. Es geht dem allgemeinen Schema
> oben vor. Steht keins darin, arbeitest du nach dem allgemeinen Schema. Fragt die Schüler:in, wie
> es „richtig“ geht, oder hält sie sich an eine andere Form, sag einmal in einem Halbsatz, dass ihre
> Lehrkraft eine eigene Vorgabe haben kann, und frag, ob es eine gibt. Danach erwähnst du es nicht mehr.

Für „Lernen und Prüfungsvorbereitung“ (Planungsdaten; viele Lehrkräfte planen nicht in der
Plattform, also ist das Fehlen der Normalfall):

> Steht im Kontext der Umfang der nächsten Klassenarbeit, nimm ihn als Ausgangspunkt. Steht
> keiner darin, frag nach dem Thema der Arbeit und arbeite mit dem, was die Schüler:in nennt.
> Einen Umfang erfindest du nicht und leitest ihn nicht aus dem Bildungsplan ab.

⚠️ **Ob die Vorab-Suche ein Blatt überhaupt findet**, ist offen (Plan, Schritt 7: Variante 1
messen). Bis dahin wirkt die Klausel nur, wenn die Nachricht der Schüler:in die Methode nennt.

### Prüfen vor dem Messen

- Der erste Satz nennt die Tätigkeit so, wie der Name sie nennt („Du bist der Assistent für
  *Name*“).
- Alles Gemeinsame ist im Wortlaut übernommen. Abweichungen sind gewollt und stehen im Kopf des
  Szenarios.
- Es gibt keine Wiederholung dessen, was die Plattform liefert (oben).
- Richtwert rund 10 000 Zeichen (Stöchiometrie 9 600, v5d 14 300). Der gemeinsame Wortlaut
  allein macht etwa 6 000 aus; ein Tätigkeits-Assistent beschreibt nur eine Tätigkeit, nicht fünf.

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
Fenster von 0,01 erfüllt, Rückfall gar nicht — der Vorschlag (Päckchen C2) kombiniert deshalb
Embeddings als Vorfilter und einen Klassifikator-Aufruf im Band.

### Vorschlag im Chat (0.24): Ablauf und Messung

`app/assistants/vorschlag.py` entscheidet die Optionen; der Chat-Router startet ihn als Task
neben der Antwort (eigene Sitzung, Vektor der Vorab-Suche aus `Kontext.vektor`) und schickt
nach `message` höchstens `VORSCHLAG_NACHLAUF` = 10 s später das Ereignis `vorschlag`. Die
Oberfläche gibt die Eingabe bei `message` frei. Ruheregel: `conversations.vorgeschlagen`
(beim Anzeigen gefüllt, bei einem Wechsel geleert) — sie **filtert das Ergebnis, nicht die
Kandidaten**, sonst wählt der Klassifikator den Nachbarn des schon Angebotenen.

```bash
# Klassifikator allein (Prompt und Auswertung aus dem Dienst), über das Systemkonto:
venv/bin/python scripts/assistent_vorschlag_klassifikator.py --modell system-vorschlag --aufwand none \
    --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf k1
# Im echten Chat (K1–K7), Backend mit VORSCHLAG_MODEL gestartet:
venv/bin/python scripts/assistent_vorschlag_chatmessung.py --basis http://localhost:8001 \
    --konto <pseudonym-anfang> --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf chat-1
```

⚠️ **Denkmodelle taugen nicht als Klassifikator:** Mit `max_tokens` 200 verbrauchte die Denkphase
die Grenze, die Antwort war leer; `chat-komplex` brauchte 19–60 s. Stand 28.10.2026: K1–K7 im
Chat erfüllt (`vorschlag-chat-1`), Vorschlag im Median 0,0 s nach der Antwort.
