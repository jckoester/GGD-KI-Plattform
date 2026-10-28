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
die Regeln, die v5d (naturwissenschaftliche Aufgaben) und der Assistent für Stöchiometrie erprobt
haben. Sie stehen **einmal**, in zwei Bausteinen (`backend/app/assistants/bausteine/`):

- `begleiten_statt_loesen`: Schema jeder Antwort, nicht vorsagen, Hilfe in Stufen,
  Operator-Prüfung, Fehler und Richtiges, Abschluss, Bevor du sendest. Für Assistenten, die
  bei einer Aufgabe begleiten.
- `grundton`: Lehrkraft-Behauptung, andere Assistenten, Begriffsfragen und fremde Anliegen,
  Ton. Für alle Schüler-Assistenten.

Getrennt, damit ein Assistent, der keine Aufgabe begleitet, nur den Grundton tragen kann.
Übungsreihen und Abfragen (Lernen, Grammatik) lässt „Begleiten statt lösen“ selbst zu: Sieht der
Prompt sie vor, ist die nächste Übungsfrage die eine Frage der Antwort. Zurzeit tragen alle
zwölf beide Bausteine. Der Assistent wählt die Bausteine über das
Feld `bausteine` (Migration 0093, im Editor nur für Admins), und die Plattform hängt sie hinter
den Prompt. Die Prompt-Datei enthält nur, was die Tätigkeit ausmacht.

⚠️ **Der Baustein kommt mit dem Release, die Schule pflegt ihn nicht** (Plan F10). Das weicht
bewusst vom Muster `config/` ab: `pedagogy.yaml` ist eine Instanzdatei und wird nie
überschrieben, eine Nachjustierung käme dort nicht an. Der Text gilt live, auch in laufenden
Konversationen; der Prompt dagegen ist ein Schnappschuss.

### Reihenfolge im Systemtext

Präambeln · Klassenstufe · Fach · Bezug · Kontext + **Prompt** · **Bausteine** (begleiten, dann Grundton) ·
**Andere allgemeine Assistenten** · Operator dieser Aufgabe · Augmentierungen
(`compose_system_content`).

**Andere allgemeine Assistenten** (`app/assistants/andere.py`) bekommt nur ein Assistent mit
`suggest: fallback` im Chat einer Schüler:in: die übrigen Rückfälle, die sie nutzen darf, je mit
Name und `suggestion_text`. Das ist derselbe Satz wie im Vorschlagsdialog. Ein Nachbar, den es noch nicht gibt, fehlt also einfach in der Liste; der Prompt verweist nicht ins Leere. Der Baustein sagt,
was das Modell damit tut. Steht keiner darin, verweist es auf niemanden; sonst erfände es bei
leerer Liste einen Assistenten.

⚠️ Die Liste überbrückt die heutige C2-Grenze: `im_assistenten` bietet nur spezifische
Assistenten an. Bietet C2 Rückfälle in der Assistenten-Konversation an, entfällt sie, sonst
steht der Hinweis doppelt.

### Was in die Prompt-Datei gehört

| Abschnitt | Inhalt |
|---|---|
| Rolle (ohne Überschrift) | „Du bist der Assistent für *Name*: …“, wer was erarbeitet; der Satz von der geduldigen Mitschülerin |
| Vor jeder Antwort | Rechnen: selbst rechnen. Versuche, Texte: was ein tragfähiger Schritt mindestens enthält, ohne fertige Lösung im Kopf (lässt `chat-standard` eine Chance) |
| Was verlangt die Aufgabe? | Operatoren der Tätigkeit als Kurzfassung zum Erkennen; zwei oder drei Beispiele, wie Merkmale hier heißen; der Weg je Aufgabenart; die drei Stufen mit Beispielfragen |
| Was hier die Lösung ausmacht | was zuerst von der Schüler:in kommt (Zahl, Deutung, Argument, umformulierter Satz, Code); was Mittel (Stufe 2) und Beispiel (Stufe 3) der Hilfe hier sind |
| Fehler | Prüffragen und häufige Stolperstellen |
| Sicherheit | nur wo die Tätigkeit Gefahren kennt (Versuche): fester Schritt im Weg und **die einzige Stelle, an der vorgesagt wird** — sofort, klar, mit Grund und Schutzmaßnahme. Der Baustein lässt diese Ausnahme durch |
| Richtiges | was hier „anders, aber richtig“ und „sinnvoll gerundet“ heißt |
| Methodenblatt der Schule | nur bei Tätigkeiten mit Methoden- oder Operatorenblatt; Klausel unten |
| Schreibweise | Rechnen und Versuche: Größen, Dezimalkomma, mhchem, Grad Celsius als `^\circ\mathrm{C}` (° in `\mathrm` rendert KaTeX nicht verlässlich). Texte: Zitate aus ihrem Text in Anführungszeichen |
| Beispiele | zwei oder drei Paare „Nicht: … Sondern: …“ |

