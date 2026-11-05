# Rückmeldungen sichten

Die Plattform hat einen eigenen Rückkanal: Schüler:innen und Lehrkräfte melden Fehler
und Vorschläge aus der Anwendung heraus, die Administration sichtet sie unter
**`/feedback/manage`**. Grundlage ist ADR-020.

Diese Seite beschreibt die Triage — also die Handarbeit, die den Wert des Kanals
ausmacht —, die **bekannten Probleme** (seit 0.31) und die Auswertung der **Daumen** an
den Antworten (seit 0.31).

## Was eine Meldung enthält

- **Pseudonym und Rolle** — mehr Identität gibt es nicht.
- **Freitext**, Kategorie (Fehler · Vorschlag · Sonstiges) und der technische Kontext
  (Version, Seite, Browser, Fenstergröße; aus dem Chat auch Assistent und **Modell** der
  letzten Antwort, seit 0.28.1). Das Modell steht als Alias mit dem Anbietermodell dahinter,
  etwa „chat-komplex (openai/gpt-oss-120b)“: Der Alias zeigt, was die Schule eingestellt hat,
  das Anbietermodell, was tatsächlich geantwortet hat. Es wird ohne Einwilligung erfasst, weil
  es weder Inhalt noch Personenbezug trägt; den Chat selbst gibt es weiterhin nur als Anhang.
  Ältere Meldungen haben kein Modell.
- **Aus der Vorschau** (seit 0.29): Eine Lehrkraft hat die Meldung im Vorschaumodus
  geschrieben, also beim Ansehen der Plattform als Schüler:in. In der Liste steht dann „aus der
  Vorschau“; als Rolle steht ihre echte Rolle da, nicht „Schüler:in“.
- **Kontaktangabe**, falls die meldende Person freiwillig eine gemacht hat.
- **Chat-Kopie**, falls sie ausdrücklich angehängt wurde. Sie wird erst beim Aufklappen
  geladen und nennt bei jeder Antwort das Modell.

Der Freitext läuft **nicht** durch Guardrails oder die Krisenerkennung — er ist keine
Modelleingabe. Das ist eine bewusste Lücke, siehe unten.

## Der Weg einer Meldung

1. **Sichten.** Was Arbeit macht, steht standardmäßig oben: offen und in Bearbeitung.
   Die Zähler an den Filterknöpfen zeigen den Gesamtstand je Status.
2. **Bündeln.** Mehrere Meldungen zum selben Thema bekommen dieselbe
   **Issue-Referenz** und wechseln gemeinsam den Status. Die Referenz ist Freitext
   (`#142` oder eine URL) und erscheint **nicht** bei den Meldenden.
3. **Ein Issue anlegen** — nur für technische Befunde und nur mit *eigenen* Worten.
   Nutzertexte gehören nicht in einen öffentlichen Tracker: Sie können Namen Dritter,
   Klassenbezüge oder Chatinhalte enthalten. Was an der Konfiguration der eigenen
   Schule liegt (Assistenten, Inhalte, Einrichtung), bleibt hier und erreicht das
   Projekt gar nicht — richtig so.
4. **Abschließen.** `Erledigt` mit Angabe der Version, `Nicht umgesetzt` mit einer
   kurzen Begründung (Pflichtfeld), `Spam` bei Missbrauch.

## Was die Meldenden sehen

| Status | Anzeige unter „Meine Meldungen" |
|---|---|
| `open` | Offen — zurückziehbar |
| `in_progress` | In Bearbeitung — nicht mehr zurückziehbar |
| `done` | Erledigt in *Version* |
| `declined` | Nicht umgesetzt, **mit** Begründung |
| `spam` | Nicht umgesetzt, **ohne** Begründung |

Die kurze Antwort erscheint dort ebenfalls. Antworten können die Meldenden nicht — der
Kanal ist bewusst eine Einbahnstraße. Wer eine Rückfrage stellen will, braucht eine
Kontaktangabe (s. u.) oder spricht die Person an.

**Wiedereröffnen** geht aus jedem abgeschlossenen Zustand zurück nach `open`. Ein
direkter Sprung zwischen abgeschlossenen Zuständen wird abgelehnt — er liefe am
Wiedereröffnen vorbei und verstellte den Zeitpunkt, ab dem die Löschfrist läuft.

## Bekannte Probleme (seit 0.31)

Eine Meldung lässt sich als **bekanntes Problem** zeigen: In der aufgeklappten Meldung wählen
Sie „Für alle sichtbar" oder „Nur für Lehrkräfte sichtbar" und geben einen **öffentlichen
Titel** ein (höchstens 200 Zeichen). Der Eintrag erscheint dann

