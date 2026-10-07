# Den Chat nutzen

## Nachrichten schreiben und senden

Tippen Sie Ihre Nachricht in das Textfeld am unteren Rand des Chatfensters. Mit **Enter** wird die Nachricht abgeschickt. Mit **Shift + Enter** können Sie innerhalb der Eingabe einen Zeilenumbruch einfügen, ohne die Nachricht abzusenden.

Die KI antwortet direkt im Gesprächsfenster. Sie sieht dabei immer den gesamten bisherigen Verlauf des aktuellen Gesprächs — Sie müssen Zusammenhänge nicht jedes Mal neu erklären.

> 📷 *Screenshot folgt: Eingabefeld mit Büroklammer (Datei), Suche-Button und Modell-Auswahl.*
<!-- Ersetzen durch: ![Chat-Eingabefeld](/help-images/chat/eingabefeld.png) -->

## Modell wechseln

Über das Auswahlmenü im Chatfenster können Sie zwischen verschiedenen KI-Modellen wechseln — auch mitten in einem laufenden Gespräch. Welche Modelle verfügbar sind, hängt von der Konfiguration Ihrer Schule ab.

> 📷 *Screenshot folgt: Geöffnete Modell-Auswahl im Chatfenster.*
<!-- Ersetzen durch: ![Modell-Auswahl](/help-images/chat/modell-auswahl.png) -->

Ein einmal gewähltes Modell wird gespeichert und beim nächsten Chat automatisch vorausgewählt. Sie können es jederzeit wieder ändern.

Modelle unterscheiden sich in Geschwindigkeit, Qualität und Kosten. Für die meisten Aufgaben reicht das voreingestellte Modell aus. Wenn Sie sehr lange Texte verarbeiten oder besonders anspruchsvolle Aufgaben stellen, kann ein leistungsstärkeres Modell besser geeignet sein.

**Was neben dem Namen steht.** `~7 🪙` schätzt, wie viele Einheiten eine gewöhnliche Nachricht mit diesem Modell kostet; abgerechnet wird nach dem tatsächlichen Verbrauch. Was eine Einheit ist, erklärt [Profil & Budget](profil.md). Das Zahnrad `⚙` heißt: Das Modell kann die Fähigkeiten eines Assistenten nutzen, etwa im Wissensspeicher suchen oder Unterricht planen. Fehlt es, ist das nicht der Fall oder nicht bekannt — für einfache Fragen spielt es keine Rolle.

Wenn Sie das Modell wechseln, erscheint im Gesprächsverlauf ein schmaler Trenner, der anzeigt, ab welcher Antwort das neue Modell aktiv war. Der bisherige Verlauf bleibt vollständig erhalten und ist weiterhin Teil des Kontexts.

## Assistenten im laufenden Chat wechseln

Sie können auch während eines Gesprächs zu einem anderen Assistenten wechseln, ohne einen neuen Chat starten zu müssen. Tippen Sie dazu **`/`** in das Textfeld — der Assistenten-Picker öffnet sich und Sie können einen anderen Assistenten auswählen.

Nach dem Wechsel erscheint ein Hinweis über dem Eingabefeld, der den neuen Assistenten bestätigt. Beim nächsten Senden ist der neue Assistent aktiv. Im Gesprächsverlauf wird der Wechsel durch einen Trenner markiert.

## Dateien hochladen

Sie können Dateien direkt in ein Gespräch einbinden — zum Beispiel ein PDF, ein Bild oder eine Textdatei. Die KI kann den Inhalt lesen und in ihrer Antwort berücksichtigen.

**So laden Sie eine Datei hoch:**
1. Klicken Sie auf das Büroklammer-Symbol neben dem Textfeld.
2. Wählen Sie eine Datei von Ihrem Gerät aus.
3. Schreiben Sie dazu, was die KI damit tun soll, und senden Sie die Nachricht.

**Unterstützte Dateitypen:** PDF, gängige Bildformate (JPG, PNG, …), Textdateien  
**Maximale Dateigröße:** 10 MB pro Datei

## Kontextbausteine hinzufügen

Über den **Suche-Button** (Lupensymbol) neben dem Textfeld können Sie passende Wissensbausteine aus dem Kontextspeicher in den Chat einbinden — zum Beispiel Bildungsplan-Kompetenzen oder Unterrichtsmaterial. Die KI berücksichtigt diese Bausteine beim Antworten.

Tippen Sie Ihre Frage oder einen beschreibenden Text ein und klicken Sie den Button. Die Plattform sucht semantisch passende Bausteine und zeigt sie zur Auswahl an. Bestätigte Bausteine erscheinen als Chips oberhalb des Textfelds und können dort wieder entfernt werden.

Alternativ tippen Sie **`@`** ins Textfeld, um direkt nach einem Baustein zu suchen.

Mehr dazu: [Kontextspeicher](kontext.md)

## Kontext unter der Antwort

