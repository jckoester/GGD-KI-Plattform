# Unterrichtsplanung

Die Unterrichtsplanung hilft Lehrkräften, ein Schuljahr von der groben
Jahresübersicht bis zur einzelnen Stunde zu planen — manuell oder dialoggestützt
mit einem Assistenten. Sie erreichen sie über eine Ihrer Unterrichtsgruppen
(**Fächer → Gruppe → Planung**).

> **Hinweis:** Die Unterrichtsplanung ist eine Funktion für **Lehrkräfte**.
> Schüler:innen sehen sie nicht — sie bekommen nur das aktuelle Thema im Chat
> (siehe [Was Schüler:innen mitbekommen](#was-schülerinnen-mitbekommen)).

---

## Jahresübersicht

Die Jahresübersicht zeigt jede Unterrichtsstunde des Schuljahres als Zeile,
gruppiert nach Kalenderwochen. Ferien, Feiertage und unterrichtsfreie Tage
erscheinen als eigene, schraffierte Zeilen.

> 📷 *Screenshot folgt: Jahresübersicht mit Wochenzeilen, UE-Farbbalken und Stundenbilanz in der Leiste.*
<!-- Ersetzen durch: ![Jahresübersicht](/help-images/unterrichtsplanung/jahresuebersicht.png) -->

Damit arbeiten Sie so:

- **Unterrichtseinheiten (UE) anlegen** und mit Kapiteln des
  [Schulcurriculums](curriculum.md) verknüpfen. Die
  Leiste oben zeigt pro UE die **Stundenbilanz**: Soll-Stunden aus dem Lehrplan
  gegen die zugewiesenen Slots.
- **Slots einer UE zuordnen**, Themen direkt eintragen, **Kategorie** ändern
  (Unterricht, Prüfung, Puffer, Ausfall, Vertretung), Stunden **anpinnen** (Fixpunkte
  wie Klassenarbeiten) und Kommentare hinterlegen. Prüfungsstunden sind **rot
  schraffiert**, ausgefallene gedämpft und durchgestrichen — der Tag lässt sich
  überfliegen, ohne jede Zeile zu lesen.
- **Klick auf eine UE** in der oberen Leiste springt zur ersten Stunde dieser UE.
- **Klick auf den Titel** einer geplanten Stunde öffnet deren Stundenentwurf.
- Beim Öffnen scrollt die Übersicht automatisch zur **aktuellen Woche**.
- Über **Wochenmuster** legen Sie fest, an welchen Wochentagen die Gruppe
  Unterricht hat, und erzeugen daraus die Slots eines Halbjahres — auf Wunsch gleich
  [bis zum Schuljahresende](#das-ganze-jahr-planen).
- Über **Verlauf** machen Sie Änderungen rückgängig (jede Änderung wird gesichert).

> **Wenn Ihre Schule den Stundenplan angebunden hat**, können Sie das Wochenmuster
> übernehmen statt eintippen, und Ausfall, Vertretung und Verlegungen kommen von selbst in
> die Planung — siehe [Stundenplan übernehmen](stundenplan.md).

---

### Wenn keine Kapitel zur Auswahl stehen

Beim Anlegen einer Unterrichtseinheit können Sie sie mit einem Kapitel des
[Schulcurriculums](curriculum.md) verknüpfen. Stehen dort keine zur Auswahl, sagt die
Plattform, **woran** es liegt — die drei Gründe verlangen verschiedene Schritte:

| Was dasteht | Was fehlt | Was zu tun ist |
|---|---|---|
| „Dieser Gruppe ist kein Fach zugeordnet." | das **Fach** an der Gruppe | Ohne Fach gibt es weder Curriculum noch Assistentenauswahl noch Fachseite. Legen Sie die Gruppe über **Klasse und Fach** neu an. |
| „Der Jahrgang dieser Gruppe ist nicht bekannt." | die **Stufe** | Tragen Sie sie unter **Unterricht → Meine Unterrichtsgruppen** im Feld „Jahrgang" ein. |
| „Für diese Stufe ist kein Curriculum hinterlegt." | tatsächlich das Curriculum | Nichts — die Verknüpfung ist optional. Wer eines braucht, legt es unter [Schulcurriculum](curriculum.md) an. |

### Der Jahrgang einer Unterrichtsgruppe

Meist ergibt er sich von selbst: aus der Klasse, aus der die Gruppe stammt, sonst aus
ihrem Namen (`10abcd nwt` → 10, `ch-tl-abi28` → Kursstufe). Beides ist nur eine
**Vermutung**. Unter **Unterricht → Meine Unterrichtsgruppen** steht dafür das Feld
„Jahrgang":

- Leer heißt **nicht festgelegt** — dann gilt die Vermutung.
- Eine eingetragene Zahl **gilt**, auch gegen die Klasse. Das ist Absicht: Bei
  jahrgangsübergreifenden Kursen und Wiederholer-Gruppen ist die Klasse der falsche
  Anhaltspunkt.
- Das Feld wieder zu leeren nimmt die Festlegung zurück.

Der Jahrgang entscheidet, **welche** Curricula angeboten werden. Ist er unbekannt, wird
gar keines angeboten — früher waren es alle des Fachs, was einem Abiturkurs auch
Curricula der Mittelstufe vorlegte.

## Das ganze Jahr planen

Viele Lehrkräfte legen ihre Jahresplanung **im September** an — für das ganze Schuljahr,
nicht nur bis Februar. Der Stundenplan gibt das aber nicht her: Wie der Unterricht im 2.
Halbjahr liegt, steht zu Schuljahresbeginn noch nicht fest.

Deshalb können Sie die Stunden des 2. Halbjahres **vorläufig** aus dem jetzigen Raster
erzeugen lassen. Die Option heißt **„Stunden bis zum Schuljahresende anlegen"** und steht
an beiden Stellen, an denen Stunden entstehen: in der Sammelübernahme aus dem Stundenplan
und im Wochenmuster-Dialog. Solange das 1. Halbjahr läuft, ist sie vorbelegt.

Vorläufige Termine sind in der Jahresübersicht als **vorläufig** gekennzeichnet. Sie sind
ganz normale Stunden — Sie können ihnen Einheiten zuordnen, Themen eintragen und
Stundenentwürfe schreiben.

> **Die Annahme dahinter:** Der Stundenplan ändert sich zum Halbjahr fast immer, die
> *Anzahl* der Stunden bleibt aber ungefähr gleich. Deshalb lohnt die Planung auch auf
> Terminen, die sich noch verschieben.

### Was im Februar passiert

Steht der neue Stundenplan, übernehmen Sie ihn wie gewohnt und erzeugen die Stunden des 2.
Halbjahres neu. Dabei geht Ihre Planung **nicht** verloren — sie wird auf die neuen Termine
**umgehängt**:

- **Klassenarbeiten und festgehaltene Stunden behalten ihr Datum.** Eine Arbeit am 12.03.
  bleibt am 12.03.
- **Alles andere wandert in seiner Reihenfolge mit** auf die neuen Termine.
- **Ändert sich der Umfang** einer Stunde (Einzel- ↔ Doppelstunde), wird sie als
  *anzupassen* markiert. Das ist Absicht: Für eine Doppelstunde planen Sie anders als für
  eine Einzelstunde, und diese Entscheidung nimmt Ihnen niemand ab.
- **Nichts wird verworfen.** Was keinen Termin mehr findet, landet auf dem **Parkplatz**.

Bevor es losgeht, sagt Ihnen die Rückfrage, was passieren wird — wie viele Stunden wandern
und wie viele übrig bleiben. Ein Wiederherstellungspunkt wird vorher angelegt; über
**Verlauf** kommen Sie jederzeit zurück.

### Der Parkplatz

Hat der neue Stundenplan **weniger** Termine als der alte, bleibt Planung übrig. Sie
erscheint über der Jahresübersicht unter **„Ohne Termin"** — mit Thema, dem ursprünglichen
Datum („war für den 12.03. geplant") und, wo bekannt, der Bilanz der Einheit („diese
Einheit liegt 2 Stunden über Soll").

Zwei Wege führen von dort weg:

- **Auf eine freie Stunde ziehen.** Der Inhalt wird dort eingeplant.
- **Verwerfen** (Papierkorb). Der Eintrag verschwindet; **der Stundenentwurf bleibt
  erhalten** — Sie finden ihn weiterhin über die Einheit.

Der zweite Weg ist der ehrlichere, wenn eine Einheit ohnehin über Soll liegt: Dann ist
nicht der Termin das Problem, sondern der Umfang. Kürzen Sie die Einheit, statt Stunden
zu suchen, die es nicht gibt.

> **Der Parkplatz lässt sich nicht wegklicken.** Er verschwindet erst, wenn er leer ist.
> Liegen gebliebene Inhalte sollen auffallen, nicht in einem zugeklappten Bereich
> verschwinden.

---

## Stundenentwurf

Den Stundenentwurf öffnen Sie über den Titel einer Stunde oder den Stift in der
Jahresübersicht — oder über den Stundentitel auf der
[Startseite](erste-schritte.md#die-startseite). Gibt es noch keinen Entwurf, entsteht er
beim Klick; eine Unterrichtseinheit braucht es dafür nicht, die Zuordnung können Sie
nachholen. Er besteht aus dem **Verlaufsplan** (Phasen) und einer **Kompetenz-Leiste**.

> 📷 *Screenshot folgt: Stundenentwurf mit Phasentabelle, Zeitbudget-Balken und Kompetenz-Leiste.*
<!-- Ersetzen durch: ![Stundenentwurf](/help-images/unterrichtsplanung/stundenentwurf.png) -->

### Phasen

Jede Phase hat eine **Dauer**, eine **Priorität**, eine **Sozialform/Methode** und
**Material**. Der Zeitbudget-Balken oben zeigt, ob Sie im verfügbaren Zeitrahmen
liegen oder einen Überhang haben.

- **Priorität** (farbiges Pill): *Kern*, *Übung* oder *Vertiefung*. Sie steuert
  später, was bei Zeitnot zuerst gekürzt wird.
- **Sozialform / Methode** (gestapelt: oben Sozialform, darunter Methode): Sie
  tippen frei oder wählen aus dem mitgelieferten Vokabular (z. B. *Partnerarbeit*,
  *Think-Pair-Share*). Tippen schlägt passende Begriffe vor — auch über Synonyme
  (z. B. findet „Ich-Du-Wir" den Eintrag „Think-Pair-Share"). Ein aus dem Vokabular
  gewählter Eintrag ist **anklickbar**: Er öffnet in einem neuen Tab die Beschreibung der
  Methode — wie sie abläuft und worauf es ankommt. Über **„+ … anlegen"**
  legen Sie einen eigenen, zunächst privaten Eintrag an, den Sie später Ihrer
  Fachschaft freigeben können.
- **Material**: Freitext **oder** verknüpfter Material-Knoten. Im Feld tippen Sie
  einen Namen ein; mit **`@`** suchen Sie einen vorhandenen Knoten und verlinken ihn.

> 📷 *Screenshot folgt: Methodenspalte mit gestapelter Sozialform/Methode und der Vorschlagsliste.*
<!-- Ersetzen durch: ![Sozialform und Methode](/help-images/unterrichtsplanung/methode-sozialform.png) -->

### Export

Den fertigen Entwurf exportieren Sie über die Export-Zeile im Kopf als **Markdown**
(zum Kopieren in die Zwischenablage, z. B. für Obsidian), **PDF** oder **DOCX**.

---

## Nachbereiten

Nach einer Stunde halten Sie über **Nachbereiten** fest, welche Phasen erledigt,
offen oder gestrichen wurden, und schreiben optional eine Kurzreflexion. Die
behandelten Kompetenzen fließen damit in den Lernstand der Klasse ein (das nutzen
die Schüler-Assistenten als „Vorwissen").

Blieben **Phasen offen**, bietet der Abschluss-Dialog **„Verschiebe-Dialog starten"**
an — damit übertragen Sie die offenen Inhalte mit dem Assistenten auf die
Folgestunde (siehe unten).

---

## Verschiebe-Assistent

Wenn der Plan durcheinandergerät — Ausfall, verschobene Stunden, offene Phasen oder
nach einer Halbjahres-Regenerierung — hilft der **Verschiebe-Assistent**, Inhalte
neu zu verteilen, Kürzungen vorzuschlagen und sie nach Ihrer Bestätigung anzuwenden.
Er respektiert dabei Fixpunkte (angepinnte Stunden, Klassenarbeiten) und benennt die
Folge jeder Änderung in Zahlen.

Aufgerufen wird er an mehreren Stellen — alle öffnen einen Chat mit Gruppenbezug und
einem vorbefüllten Anliegen:

- **Ausfall:** Wo an einer ausgefallenen Stunde etwas geplant war, stehen **an der Zeile**
  drei Wege — *entfallen lassen*, *verschieben*, *umplanen*. Die beiden letzten öffnen den
  Assistenten. Mehr unter [Wenn Sie ausfallen](#wenn-sie-ausfallen).
- **Verschieben per Drag & Drop:** Ziehen Sie eine **bereits ausgeplante** Stunde,
  öffnet sich der Dialog (statt eines einfachen Tauschs) — der Drop ist ein Auftrag,
  kein direkter Eingriff.
- **Halbjahreswechsel:** Nach dem Neu-Erzeugen des 2. Halbjahres berichtet ein Hinweis,
  was umgehängt wurde. Liegt etwas auf dem Parkplatz, führt er von dort zum Assistenten —
  siehe [Das ganze Jahr planen](#das-ganze-jahr-planen).
- **Überhang-Hinweisleiste:** Hat eine UE mehr Stunden als nötig bis zur nächsten
  Klassenarbeit, erscheint unten eine Leiste mit **„Vorschlag zeigen"** / **„Übernehmen"**.

> 📷 *Screenshot folgt: Überhang-Hinweisleiste am unteren Rand der Jahresübersicht.*
<!-- Ersetzen durch: ![Hinweisleiste](/help-images/unterrichtsplanung/hinweisleiste.png) -->

Jede vom Assistenten übernommene Änderung landet im **Verlauf** und lässt sich dort
oder per „Mach das rückgängig" im Chat **rückgängig** machen.

> **Voraussetzung:** Es muss ein Assistent mit der Fähigkeit *Unterrichtsplanung* und dem
> Verschiebe-Prompt freigeschaltet sein. Das richtet Ihre Schul-Administration ein
> (siehe Admin-Doku „Modelle & Assistenten").

---

## Wenn Sie ausfallen

Fortbildung, Krankheit, ein Termin: Im Jahresplan tragen Sie den Ausfall selbst ein —
über das Menü **⋯** an einer Stunde, Eintrag **„Ich falle aus …"**. Es öffnet sich ein
Dialog mit zwei Fragen:

- **Was ist betroffen?** Nur die gerade bearbeitete Gruppe, oder **alle** Ihre Stunden
  dieses Tages über alle Unterrichtsgruppen hinweg.
- **Warum?** Ein Grund („Fortbildung") ist freiwillig und erscheint an den Stunden.

Einzelne Stunden stellen Sie wie bisher über die Kategorie-Auswahl auf *Ausfall*.

An der Zeile steht danach, **woher** der Ausfall stammt — aus dem Stundenplan, von Ihnen
selbst oder vom Assistenten. Das ist keine Kosmetik: Nur Ihre eigenen Einträge können Sie
auch zurücknehmen; ein Ausfall aus dem Stundenplan gehört dem Abgleich und käme beim
nächsten Lauf ohnehin wieder.

**Ihr Eintrag überlebt den Stundenplan-Abgleich.** Meldet der Stundenplan später dieselbe
Stunde — oft Tage danach —, bleibt Ihre Markierung stehen. Eine Vertretungsangabe kommt
dann **zusätzlich** zu Ihrem Grund in die Notiz; überschrieben wird nichts.

### Was mit den Inhalten geschieht

Nichts — **von allein**. Was aus einem Ausfall folgt, hängt am Fach, an der Einheit und
am Rest des Halbjahres; das kann keine Mechanik entscheiden. Wo an der ausgefallenen
Stunde etwas geplant war, bietet die Zeile deshalb drei Wege an:

| Weg | Was er bedeutet |
|---|---|
| **entfallen lassen** | Der Stoff ist gestrichen, die Einheit rückt nicht nach |
| **verschieben** | Die Inhalte wandern mit dem Assistenten auf die folgenden Stunden |
| **umplanen** | Die Einheit wird neu zugeschnitten — kürzen oder zusammenlegen |

Der Hinweis steht **an der betroffenen Stunde** und bleibt dort, bis Sie entschieden
haben — auch nach dem Neuladen. War an der Stunde nichts geplant, fragt die Plattform
gar nicht erst.

### Zurücknehmen

Auch das Zurücknehmen läuft über den Dialog; die Reichweite wählen Sie dort genauso.

⚠️ Die Rücknahme eines Tages nimmt **alle selbst eingetragenen** Ausfälle dieses Tages
mit — auch solche, die Sie vorher einzeln für eine Stunde gesetzt hatten. Nach dem
Eintragen lässt sich beides nicht mehr unterscheiden; die Rückfrage sagt es Ihnen vorher.
Die Stunden bekommen dabei ihre vorherige Kategorie zurück: Aus einer Klassenarbeit wird
wieder eine Klassenarbeit, nicht bloß „Unterricht".

---

## Was Schüler:innen mitbekommen

Damit Schüler-Assistenten sinnvoll helfen können, erhält ein Chat **mit
Gruppenbezug** einen kleinen Hinweisblock zum **aktuellen Unterricht**: zuletzt
behandeltes und nächstes Thema sowie Termin und Umfang der nächsten Klassenarbeit.

**Nicht** weitergegeben werden interne Planungsfelder wie Ihre Kommentare,
Reflexionen, der Pin-Status oder Phasen-Details. Mehr dazu unter
[Datenschutz](datenschutz.md).

---

## Häufige Fragen

**Muss ich den Assistenten benutzen?**
Nein. Der gesamte Ablauf — Jahresplan, Stundenentwurf, Nachbereiten, Verschieben —
funktioniert vollständig manuell. Der Assistent ist ein Angebot, kein Zwang.

**Was passiert mit einer ausgefallenen Stunde?**
Sie zählt nicht mehr zur Stundenbilanz der UE. Die Zuordnung bleibt zur
Nachvollziehbarkeit erhalten; über die Inhalte entscheiden Sie — siehe
[Wenn Sie ausfallen](#wenn-sie-ausfallen).

**Mein Stundenplan ändert sich zum Halbjahr — verliere ich meine Planung?**
Nein. Beim Neu-Erzeugen des 2. Halbjahres wird die Planung auf die neuen Termine
umgehängt: Klassenarbeiten behalten ihr Datum, alles andere wandert in seiner Reihenfolge
mit. Was keinen Termin mehr findet, liegt auf dem Parkplatz statt im Papierkorb. Mehr
unter [Das ganze Jahr planen](#das-ganze-jahr-planen).

**Ich habe eine Stunde vom Parkplatz verworfen — ist der Entwurf weg?**
Nein. Verworfen wird nur der Eintrag auf dem Parkplatz. Der Stundenentwurf bleibt an
seiner Unterrichtseinheit erhalten.

**Eine Doppelstunde passt nicht auf einen Einzelslot — was tun?**
Der Assistent erkennt das an der Stundenzahl und schlägt vor, die Phasen auf zwei
Stunden zu verteilen oder die Stunde umzubauen, statt sie stillschweigend zu
quetschen.

**Kennt der Assistent die Operatoren des Fachs?**
Ja. In einem fach- oder gruppengebundenen Chat kann der Assistent die offizielle
Operatorenliste des Fachs (handlungsleitende Verben mit Definition und
Anforderungsbereich AFB I–III) abrufen — etwa um eine Aufgabenstellung mit den
korrekten Operatoren zu formulieren oder um zu prüfen, ob eine Schülerlösung den
geforderten Operator angemessen umsetzt. Die Liste selbst finden Sie im
Bildungsplan-View unter dem Reiter **Operatoren**.
