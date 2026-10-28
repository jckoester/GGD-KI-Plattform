# Datenschutz

## Was wird gespeichert?

ki@schule speichert deine Chat-Verläufe auf dem Schulserver. Das ist notwendig, damit du frühere Gespräche wiederfinden kannst.

Gespeichert werden:
- Die Inhalte deiner Gespräche (Fragen und Antworten)
- Der Zeitpunkt der Nachrichten
- Welches KI-Modell verwendet wurde
- Die anfallenden Kosten pro Gespräch (für die Budgetübersicht)

**Nicht** gespeichert werden:
- Dein echter Name oder deine E-Mail-Adresse in Verbindung mit den Chat-Inhalten
- Passwörter oder andere Zugangsdaten

## Was landet beim KI-Anbieter?

Wenn du eine Nachricht sendest, wird diese über einen schuleigenen Vermittlungsserver (LiteLLM-Proxy) an den KI-Anbieter weitergeleitet. Dabei wird ausschließlich der **Inhalt der Konversation** übertragen — also deine Fragen und die bisherigen Antworten im aktuellen Gespräch.

Der KI-Anbieter erhält **keine** Informationen, die auf dich persönlich schließen lassen: keinen Namen, keine E-Mail-Adresse, keine Klasse, kein Schulkonto. Stattdessen wird ein anonymer Code übermittelt, der keinen Rückschluss auf deine Identität zulässt. Die Zuordnung zwischen Code und Person liegt ausschließlich auf dem Schulserver.

### Aktueller Unterricht in Gruppen-Chats

Führst du einen Chat **mit Bezug zu einer Unterrichtsgruppe**, ergänzt die Plattform einen kleinen Hinweis zum aktuellen Unterricht, damit der Assistent passend helfen kann: Thema und Inhalte der letzten und vorletzten Stunde, das nächste Thema sowie Termin und Umfang der nächsten Klassenarbeit. Als Inhalte erscheinen die Kompetenzen (und Fachbegriffe) aus dem Stundenentwurf — nur solche, die alle in der Gruppe ohnehin lesen dürfen; ist eine Stunde noch nicht nachbereitet, steht dabei „laut Plan“. Seit 0.20 nennt der Hinweis außerdem die Titel der Fachbegriffe, die die Gruppe in der laufenden Unterrichtseinheit schon hatte — ebenfalls nur solche, die alle in der Gruppe lesen dürfen.

**Assistenten-Vorschlag im Chat** *(seit 0.24)*: Passt eine Nachricht im normalen Chat zu einem Assistenten, fragt die Plattform ein kurzes Modell, welcher passt. Dafür geht **dieselbe Nachricht ein zweites Mal** an einen KI-Anbieter — über denselben Vermittlungsserver, ohne deinen Code, zusammen mit den Namen und Beispielsätzen der infrage kommenden Assistenten. Gespeichert wird nur, welche Assistenten in diesem Chat schon angeboten wurden (ihre Nummern, damit derselbe nicht noch einmal kommt); diese Angabe wird mit dem Chat gelöscht.

**Begriffsvorschläge im Stundenentwurf** *(seit 0.18)*: Schlägt die Leiste „Kompetenzen und Fachbegriffe" Begriffe vor, geht der Text des Entwurfs — Titel, Stundenziel und Phasen — an den KI-Anbieter, auf demselben Weg und mit demselben anonymen Code wie im Chat. Das geschieht auf Knopfdruck und automatisch, nachdem der Stundenassistent den Entwurf geändert hat; den Entwurf kennt der Assistent dann ohnehin.

**Nicht** übermittelt werden interne Planungsfelder der Lehrkraft — etwa Kommentare, Reflexionen, der Pin-Status oder die einzelnen Phasen einer Stunde. Es werden nur Angaben weitergegeben, die ohnehin für die Gruppe bestimmt sind (Themen, Stundenziele, Kompetenzen und Fachbegriffe der Stunden, Klassenarbeits-Umfang). Material bleibt draußen — ein Arbeitsblatt mit Lösungen etwa.

