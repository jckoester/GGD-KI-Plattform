# Kontextspeicher

Der Kontextspeicher ist eine Sammlung von Wissensbausteinen, die Sie einer Chat-Unterhaltung gezielt hinzufügen können. Die KI liest diese Bausteine beim Antworten mit und kann so präzisere, inhaltlich passendere Antworten geben.

> ⚠️ **Die Suche im Kontextspeicher ist noch experimentell.** Sie findet oft das Richtige, aber nicht verlässlich — je nach Formulierung liefert sie auch einmal thematisch benachbarte Bausteine statt der gesuchten, oder sie übersieht etwas, das vorhanden ist. Auch der Assistent kann sich davon täuschen lassen und antworten, es gebe zu einem Thema nichts, obwohl Bausteine dazu vorliegen.
>
> **Was das für Sie heißt:** Verlassen Sie sich bei wichtigen Inhalten nicht allein auf die Suche. Findet sie einen Baustein nicht, versuchen Sie es mit dem genauen Namen (siehe unten) oder heften Sie ihn über den `@`-Shortcode direkt an. Und prüfen Sie die Aussage eines Assistenten, im Kontextspeicher sei „nichts vorhanden", im Zweifel selbst nach.
>
> **Wenn der Assistent nach einem Fach fragt, obwohl Sie alle meinen:** Bitten Sie ihn ausdrücklich zu suchen — etwa „Bitte suche nach allen Vorkommen von ‚nennen' und erstelle daraus die Liste." Assistenten greifen bei fachbezogenen Fragen bevorzugt zum Fach-Werkzeug, das nur ein Fach kennt; der ausdrückliche Suchauftrag führt sie auf den richtigen Weg.
>
> Woran das liegt: Der Bestand besteht bislang fast nur aus Bildungsplan-Daten. Sobald Lehrkräfte in größerem Umfang eigene Bausteine anlegen — Begriffsdefinitionen, Methoden, Anleitungen —, muss die Suche neu bewertet werden. Wir arbeiten daran.

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

Tippen Sie **`@`** in das Textfeld, um nach einem Baustein nach Name zu suchen. Wählen Sie einen Treffer aus der Liste — der Baustein wird sofort angeheftet.

### Kontext wieder entfernen

Angeheftete Bausteine werden als beschriftete Chips oberhalb des Textfelds angezeigt. Ein Klick auf das **×** rechts am Chip entfernt ihn wieder aus dem Kontext.

## Angezeigte Trefferzahl einstellen

Das Vorschlagsfenster zeigt standardmäßig bis zu 8 Treffer. Wenn Sie häufig mit komplexen Themen arbeiten und mehr Auswahlmöglichkeiten wünschen, können Sie den Wert auf Ihrer [Profilseite](profil.md) erhöhen.

Die Einstellung betrifft **nur Ihre eigene Suche** über den Suche-Button. Wie viele Bausteine ein Assistent bei seiner eigenen Suche heranzieht, legt die Schule zentral fest — dort geht es nicht um Platz auf dem Bildschirm, sondern um Kosten. Diese Suche läuft im Hintergrund: Der Assistent liest die gefundenen Bausteine, ohne dass Ihnen dazu eine Auswahlliste angeboten wird. Das Vorschlagsfenster erscheint also nur, wenn Sie selbst gesucht haben.

> ⚠️ **Trefferlisten sind gekürzt, und das steht nirgends dabei.** Gibt es zu einer Suche mehr passende Bausteine als Plätze, liefert die Suche nur die vordersten — ohne Hinweis darauf, dass etwas fehlt. Eine Liste sieht also immer vollständig aus.
>
> Das trifft besonders Fragen, die **alle** Vorkommen eines Begriffs wollen. Der Operator „nennen" etwa steht in 18 Fächern; eine Antwort darauf nennt derzeit 14 davon und wirkt dabei erschöpfend. Wenn Vollständigkeit für Sie zählt, prüfen Sie das Ergebnis gegen den Wissensgraphen — verlassen Sie sich nicht darauf, dass eine Liste alles enthält.

## Kontext und Datenschutz

Kontextbausteine, die einer Unterhaltung hinzugefügt werden, werden zusammen mit Ihren Nachrichten an die KI übermittelt. Es gelten dieselben Datenschutzregeln wie für Chat-Nachrichten — lesen Sie dazu die [Datenschutzerklärung](datenschutz.md).
