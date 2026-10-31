# Antworten der Assistenten verbessern

Diese Seite richtet sich an die Schule: die Administration und die Verantwortlichen für die
Plattform. Sie beantwortet die Frage, **wie die Antworten der Assistenten an Ihrer Schule
besser werden**. Die Hinweise für Lehrkräfte stehen in der Hilfe unter
[Bessere Antworten](../user/bessere-antworten.md). Diese Seite ergänzt, was nur die
Schule einstellen kann.

Kurz gesagt: Die mitgelieferten Assistenten sind allgemein. Genauer werden sie durch das
Modell, durch Schulinhalt im Wissensspeicher und durch speziellere Assistenten. Die Prompts
und Bausteine selbst anzupassen bringt am wenigsten.

## 1. Das Modell

Die zwölf allgemeinen Schüler-Assistenten laufen auf `chat-komplex`. Ihre Zusagen sind an
wenigen Modellen gemessen: kein Ergebnis vorab, kein Nachgeben unter Druck, nichts erfunden.
**Dass ein anderes Modell sie ebenso hält, lässt sich daraus nicht schließen.** Die Plattform
verspricht es nicht.

- Schalten Sie `chat-komplex` unter `/settings/models` für die Jahrgänge 5 bis 13 frei
  (siehe CHANGELOG, „Nach dem Update“).
- Welches Modell hinter dem Alias steht, entscheidet die Schule (siehe
  [Vor der Installation](vor-der-installation.md)). Prüfen Sie vor dem Einsatz und nach jedem
  Wechsel selbst, ob das Modell die Zusagen hält: mit Gesprächen, in denen eine Schüler:in
  um die Lösung bittet, nachsetzt oder einen falschen Schritt schickt. Der Vorschaumodus
  zeigt das Verhalten gegenüber Schüler:innen.

## 2. Schulinhalt in den Wissensspeicher

Die Plattform liefert keine Fachbegriffe und keine Methodenblätter mit. Was die Vorab-Suche
nicht findet, ersetzt das Modell durch allgemeines Wissen.

| Inhalt | Wirkung | Wo |
|---|---|---|
| **Fachbegriffe** und Stoffsteckbriefe | Der Assistent erklärt und fragt in der Sprache der Fachschaft, auf dem Stand der Klasse | Fachseite → „weiterer Kontext“; für alle Fächer auf einmal `/settings/fachbegriffe` |
| **Methodenblätter** | Das Schema der Schule geht dem allgemeinen vor (Protokoll, Erörterung, Gedichtanalyse) | Sammlung „Methodenblätter“ |
| **Konventionen** | Zitierweise, Bezeichnungen, Protokollform schulweit | Fachseite → „weiterer Kontext“, Bausteinart „Konvention“; schulweit mit `write_scope=school` |
| **Stundenentwürfe mit Fachbegriffen** | Chats mit Gruppenbezug kennen die Begriffe, die die Gruppe schon hatte | Unterrichtsplanung der Lehrkräfte |

**Was die Messung zu Methodenblättern sagt** (drei Testblätter, 18 Schülernachrichten,
10/2026):

- Nennt die Nachricht die Methode, findet die Vorab-Suche das Blatt in allen Fällen: zwei
  Drittel direkt im Prompt, der Rest als Angebot zum Nachschlagen.
- Nennt sie die Methode nicht, fand die Suche das Blatt in gut der Hälfte der Fälle nicht.
- Lag das Blatt im Prompt, folgte der Assistent ihm in jedem Fall.

Ein eigener Suchweg für Methodenblätter (je Assistent hinterlegte Suchanfragen) ist als
Todo vermerkt und noch nicht gebaut. Bis dahin hilft, was in der Hilfe für Lehrkräfte steht:
die Methode in der Aufgabe nennen, den Titel in Schülersprache wählen, ein Verfahren je Blatt.

Ob ein Inhalt im Betrieb ankommt, zeigt die [Vorab-Statistik](vorab-statistik.md): was der
Wissensspeicher vorlegt, was er nur anbietet und was nachgeschlagen wird.

## 3. Assistenten ordnen

Damit Schüler:innen den passenden Assistenten finden, braucht es drei Einstellungen. Alle
drei liegen im Assistenten-Editor (`/assistants/manage/[id]`).