Dasselbe gilt für den **Wissensbereich**: Jahrespläne, Unterrichtseinheiten und Stundenentwürfe sind den **Lehrkräften ihrer Unterrichtsgruppe** vorbehalten. Schüler:innen derselben Gruppe finden sie weder über die Suche noch über einen Direktaufruf. *(Bis September 2026 war das anders — sie galten als gruppenweit lesbar, was auch die Schüler:innen einschloss. Seit 0.11 nicht mehr.)*

## Warnung bei persönlichen Daten

Auch wenn der KI-Anbieter deinen Namen nie erfährt (siehe oben): Der **Inhalt** deiner
Nachricht wird übertragen. Tippst du dort echte Namen, Adressen oder Kontaktdaten —
von dir oder von anderen — hinein, landen diese beim Anbieter, obwohl das selten
nötig ist.

Damit das nicht aus Versehen passiert, prüft die Plattform deine Nachricht **vor dem
Senden lokal auf dem Schulserver** auf personenbezogene Daten: Namen, Wohnorte und
Adressen sowie E-Mail-Adressen, Telefonnummern und IBANs.

Wird etwas gefunden, erscheint ein Hinweis mit den markierten Stellen — **gesendet
wurde zu diesem Zeitpunkt noch nichts.** Du entscheidest:

- **Bearbeiten:** zurück zur Nachricht, um die Angaben zu entfernen oder zu ändern.
- **Trotzdem senden:** wenn die Daten bewusst gewollt sind (z. B. eine erfundene
  Beispieladresse für eine Übung), sendest du die Nachricht unverändert.

Der Hinweis ist eine **Empfehlung, keine Sperre.** Die Prüfung läuft vollständig auf
dem Schulserver, **ruft nichts extern auf** und **speichert nichts**.

> **Ehrlich gesagt:** Die Erkennung findet vieles, aber nicht alles — verlass dich
> nicht allein darauf. Die Entscheidung, welche Daten du teilst, bleibt bei dir.

> 📷 *Screenshot folgt: Hinweis auf persönliche Daten vor dem Senden.*
<!-- Ersetzen durch: ![PII-Warnung](/help-images/datenschutz/pii-warnung.png) -->

## Hinweis auf Hilfsangebote

Damit du in schwierigen Situationen nicht allein bleibst, prüft die Plattform deine
Nachrichten **lokal auf dem Schulserver** auf Anzeichen einer persönlichen Krise —
mit einer einfachen Stichwortliste, **ohne KI** und **ohne** dass dafür zusätzliche
Daten an den KI-Anbieter gesendet werden.

Erkennt die Plattform einen solchen Hinweis, erscheint im Chat ein **Hilfe-Banner**
mit schulischen und externen Anlaufstellen. Dein Gespräch wird dabei **nicht**
unterbrochen, und es werden keine Inhalte über das hinaus gespeichert, was ohnehin
als Konversation gespeichert wird.

> 📷 *Screenshot folgt: Hilfe-Banner mit Anlaufstellen im Chat.*
<!-- Ersetzen durch: ![Hilfe-Banner](/help-images/datenschutz/hilfe-banner.png) -->

## Wer kann meine Chats lesen?

Deine Gespräche sind für andere Nutzerinnen und Nutzer — auch für Lehrkräfte — **nicht**
einsehbar. In zwei eng geregelten Ausnahmefällen ist ein Zugriff möglich:

- **Hinweis auf eine Krise:** Erkennt die Plattform Anzeichen einer Notlage (siehe
  „Hinweis auf Hilfsangebote"), kann die Schule in begründeten Fällen Einsicht in das
  betroffene Gespräch nehmen — aber nur im **Vier-Augen-Prinzip**: Zwei berechtigte
  Personen (die Administration und eine beratende Person, z. B. die Schulsozialarbeit)
  müssen **beide** zustimmen. Der Zugriff ist zeitlich befristet, erfolgt **nur lesend**,
  und **jeder** Zugriff wird protokolliert. Eine Nachricht, die du später bearbeitet und
  ersetzt hast, ist in dieser Einsicht weiterhin zu sehen (als ersetzt gekennzeichnet) —
  in deinem eigenen Verlauf nicht mehr.
- **Rechtliche Verpflichtung:** etwa auf richterliche Anordnung.

Die Plattform kann ein Gespräch **nicht** von sich aus deiner Person zuordnen: Die
Verbindung zwischen dem anonymen Code und einer Person liegt allein auf dem Schulserver
und wird nur in diesen geregelten Verfahren — und außerhalb der Software — hergestellt.

## Wie lange bleiben meine Daten?

| Was | Löschung |
|-----|---------|
| Einzelne Konversation | 3 Monate nach der letzten Nachricht |
| Gesamter Account | 3 Monate nach dem letzten Login |
| Eigene Bausteine, die nur du siehst | mit dem Account |
| Eigene Bausteine, die du geteilt hast | bleiben — ohne deinen Namen |
| Deine Bibliothek (Bilder, Diagramme, Dokumente) | mit dem Account |
| Gruppenmitgliedschaften, Lernstand, eigene Einstellungen | mit dem Account |
| Rückmeldungen (Feedback) | 180 Tage nach dem Abschluss; offene bleiben stehen |

Die Löschung erfolgt automatisch. Es gibt keine manuelle Wiederherstellung gelöschter Daten.

Was du mit einer Klasse, einer Fachschaft oder der Schule geteilt hast, wird beim
Löschen deines Accounts **nicht** mitgelöscht — sonst fehlte es plötzlich in den
Planungen anderer. Der Baustein bleibt, die Verbindung zu dir wird entfernt.

> **Ausnahme bei Krisen-Hinweisen:** Wird ein Gespräch wegen eines möglichen
> Krisen-Hinweises markiert, bleibt es länger erhalten — solange die Schule den Fall
> bearbeitet und danach noch bis zu 180 Tage, auch wenn du es selbst löschst. So ist
> sichergestellt, dass Hilfe nicht an einer zu frühen Löschung scheitert.

> **Denk daran:** Ergebnisse, die du aufbewahren möchtest, musst du
> selbst kopieren — ki@schule ist kein dauerhafter Wissensspeicher.

## Rückmeldungen

Wenn du über **„Feedback geben"** eine Meldung schreibst, werden drei Arten von Daten
gespeichert:

| Was | Woher | Löschung |
|-----|-------|---------|
| Dein Meldungstext samt technischem Kontext (Version, Seite, Browser, Fenstergröße) | Du schreibst ihn, den Kontext legt die Plattform bei | 180 Tage nach dem Abschluss der Meldung |
| Eine **freiwillige** Kontaktangabe | nur wenn du das Feld ausfüllst | beim Abschluss der Meldung, spätestens mit der Meldung |
| Eine **Kopie des Chats**, wenn du ihn ausdrücklich anhängst | nur nach deinem Häkchen | beim Abschluss der Meldung, sofern sie nicht ausdrücklich behalten wird |

Die Meldung trägt dein Pseudonym und deine Rolle — sonst keine Identität. Lesen können sie
nur die Administrator:innen der Schule; sie dient allein der Verbesserung der Plattform.
Eine Kontaktangabe wird **ausschließlich** für Rückfragen zu dieser einen Meldung
genutzt, nie als Grundlage für Einsicht in Chats.

Der angehängte Chat bleibt damit **länger erhalten** als die normalen drei Monate — er
folgt der Frist der Meldung. Das geschieht nur auf dein ausdrückliches Häkchen hin.

Wird dein Konto gelöscht, bleibt die Meldung als Befund über die Software bestehen,
verliert aber Pseudonym und Kontaktangabe und ist dann niemandem mehr zuzuordnen.

Mehr dazu: [Feedback geben](/help/feedback).

## Weiterführende Informationen

Für die vollständige [Datenschutzerklärung](/info/datenschutz) und das [Impressum](/info/impressum) besuch bitte die entsprechenden Seiten.