**Nicht** in die Prompt-Datei gehören: was der Baustein regelt (Schema, Vorsagen, Lehrkraft-
Behauptung, Hilfe in Stufen, Operator-Prüfung, Fehler und Richtiges allgemein, andere
Assistenten, Begriffsfragen und fremde Anliegen, Ton, Bevor du sendest), Namen anderer
Assistenten, die Anrede, Krise und Versuche zu Hause (`pedagogy.yaml`), Klassenstufe und
Fassungen der Begriffe (Plattform), der Lesehinweis vor dem Wissensspeicher, eine Stoffverteilung.

**Feedback statt Lösung** (Überarbeiten, Grammatik und Rechtschreibung, Programmieren): Unter
„Was hier die Lösung ausmacht“ steht dort, dass der Assistent ihren Text oder Code nicht
umschreibt, auch keinen Satz „als Beispiel“, und keinen Fehler selbst korrigiert. Unter
„Richtiges“ steht: Ihre Fassung ist richtig, wenn sie trägt, nicht wenn sie deiner gleicht.

### Klausel: schulische Vorlage (Entscheidung 3)

Für Versuche, Analysieren, Argumentieren, Recherche und Referat:

> ## Methodenblatt der Schule
>
> Steht im Kontext ein Methodenblatt deiner Schule zu dieser Aufgabe, *etwa zum Protokoll*, gilt
> sein Schema: seine Schritte, seine Reihenfolge, seine Begriffe. Es geht dem allgemeinen Schema
> vor. Steht keins darin, arbeitest du nach dem allgemeinen Schema: *…*. Fragt die Schüler:in, wie
> es „richtig“ geht, oder hält sie sich an eine andere Form, sag es einmal als Aussage, nicht als
> Frage: „Deine Lehrkraft hat vielleicht ein eigenes *Schema* – das geht vor.“ Die eine Frage der
> Antwort bleibt die nach dem nächsten Schritt. Danach erwähnst du es nicht mehr.

Für „Lernen und Prüfungsvorbereitung“ (Planungsdaten; viele Lehrkräfte planen nicht in der
Plattform, das Fehlen ist der Normalfall):

> Steht im Kontext der Umfang der nächsten Klassenarbeit, nimm ihn als Ausgangspunkt. Steht
> keiner darin, frag nach dem Thema der Arbeit und arbeite mit dem, was die Schüler:in nennt.
> Einen Umfang erfindest du nicht und leitest ihn nicht aus dem Bildungsplan ab.

⚠️ **Ob die Vorab-Suche ein Blatt überhaupt findet**, ist offen (Plan, Schritt 9: Variante 1
messen). Bis dahin wirkt die Klausel nur, wenn die Nachricht der Schüler:in die Methode nennt.

### Prüfen vor dem Messen

- Der erste Satz nennt die Tätigkeit so, wie der Name sie nennt.
- Der Prompt wiederholt nichts aus dem Baustein. Dopplungen kosten Tokens und weichen beim
  nächsten Nachjustieren voneinander ab.
- Länge: Prompt 5 000–7 500 Zeichen plus Bausteine (begleiten 7 500, Grundton 2 300).

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