**Schlagwörter = Fachkennung.** Ein allgemeiner Assistent erscheint auf der Fachseite eines
Fachs, wenn eines seiner Schlagwörter die Kennung des Fachs ist, etwa `chemie` oder
`deutsch` (die `slug` aus `config/subjects.yaml`). Ohne passendes Schlagwort steht er auf
keiner Fachseite, sondern nur unter `/assistants`. Das gilt in der Grundausstattung für
„Lernen und Prüfungsvorbereitung“: Er hat kein Schlagwort. Ergänzen Sie Schlagwörter für die
Fächer, in denen Ihre Schule ihn anbieten will.

**Speziell vor allgemein.** Ein Assistent für eine bestimmte Aufgabe (Vorschlagen: „Für eine
bestimmte Aufgabe“) kann unter **„Darunter anbieten“** bis zu drei allgemeine Assistenten
nennen, die der Vorschlag mit anbietet. Der Assistent für Stöchiometrie bietet so
„Rechnen mit Größen und Einheiten“ an. Das Feld sehen nur Admins.

**Bausteine hinter dem Prompt.** „Begleiten statt lösen“ und „Grundton“ sind gemessene
Blöcke, die die Plattform hinter den Prompt hängt: Schema, Hilfe in Stufen, Prüfung am
Operator, Begriffsfragen. Nur Admins hängen sie an. Legt eine Lehrkraft einen eigenen
Schüler-Assistenten an, der begleiten soll, hängen Sie die Bausteine an, statt das Schema
im Prompt nachzubauen. Nur mit „Begleiten statt lösen“ greift auch der Zug-Auslöser
„Nachsetzen“ (Abschnitt 4).

## 4. Die Zug-Auslöser an die Schule anpassen

Zwei Auslöser hängen für eine Antwort eine zusätzliche Anweisung an:

- **Nachsetzen:** Eine Schüler:in bittet zum zweiten Mal hintereinander um die Lösung.
- **Lehrkraft-Behauptung:** Jemand gibt sich in einem Schüler-Chat als Lehrkraft aus.

Erkannt wird über Muster und Beispielsätze in `config/druck_triggers.yaml` und
`config/druck_korpus.yaml`. Die mitgelieferten Sätze sind allgemein. Sprechen Ihre
Schüler:innen anders, ergänzen Sie Beispielsätze aus echten Gesprächen. Ergänzen Sie dabei
immer auch Gegenbeispiele, damit gewöhnliche Fragen nicht anschlagen. Format und Regeln
stehen unter [Konfiguration](konfiguration.md#configdruck_triggersyaml-und-configdruck_korpusyaml).

Wie oft die Auslöser anschlagen und ob die Schüler:in danach weiterarbeitet, zählt

```bash
docker compose exec backend python scripts/zug_ausloeser_statistik.py --seit 2026-11-02
```

Die Ausgabe enthält nur Zahlen, keine Texte und keine Pseudonyme.

## 5. Rückmeldungen auswerten

Lehrkräfte und Schüler:innen melden auffällige Antworten über den Feedback-Kanal. Wie Sie
die Meldungen sichten, steht unter [Rückmeldungen sichten](feedback.md). Zu den Assistenten
sind drei Fälle zu erwarten, die als bekannte Eigenschaften gelten:

- **Korrektur-Reflex:** Bei einem falschen Schritt nennt der Assistent oft gleich das
  Richtige, statt nach dem Fehler zu fragen.
- **Grauzone bei Deutungen:** Bei Text- und Gedichtanalysen ist die Grenze zwischen
  Leitfrage und vorweggenommener Deutung unscharf.
- **Wiederholtes Drängen:** Hier setzt der Auslöser „Nachsetzen“ an; er schlägt aber nicht
  bei jeder Formulierung an.

Einzelheiten zur Messung stehen in der Entwicklerdoku (`docs/dev/assistenten-messen.md`).

## Was wenig hilft

**Eine weitere Regel im Prompt für einen einzelnen Fall.** Gegen den Korrektur-Reflex wurden
mehrere Regeln gemessen. Keine hat ihn verringert. Wer einen Prompt nach einem auffälligen Gespräch ändert, sollte vorher und
nachher an mehreren Fällen messen (siehe `docs/dev/assistenten-messen.md`).

**Der normale Chat statt eines Assistenten.** Auch der normale Chat begleitet Schüler:innen,
aber ohne die Bausteine und ohne den Auslöser „Nachsetzen“. Für Aufgaben sind die Assistenten gemessen,
der normale Chat nicht.