- im Feedback-Formular als „Schon bekannt" — dort, wo eine Doppelmeldung entsteht,
- und unter „Feedback & Neuigkeiten" im Nutzermenü,

mit dem Stand **Bekannt** (offen), **Wird bearbeitet** oder **Behoben in *Version***. Nach
`Erledigt` bleibt er **30 Tage** stehen und verschwindet dann von selbst. In der Liste der
Sichtung tragen öffentliche Meldungen das Abzeichen „Bekannt".

Öffentlich ist **nur der Titel**, den Sie schreiben — nie der Text der Meldung, nie
Kategorie, Rolle, Version oder wer gemeldet hat. Formulieren Sie ihn deshalb selbst und ohne
Namen, Klassen oder Zitate aus der Meldung, etwa „Formeln im PDF-Export verrutschen".

- **Zielgruppe:** „Nur für Lehrkräfte" für alles, was Schüler:innen nicht betrifft oder nicht
  kennen (Planung, Assistenten-Editor, Werkstatt). Die Entscheidung trifft bewusst der
  Mensch, nicht die Plattform.
- **Mehrere Meldungen zum selben Problem:** nur **eine** öffentlich zeigen; die übrigen
  bündeln Sie wie gewohnt über die Issue-Referenz.
- **Abgelehnt oder Spam:** Solche Meldungen erscheinen nie als bekanntes Problem. Wer eine
  öffentliche Meldung ablehnt, nimmt sie damit aus der Liste; der Titel bleibt für ein
  späteres Wiedereröffnen gespeichert.
- **Zurücknehmen:** „Nicht öffentlich" wählen und speichern.

Zeigen und Zurücknehmen stehen im **Audit-Log** (`feedback_public_changed`, mit alter und neuer
Zielgruppe, ohne Titel).

## Antwortbewertung auswerten (seit 0.31)

