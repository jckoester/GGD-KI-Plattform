# Datenschutz

## Was wird gespeichert?

ki@schule speichert Ihre Chat-Verläufe auf dem Schulserver. Das ist notwendig, damit Sie frühere Gespräche wiederfinden können.

Gespeichert werden:
- Die Inhalte Ihrer Gespräche (Fragen und Antworten)
- Der Zeitpunkt der Nachrichten
- Welches KI-Modell verwendet wurde
- Die anfallenden Kosten pro Gespräch (für die Budgetübersicht)

**Nicht** gespeichert werden:
- Ihr echter Name oder Ihre E-Mail-Adresse in Verbindung mit den Chat-Inhalten
- Passwörter oder andere Zugangsdaten

## Was landet beim KI-Anbieter?

Wenn Sie eine Nachricht senden, wird diese über einen schuleigenen Vermittlungsserver (LiteLLM-Proxy) an den KI-Anbieter weitergeleitet. Dabei wird ausschließlich der **Inhalt der Konversation** übertragen — also Ihre Fragen und die bisherigen Antworten im aktuellen Gespräch.

Der KI-Anbieter erhält **keine** Informationen, die auf Sie persönlich schließen lassen: keinen Namen, keine E-Mail-Adresse, keine Klasse, kein Schulkonto. Stattdessen wird ein anonymer Code übermittelt, der keinen Rückschluss auf Ihre Identität zulässt. Die Zuordnung zwischen Code und Person liegt ausschließlich auf dem Schulserver.

### Aktueller Unterricht in Gruppen-Chats

Führen Sie einen Chat **mit Bezug zu einer Unterrichtsgruppe**, ergänzt die Plattform einen kleinen Hinweis zum aktuellen Unterricht, damit der Assistent passend helfen kann: das zuletzt behandelte und das nächste Thema sowie Termin und Umfang der nächsten Klassenarbeit.

**Nicht** übermittelt werden interne Planungsfelder der Lehrkraft — etwa Kommentare, Reflexionen, der Pin-Status oder die einzelnen Phasen einer Stunde. Es werden nur Angaben weitergegeben, die ohnehin für die Gruppe bestimmt sind (Themen, Stundenziele, Klassenarbeits-Umfang).

## Warnung bei persönlichen Daten

Auch wenn der KI-Anbieter Ihren Namen nie erfährt (siehe oben): Der **Inhalt** Ihrer
Nachricht wird übertragen. Tippen Sie dort echte Namen, Adressen oder Kontaktdaten —
von sich oder von anderen — hinein, landen diese beim Anbieter, obwohl das selten
nötig ist.

Damit das nicht aus Versehen passiert, prüft die Plattform Ihre Nachricht **vor dem
Senden lokal auf dem Schulserver** auf personenbezogene Daten: Namen, Wohnorte und
Adressen sowie E-Mail-Adressen, Telefonnummern und IBANs.

Wird etwas gefunden, erscheint ein Hinweis mit den markierten Stellen — **gesendet
wurde zu diesem Zeitpunkt noch nichts.** Sie entscheiden:

- **Bearbeiten:** zurück zur Nachricht, um die Angaben zu entfernen oder zu ändern.
- **Trotzdem senden:** wenn die Daten bewusst gewollt sind (z. B. eine erfundene
  Beispieladresse für eine Übung), senden Sie die Nachricht unverändert.

Der Hinweis ist eine **Empfehlung, keine Sperre.** Die Prüfung läuft vollständig auf
dem Schulserver, **ruft nichts extern auf** und **speichert nichts**.

> **Ehrlich gesagt:** Die Erkennung findet vieles, aber nicht alles — verlassen Sie
> sich nicht allein darauf. Die Entscheidung, welche Daten Sie teilen, bleibt bei Ihnen.

> 📷 *Screenshot folgt: Hinweis auf persönliche Daten vor dem Senden.*
<!-- Ersetzen durch: ![PII-Warnung](/help-images/datenschutz/pii-warnung.png) -->

## Hinweis auf Hilfsangebote

Damit Sie in schwierigen Situationen nicht allein bleiben, prüft die Plattform Ihre
Nachrichten **lokal auf dem Schulserver** auf Anzeichen einer persönlichen Krise —
mit einer einfachen Stichwortliste, **ohne KI** und **ohne** dass dafür zusätzliche
Daten an den KI-Anbieter gesendet werden.

Erkennt die Plattform einen solchen Hinweis, erscheint im Chat ein **Hilfe-Banner**
mit schulischen und externen Anlaufstellen. Ihr Gespräch wird dabei **nicht**
unterbrochen, und es werden keine Inhalte über das hinaus gespeichert, was ohnehin
als Konversation gespeichert wird.

> 📷 *Screenshot folgt: Hilfe-Banner mit Anlaufstellen im Chat.*
<!-- Ersetzen durch: ![Hilfe-Banner](/help-images/datenschutz/hilfe-banner.png) -->

## Wer kann meine Chats lesen?

Ihre Gespräche sind für andere Nutzerinnen und Nutzer — auch für Lehrkräfte — **nicht**
einsehbar. In zwei eng geregelten Ausnahmefällen ist ein Zugriff möglich:

- **Hinweis auf eine Krise:** Erkennt die Plattform Anzeichen einer Notlage (siehe
  „Hinweis auf Hilfsangebote"), kann die Schule in begründeten Fällen Einsicht in das
  betroffene Gespräch nehmen — aber nur im **Vier-Augen-Prinzip**: Zwei berechtigte
  Personen (die Administration und eine beratende Person, z. B. die Schulsozialarbeit)
  müssen **beide** zustimmen. Der Zugriff ist zeitlich befristet, erfolgt **nur lesend**,
  und **jeder** Zugriff wird protokolliert.
- **Rechtliche Verpflichtung:** etwa auf richterliche Anordnung.

Die Plattform kann ein Gespräch **nicht** von sich aus Ihrer Person zuordnen: Die
Verbindung zwischen dem anonymen Code und einer Person liegt allein auf dem Schulserver
und wird nur in diesen geregelten Verfahren — und außerhalb der Software — hergestellt.

## Wie lange bleiben meine Daten?

| Was | Löschung |
|-----|---------|
| Einzelne Konversation | 3 Monate nach der letzten Nachricht |
| Gesamter Account | 3 Monate nach dem letzten Login |

Die Löschung erfolgt automatisch. Es gibt keine manuelle Wiederherstellung gelöschter Daten.

> **Ausnahme bei Krisen-Hinweisen:** Wird ein Gespräch wegen eines möglichen
> Krisen-Hinweises markiert, bleibt es länger erhalten — solange die Schule den Fall
> bearbeitet und danach noch bis zu 180 Tage, auch wenn Sie es selbst löschen. So ist
> sichergestellt, dass Hilfe nicht an einer zu frühen Löschung scheitert.

> **Denken Sie daran:** Ergebnisse, die Sie aufbewahren möchten, müssen Sie
> selbst kopieren — ki@schule ist kein dauerhafter Wissensspeicher.

## Weiterführende Informationen

Für die vollständige [Datenschutzerklärung](/info/datenschutz) und das [Impressum](/info/impressum) besuchen Sie bitte die entsprechenden Seiten.
