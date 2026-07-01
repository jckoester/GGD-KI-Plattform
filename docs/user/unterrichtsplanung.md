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

- **Unterrichtseinheiten (UE) anlegen** und mit Lehrplan-Kapiteln verknüpfen. Die
  Leiste oben zeigt pro UE die **Stundenbilanz**: Soll-Stunden aus dem Lehrplan
  gegen die zugewiesenen Slots.
- **Slots einer UE zuordnen**, Themen direkt eintragen, **Kategorie** ändern
  (Unterricht, Prüfung, Puffer, Ausfall, Vertretung), Stunden **anpinnen** (Fixpunkte
  wie Klassenarbeiten) und Kommentare hinterlegen.
- **Klick auf eine UE** in der oberen Leiste springt zur ersten Stunde dieser UE.
- **Klick auf den Titel** einer geplanten Stunde öffnet deren Stundenentwurf.
- Beim Öffnen scrollt die Übersicht automatisch zur **aktuellen Woche**.
- Über **Wochenmuster** legen Sie fest, an welchen Wochentagen die Gruppe
  Unterricht hat, und erzeugen daraus die Slots eines Halbjahres.
- Über **Verlauf** machen Sie Änderungen rückgängig (jede Änderung wird gesichert).

---

## Stundenentwurf

Den Stundenentwurf öffnen Sie über den Titel einer Stunde oder den Stift in der
Jahresübersicht. Er besteht aus dem **Verlaufsplan** (Phasen) und einer
**Kompetenz-Leiste**.

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
  (z. B. findet „Ich-Du-Wir" den Eintrag „Think-Pair-Share"). Über **„+ … anlegen"**
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

- **Ausfall:** Setzen Sie eine Stunde **mit Inhalt** auf *Ausfall*, erscheint über der
  Tabelle ein Banner **„Inhalte verschieben (Assistent)"**.
- **Verschieben per Drag & Drop:** Ziehen Sie eine **bereits ausgeplante** Stunde,
  öffnet sich der Dialog (statt eines einfachen Tauschs) — der Drop ist ein Auftrag,
  kein direkter Eingriff.
- **Halbjahreswechsel:** Nach dem Neu-Generieren des 2. Halbjahres weist ein Hinweis
  darauf hin, die Zuordnung neu aufzubauen.
- **Überhang-Hinweisleiste:** Hat eine UE mehr Stunden als nötig bis zur nächsten
  Klassenarbeit, erscheint unten eine Leiste mit **„Vorschlag zeigen"** / **„Übernehmen"**.

> 📷 *Screenshot folgt: Überhang-Hinweisleiste am unteren Rand der Jahresübersicht.*
<!-- Ersetzen durch: ![Hinweisleiste](/help-images/unterrichtsplanung/hinweisleiste.png) -->

Jede vom Assistenten übernommene Änderung landet im **Verlauf** und lässt sich dort
oder per „Mach das rückgängig" im Chat **rückgängig** machen.

> **Voraussetzung:** Es muss ein Assistent mit Planungs-Werkzeugen und dem
> Verschiebe-Prompt freigeschaltet sein. Das richtet Ihre Schul-Administration ein
> (siehe Admin-Doku „Modelle & Assistenten").

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
Nachvollziehbarkeit erhalten; die Inhalte verschieben Sie bei Bedarf (manuell oder
per Assistent).

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