Unter jeder Antwort im Chat setzen Nutzer:innen Daumen hoch („hilfreich") oder runter („nicht
hilfreich"). Das ist ein **zweiter Kanal** neben den Meldungen (ADR-020): kein Fehlerbericht,
sondern ein Qualitätssignal für die Konfiguration von Assistenten und die Modellwahl.

Ausgewertet wird unter **`/statistics/ratings`** (Rollen `admin` und `statistics`):

- **Je Assistent oder je Modell**, getrennt nach Schüler:innen und Lehrkräften (Admins zählen
  als Lehrkräfte): Daumen hoch, runter und der **Anteil „hilfreich"**. Den Anteil zeigt die
  Seite erst ab **10 Bewertungen** — darunter wäre er Zufall. „Ohne Assistent" sind Chats ohne
  Assistenten.
- **Je Woche** der Verlauf mit einer Summe für den Zeitraum; die Tabelle lässt sich als CSV
  herunterladen.

Lesehilfen:

- Gezählt wird in der Woche der **ersten** Bewertung einer Antwort. Wer sich später
  umentscheidet, ändert diese Woche, nicht die aktuelle.
- Test-Chats im Assistenten-Editor und Vorschau-Chats tragen keine Daumen und zählen nicht.
- Wenige Bewertungen sind normal: Die meisten Antworten bewertet niemand. Aussagekräftig ist
  der Vergleich zwischen Assistenten oder Modellen über einige Wochen, nicht die einzelne Zahl.
- Ein auffällig niedriger Anteil ist ein Anlass, sich den Assistenten anzusehen — mit einer
  eigenen Probe oder über Meldungen mit angehängtem Chat. Die Bewertungen selbst verweisen auf
  keinen Chat.

**Lehrkräfte sehen ihre eigenen Assistenten** (seit 0.33): Im Editor unter „So kommt er an"
und als Spalte in „Meine Assistenten" — nur die **Gesamtsumme** seit Bestehen, getrennt nach
Schüler:innen und Lehrkräften, und erst ab **10 Bewertungen je Rolle**. Darunter liefert der
Server weder Zahl noch Anteil: In einer kleinen Gruppe wäre schon „1 Daumen runter" eine
Aussage über eine bestimmte Schüler:in. Kein Wochenverlauf aus demselben Grund. Sehen kann es
nur, wer den Assistenten angelegt hat (wie das Bearbeitungsrecht); Kolleg:innen, die einen
geteilten Assistenten nur benutzen, sehen nichts. Die Zahlen der mitgelieferten Assistenten
stehen nur hier unter `/statistics/ratings`.

Die Zahlen enthalten **keine Personen und keine Chats**; sie bleiben auch nach dem Löschen der
Chats erhalten. Zeilen eines gelöschten Assistenten verschwinden mit ihm. Einzelheiten:
[Datenschutz im Betrieb](datenschutz-betrieb.md#antwortbewertung-seit-031).

## Zweckbindung der Kontaktangabe

Das Kontaktfeld ist freiwillig und **selbst eingegeben** — es ist die einzige Spalte im
System, in der Pseudonym und Klarname in einer Zeile stehen können. Daraus folgt:

- Die Angabe dient **ausschließlich** Rückfragen zu *dieser einen* Meldung.
- Sie ist **keine** Grundlage für Einsicht in Chats, für Nachforschungen oder für eine
  Kontaktaufnahme zu anderen Zwecken.
- Beim Abschluss der Meldung wird sie automatisch gelöscht — ohne Behalten-Option.

## Abgrenzung zur 4-Augen-Einsicht

Ein angehängter Chat ist eine **vom Opt-in gedeckte Kopie**, die die meldende Person
selbst mitgeschickt hat. Das ist etwas anderes als die Einsichtnahme nach
ADR-008: Die verlangt Antrag, Zweitfreigabe
und Protokollierung.

Wichtig ist die Richtung: Der Anhang berechtigt **nicht** zu weiterer Einsicht. Wer
aufgrund eines Anhangs mehr sehen möchte — andere Chats derselben Person, den weiteren
Verlauf —, geht den regulären Weg über
[Krisen-Einsicht](content-moderation.md), oder gar nicht.

Beim Abschluss wird die Kopie gelöscht. **„Angehängten Chat behalten"** gibt es für den
Fall, dass ein Fehler noch nicht behoben ist und der Verlauf zur Reproduktion gebraucht
wird; die Zusatzfrist ist dann die 180-Tage-Frist der Meldung.

## Krisenandeutung im Freitext

Der Freitext läuft nicht durch die Krisenerkennung. Deutet jemand darin eine Notlage an,
erreicht sie also **den Menschen, nicht die Pipeline** — und das ist der eigentliche
Grund, warum der Eingang regelmäßig gesichtet gehört.

Wenn das passiert:

1. Die Meldung **nicht** als Spam abtun und nicht vorschnell abschließen.
2. Den Krisenprozess der Schule anwenden, wie in
   [Content-Moderation & Guardrails](content-moderation.md) beschrieben — persönlich,
   nicht über den Statuswechsel.
3. Erst danach den Eintrag abschließen. Beachten: Beim Abschluss fallen Kontaktangabe
   und Anhang.

## Benachrichtigung

`FEEDBACK_NOTIFY_TO` in der `.env` (Liste von Adressen). Höchstens **eine Mail pro
Stunde**, ausgelöst von der ersten Meldung im Fenster; sie nennt Kategorie, Rolle,
Version und die ersten 200 Zeichen — **nicht** Pseudonym, Kontaktangabe oder Anhang.
Leer heißt: keine Mail. Das ist ein zulässiger Betriebszustand; der Eingang ist in der
Oberfläche sichtbar, und niemand wartet darauf.

Ist die Liste gesetzt, aber SMTP nicht konfiguriert, meldet das bereits die
Startprüfung.

## Missbrauchsschutz

Fünf Meldungen pro Stunde und zwanzig pro Tag je Pseudonym, Mindestlänge 20 Zeichen.
Drei als **Spam** markierte Meldungen innerhalb von 30 Tagen sperren das Pseudonym für
**14 Tage** ab dem jüngsten Eintrag; die Sperre läuft von selbst ab. Wer eine Meldung
versehentlich als Spam markiert hat, nimmt die Markierung zurück (wiedereröffnen, dann
neu setzen) — die Sperre folgt dem Datenbestand und löst sich damit auf.

## Löschfristen

| Zustand | Löschung |
|---|---|
| `done`, `declined`, `spam` | 180 Tage nach dem Statuswechsel, samt Anhang |
| `open`, `in_progress` | keine — ab 365 Tagen meldet der nächtliche Lauf sie als Warnung |
| Kontaktangabe | beim Abschluss, immer |
| Chat-Anhang | beim Abschluss, außer „behalten" |
| bei Kontolöschung | Eintrag bleibt, Pseudonym und Kontakt werden geleert |

Der Löschlauf ist `scripts/cleanup_feedback.py` (nächtlich, 02:50 Uhr).
`--dry-run` zählt nur.

Die Warnung „*n* Rückmeldung(en) sind seit über 365 Tagen offen" im Cron-Log ist kein
Fehler, sondern eine Aufforderung: abschließen oder bewusst behalten.