Unter einer Antwort steht oft **„Kontext (n)“**. Aufgeklappt zeigt die Zeile die Bausteine
aus dem Wissensspeicher der Schule, die der KI beim Antworten **vorlagen** — mit Fach und
einem Link zum Baustein. Die Plattform sucht zu jeder Nachricht selbst passende Bausteine
heraus; schlägt der Assistent beim Antworten weitere nach, stehen sie mit dabei.

**Die Zeile ist keine Quellenangabe.** Sie sagt, was vorlag — nicht, was die KI davon
tatsächlich verwendet hat, und nicht, dass die Antwort stimmt. Eine Antwort kann falsch
sein und trotzdem passende Bausteine unter sich haben. Im Zweifel öffnen Sie den Baustein
und lesen selbst nach.

Steht keine Zeile da, lag zu dieser Frage nichts aus dem Wissensspeicher vor — oder Sie
haben die Zeile im Profil ausgeschaltet. Bei Antworten von vor Oktober 2026 fehlt sie
immer.

Wie ausführlich die Zeile ist, stellen Sie im [Profil](profil.md) unter **„Kontext zur
Antwort“** ein. „Ausführlich“ zeigt zusätzlich:

- den **Fundweg**: „vorab zur Frage gefunden“ (die Plattform hat gesucht) oder „vom
  Assistenten nachgeschlagen“ (das Modell hat selbst gesucht), bei der Vorab-Suche dazu
  die **Ähnlichkeit** zur Frage oder „über den Namen“;
- das **Änderungsdatum** — wann zuletzt jemand an dem Baustein gearbeitet hat;
- die **Abbildungen** des Bausteins, etwa ein Gefahrenpiktogramm oder eine
  Strukturformel.

## Formeln, Chemie und Diagramme

Mathematische Formeln, chemische Gleichungen und einfache Diagramme werden im Chat
**grafisch dargestellt** statt als Rohtext — sowohl in den Antworten der KI als auch in dem,
was Sie selbst schreiben.

- **Mathematik** in LaTeX-Schreibweise zwischen Dollarzeichen: `$a^2 + b^2 = c^2$` im Text
  oder `$$\int_0^1 x\,dx$$` als abgesetzte Formel.
- **Chemie** mit `\ce{ }`: `$\ce{2 H2 + O2 -> 2 H2O}$` ergibt eine gesetzte Reaktionsgleichung.
- **Diagramme** als Codeblock mit der Sprache **mermaid** — zum Beispiel ein Flussdiagramm:

      flowchart LR
        A[Frage] --> B[Antwort]

Die Darstellung passiert automatisch auf Ihrem Gerät. Wenn Sie die LaTeX-Schreibweise nicht
kennen, bitten Sie die KI einfach, etwas „als Formel" zu schreiben — sie kümmert sich um die
richtige Notation.

**Weiterverwenden.** Fahren Sie über eine abgesetzte Formel, erscheint **„Kopieren"**: In der
Zwischenablage landet die Schreibweise `$$…$$`, die sich in Chat, Werkstatt oder Wissensgraph
wieder einfügen lässt. Wer Text mit Formeln markiert und kopiert, bekommt die Formeln ebenfalls
so.

Auch **elektrische Schaltpläne** und **Funktionsgraphen** stellt der Chat als Grafik dar — was
dabei geht und wie Sie eine Grafik weiterverwenden, steht unter
[Diagramme, Schaltpläne & Funktionsgraphen](diagramme.md).

## Chat-Verlauf

Alle Ihre Gespräche werden unter **„Letzte Chats"** in der Seitenleiste gespeichert. Von dort können Sie ein älteres Gespräch jederzeit wieder öffnen und fortsetzen.

Gespräche, die mit einem Assistenten geführt wurden, sind im Verlauf entsprechend gekennzeichnet.

**Für Lehrkräfte:** Gehört ein Chat zu einer Unterrichtsgruppe, steht deren Name in der
Chat-Übersicht neben dem Titel; in der Seitenleiste nennt ihn der Tooltip. Vier Chats mit
dem Titel „Sinusfunktionen verstehen" lassen sich sonst nicht auseinanderhalten. Ist Ihnen
der Name zu lang, vergeben Sie der Gruppe unter *Unterricht* einen kürzeren Anzeigenamen —
er wird überall verwendet.

> **Hinweis:** Gespräche werden 3 Monate nach der letzten Nachricht automatisch gelöscht.
> Ergebnisse, die Sie aufbewahren möchten, müssen Sie selbst kopieren.

## Wenn etwas schiefläuft

**„Budget aufgebraucht"**
Ihr Budget für KI-Anfragen ist erschöpft. In der nächsten Unterrichtswoche kommt wieder Guthaben dazu; den Termin und den Betrag nennt Ihre [Profilseite](profil.md). Ein Ausweichen auf ein anderes Modell gibt es nicht. Ältere Gespräche können Sie weiterhin lesen.

**Die Antwort kommt nicht / der Chat hängt**
Laden Sie die Seite neu. Ihr Gespräch bleibt im Verlauf erhalten — Sie können dort weitermachen.

**Fehlermeldung: Modell nicht verfügbar**
Das gewählte Modell ist momentan nicht erreichbar. Wechseln Sie zu einem anderen Modell oder versuchen Sie es etwas später erneut.
