# Kontextspeicher

Der Kontextspeicher ist eine Sammlung von Wissensbausteinen, die Sie einer Chat-Unterhaltung gezielt hinzufügen können. Die KI liest diese Bausteine beim Antworten mit und kann so präzisere, inhaltlich passendere Antworten geben.

> **Was die Suche zusagt — und was nicht.** Sie antwortet in getrennten Abschnitten, und
> der Unterschied ist wichtig:
>
> - **Bausteine mit diesem Namen** und **Alle passenden Bausteine** sind
>   vollständig — mit Zahl. Steht dort „24 gefunden", gibt es 24; steht dort „8 von 24
>   angezeigt", wissen Sie, dass mehr da ist. Wird ein Name nicht gefunden, heißt das
>   verlässlich: Es gibt keinen Baustein dieses Namens.
> - **Nächstliegende Bausteine** sind eine Empfehlung nach Ähnlichkeit und **nie
>   vollständig**. Dass dort etwas fehlt, heißt nicht, dass es das nicht gibt.
>
> Was daraus folgt: Suchen Sie nach etwas Bestimmtem, nehmen Sie den Namen — über die
> Suchseite oder den `@`-Shortcode. Für „was gibt es zu diesem Thema?" ist die
> Ähnlichkeitssuche gedacht, und die bleibt eine Heuristik: Sie schlägt vor, sie zählt
> nicht.
>
> Der Bestand besteht bislang fast nur aus Bildungsplan-Daten. Sobald Lehrkräfte in
> größerem Umfang eigene Bausteine anlegen — Begriffsdefinitionen, Methoden, Anleitungen
> —, ist die thematische Suche neu zu bewerten.

## Was sind Kontextbausteine?

Ein Kontextbaustein ist ein konkretes Informationsstück — zum Beispiel:

- eine Kompetenz aus dem Bildungsplan (z. B. „Schülerinnen und Schüler können Brüche auf der Zahlengeraden darstellen")
- ein schultypisches Konzept, das an Ihrer Schule besonders behandelt wird
- ein Thema oder eine Funktion aus dem Unterrichtsmaterial

Diese Bausteine werden von der Schule gepflegt und stehen allen Nutzenden zur Verfügung. Lehrkräfte können zusätzlich eigene Bausteine anlegen.

## Wozu ist das nützlich?

Ohne Kontext kennt die KI nur das, was Sie in der Eingabe schreiben. Mit Kontextbausteinen können Sie ihr gezielt Hintergrundwissen mitgeben — ohne alles selbst eintippen zu müssen.

**Beispiele:**

- Sie fragen nach einer Erklärung für Klasse 5 und fügen die zugehörige Bildungsplan-Kompetenz als Kontext hinzu → die KI orientiert sich am tatsächlichen Kompetenzrahmen.
- Sie entwickeln eine Aufgabe zu einem Arduino-Baustein und fügen dessen technische Beschreibung als Kontext ein → die KI kennt genaue Bezeichnungen und Parameter.

## Kontext im Chat hinzufügen

### Über den Suche-Button

Neben dem Textfeld im Chat gibt es einen **Suche-Button** (Lupensymbol). Er ist klickbar, sobald Sie etwas in das Textfeld eingetippt haben.

1. Tippen Sie Ihre Frage oder einen beschreibenden Text ins Textfeld.
2. Klicken Sie den Suche-Button — die Plattform sucht automatisch nach passenden Kontextbausteinen.
3. Eine Auswahlliste erscheint über dem Eingabefeld, nach Abschnitten geordnet: **Bausteine mit diesem Namen**, **Ähnlich benannte Bausteine** und **Nächstliegende Bausteine**. Vorausgewählt sind höchstens fünf je Abschnitt, ähnlich benannte keine — Sie können einzeln zu- und abwählen oder oben rechts **„Alle"** klicken.
4. Klicken Sie **„Hinzufügen"** — die gewählten Bausteine werden als Chips über dem Textfeld angeheftet.

Warum nicht alles vorausgewählt ist: Ein Name kann vielen Bausteinen gehören — „nennen" etwa steht als Operator in jedem Fach und in mehreren Bildungsplan-Fassungen. Jeder angeheftete Baustein geht als Text an das Sprachmodell; vorausgewählt ist deshalb nur, was oben steht. Wurde die Liste gekürzt, führt ein Verweis am Abschnittsende zur Suchseite (Menüpunkt **Wissensgraph**), die alle Treffer zeigt.

> 📷 *Screenshot folgt: Angeheftete Kontextbausteine als Chips über dem Eingabefeld.*
<!-- Ersetzen durch: ![Kontext-Chips](/help-images/kontext/kontext-chips.png) -->

Die Suche verwendet semantische Ähnlichkeit: Sie müssen nicht exakte Schlagwörter treffen — auch ein vollständig formulierter Prompt liefert passende Treffer.

**Namen werden direkt nachgeschlagen.** Suchen Sie nach einem Begriff, den es als Baustein gibt — einem Operator wie „nennen", einer Leitidee, einem Fachbegriff —, steht er oben, auch wenn andere Bausteine thematisch näher liegen. Die Frageform ist dabei egal: „nennen", „Operator nennen" und „Was bedeutet der Operator nennen?" führen zum selben Ergebnis. Wo derselbe Name in mehreren Fächern vorkommt, erscheinen die Fächer nacheinander.

**Das Fach des Chats zählt mit.** Führen Sie den Chat in einem Fach oder einer Unterrichtsgruppe, stehen dessen Bausteine weiter oben. Ausgeblendet wird dabei nichts: Wer im Physik-Chat nach dem Satz des Pythagoras fragt, bekommt weiterhin die Mathematik-Kompetenz — sie ist dort schließlich die richtige Antwort. In einem Chat ohne Fach entscheidet allein die Ähnlichkeit.

### Über den @-Shortcode

Tippen Sie **`@`** in das Textfeld, um einen Baustein über seinen Namen zu finden. Wählen Sie einen Treffer aus der Liste — der Baustein wird sofort angeheftet.

**Mehrwortige Titel dürfen Sie ausschreiben.** Tippen Sie ruhig `@Satz des Pythagoras` — die Liste engt sich mit jedem Wort weiter ein. Es genügt aber auch der Anfang (`@Satz`) oder ein Wort aus der Mitte (`@Pythagoras`). Ganz oben steht, was **genau** so heißt, dahinter, was so anfängt, dann Ähnliches. Bausteine aus dem Fach des Chats stehen weiter vorn.

Die Liste schließt sich mit **Esc**, sobald Sie einen Treffer wählen — und wenn nichts mehr passt. Ein `@` mitten im Satz stört also nicht.

### Kontext wieder entfernen

Angeheftete Bausteine werden als beschriftete Chips oberhalb des Textfelds angezeigt. Ein Klick auf das **×** rechts am Chip entfernt ihn wieder aus dem Kontext.

## Angezeigte Trefferzahl einstellen

Das Vorschlagsfenster zeigt standardmäßig bis zu 8 Treffer. Wenn Sie häufig mit komplexen Themen arbeiten und mehr Auswahlmöglichkeiten wünschen, können Sie den Wert auf Ihrer [Profilseite](profil.md) erhöhen.

Die Einstellung betrifft **nur Ihre eigene Suche** über den Suche-Button. Wie viele Bausteine ein Assistent bei seiner eigenen Suche heranzieht, legt die Schule zentral fest — dort geht es nicht um Platz auf dem Bildschirm, sondern um Kosten. Diese Suche läuft im Hintergrund: Der Assistent liest die gefundenen Bausteine, ohne dass Ihnen dazu eine Auswahlliste angeboten wird. Das Vorschlagsfenster erscheint also nur, wenn Sie selbst gesucht haben.

**Eine gekürzte Liste sagt es Ihnen.** Reicht der Platz nicht, steht am Abschnittsende, wie viel fehlt — „5 von 24 angezeigt" — und ein Verweis führt zur Suchseite mit allen Treffern. Sie müssen also nicht raten, ob eine Liste vollständig ist.

Das gilt für die Abschnitte **Bausteine mit diesem Namen** und **Alle passenden Bausteine**; die **Nächstliegenden** sind eine Auswahl nach Ähnlichkeit und tragen deshalb keine Gesamtzahl (siehe oben).

## Archivieren statt löschen

Bausteine, die Sie selbst angelegt haben, können Sie im Wissensgraphen **archivieren**
oder **löschen**. Der Unterschied ist größer, als die beiden Wörter vermuten lassen:

- **Archiviert** heißt: aus Suche und Assistenten heraus, aber nicht weg. Der Baustein
  bleibt in Ihrem Archiv, alle Verknüpfungen bleiben, und Sie können ihn jederzeit
  zurückholen.
- **Gelöscht** heißt: endgültig fort, samt seiner Verknüpfungen.

Deshalb greift eine Regel: **Verweisen aktive Bausteine anderer auf Ihren, lässt er sich
nicht löschen.** Die Plattform zeigt Ihnen dann, wer darauf aufbaut, und bietet
Archivieren an. Ihre eigenen Verweise halten Sie nicht auf.

Bei fremden Bausteinen — schulweiten Vorlagen, dem Bildungsplan, Material der Fachschaft —
erscheinen die beiden Knöpfe gar nicht erst: Sie pflegt, wem sie gehören.

**Abgelaufene Bausteine.** Trägt ein Baustein ein Ablaufdatum, wandert er danach von
selbst ins Archiv; im Archiv steht dann „abgelaufen am …". **Reaktivieren** holt ihn
zurück und setzt zugleich ein neues Ablaufdatum — sonst wäre er noch in derselben Nacht
wieder verschwunden. Nach drei Schuljahren im Archiv werden eigene Bausteine endgültig
gelöscht; Bildungsplan und importierte Inhalte nie.

## Kontext und Datenschutz

Kontextbausteine, die einer Unterhaltung hinzugefügt werden, werden zusammen mit Ihren Nachrichten an die KI übermittelt. Es gelten dieselben Datenschutzregeln wie für Chat-Nachrichten — lesen Sie dazu die [Datenschutzerklärung](datenschutz.md).
