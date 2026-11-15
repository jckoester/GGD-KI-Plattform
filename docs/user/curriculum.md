# Schulcurriculum

*(nur für Lehrkräfte)*

Das Schulcurriculum ist die schuleigene Umsetzung des Bildungsplans: Es legt fest, in
welcher Reihenfolge, mit welchem Zeitansatz und mit welchen Schwerpunkten die Kompetenzen
eines Fachs unterrichtet werden.

> **Bildungsplan ≠ Curriculum.** Der **Bildungsplan** ist die Landesvorgabe — er steht fest
> und lässt sich hier nicht ändern. Das **Curriculum** ist eure Fachschaftsarbeit darauf:
> Kapitel, Lernsequenzen, Konkretisierungen, Material.

Du erreichst Curricula über **Wissen → Curricula** oder direkt von der Fachseite aus.

---

## Wer darf was

Ein Curriculum gehört der **Fachschaft**, nicht einer einzelnen Person.

| | |
|---|---|
| **Ansehen** | alle Lehrkräfte |
| **Bearbeiten** | Mitglieder der Fachschaft, dazu Admins |

Wenn du ein Curriculum nur lesen kannst, obwohl es dein Fach ist, fehlt dir
wahrscheinlich die Fachschaftsmitgliedschaft — das klärt die Administration.

---

## Ein Curriculum anlegen

**Wissen → Curricula → Neu**, dann zwei Angaben:

1. **Bildungsplan** des Fachs auswählen. Damit steht auch die Fassung fest (z. B. BP 2016
   oder die überarbeitete Fassung V2).
2. **Jahrgangsstufe oder Stufenband** eintragen — freie Eingabe: `7`, `7/8`, `5–6`.

Den Rest baust du im Editor auf.

> Erscheint dein Fach nicht in der Auswahl, ist sein Bildungsplan in dieser Installation
> noch nicht eingelesen. Das ist eine Aufgabe der Administration, keine Einstellung, die
> du ändern kannst.

---

## Aufbau: Kapitel, Lernsequenzen, Einträge

```
Curriculum  (Fach + Jahrgangsband)
└── Kapitel            z. B. „Kreise und Körper"        · Stundenansatz
    └── Lernsequenz    z. B. „Satz des Pythagoras"      · Stundenansatz
        └── Eintrag    Kompetenzen + Konkretisierung + Begriffe + Fachmethoden + Hinweise + Material
```

**Kapitel** gliedern das Schuljahr, **Lernsequenzen** die Kapitel. Ein Kapitel lässt sich
über den Pfeil im Kopf **einklappen** — bei langen Curricula die schnellste Art, den
Überblick zu behalten.

Die **Stundenansätze** addiert die Ansicht mit; oben siehst du die Gesamtsumme. So merkst
du früh, wenn die Planung nicht ins Schuljahr passt.

---

## Kompetenzen verknüpfen

In jedem Eintrag verknüpfst du Kompetenzen des Bildungsplans:

- **IK** — inhaltsbezogene Kompetenzen (was inhaltlich behandelt wird)
- **PK** — prozessbezogene Kompetenzen (welche Arbeitsweisen geübt werden)

Beide Felder durchsuchen den Bildungsplan **deines Fachs in der passenden Fassung** — du
musst dich also nicht darum kümmern, ob eine Kompetenz zur richtigen Edition gehört.

**„Partiell" ankreuzen**, wenn eine Kompetenz an dieser Stelle nur teilweise bedient wird.
Das ist kein Schönheitsfehler, sondern die ehrliche Auskunft: Dieselbe Kompetenz taucht
dann an mehreren Stellen auf, und keine behauptet, sie allein abzudecken.

### Hinweise und Leitperspektiven

Im Feld **Hinweise** schreibst du Freitext. Mit `@` verweist du zusätzlich auf
**Leitperspektiven** und ihre Aspekte, mit `#` auf Kompetenzen **anderer Fächer** — das ist
der Weg, fächerverbindende Bezüge sichtbar zu machen.

### Material

Im Feld **Material** steht Freitext, Links — und mit `@` Verweise auf Bausteine aus dem
[Bibliothek](bibliothek.md): Arbeitsblätter, Aufgaben, Präsentationen, Methodenblätter
und fachliche Konzepte.

Bildungsplan-Kompetenzen erscheinen hier bewusst **nicht** — dafür gibt es die IK- und
PK-Felder. Zwei Wege für dieselbe Verknüpfung wären nur verwirrend.

---

## Begriffe und Fachmethoden

Unter der **Konkretisierung** jedes Eintrags stehen zwei Zeilen: **Begriffe** — die
Fachbegriffe, die die Einheit tragen soll — und **Fachmethoden** — die fachspezifischen
Verfahren, etwa „Titration" oder „Gedichtanalyse". Beides trägst du als Namen ein: tippen,
mit **Enter** übernehmen. Ein Begriff muss dafür noch nicht in der Bibliothek stehen.

### Begriffe

Beim Tippen schlägt die Plattform passende Begriffe aus der Bibliothek deines Fachs und
seiner Bezugsfächer vor. **Enter** übernimmt einen Vorschlag, der genau so heißt, oder den
mit den Pfeiltasten gewählten — sonst den Namen, wie du ihn getippt hast.

Die Farbe zeigt, ob es den Begriff gibt:

| Darstellung | Bedeutung |
|---|---|
| violett, verlinkt | Den Begriff gibt es in der Bibliothek (auch über einen anderen Namen). Aus einem Bezugsfach steht dessen Name dabei. |
| gestrichelt | Platzhalter: Den Begriff gibt es noch nicht. |
| gelb | Es gibt mehrere Begriffe dieses Namens (verschiedene Fassungen). Im Bearbeitungsmodus klickst du darauf und wählst die gemeinte. |

Gespeichert wird der **Name**, keine feste Verknüpfung. Legt die Fachschaft einen
fehlenden Begriff später an, erscheint er von selbst violett — am Curriculum musst du
nichts ändern. Wird ein Begriff in der Bibliothek umbenannt, bleibt der alte Name als
Alias erhalten; das Curriculum findet ihn weiter.

### Fehlende Begriffe anlegen

Zwei Wege, die sich ergänzen:

- **Einzeln:** Am gestrichelten Begriff steht **anlegen** — der Link öffnet das Formular für
  einen neuen Begriff mit dem Namen schon eingetragen. Im Bearbeitungsmodus geht er in einem
  neuen Tab auf, damit nichts Ungespeichertes verloren geht; zurück im Curriculum ist der
  Begriff dann violett. Den Link sehen Mitglieder der Fachschaft des Fachs; alle anderen
  sehen, dass die Fachschaft ihn anlegen kann.
- **Gesammelt:** Über der Tabelle zeigt **„… Begriffe fehlen in der Bibliothek"** aufgeklappt
  jeden fehlenden Begriff mit Anzahl und Kapiteln. Darunter zwei Downloads: die **Liste** zum
  Verteilen in der Fachschaft und **Gerüste (Zip)** — je Begriff eine Datei im Format der
  Fachbegriffe. Definition eintragen, dann das Bündel unter Fachbegriffe einspielen
  ([Fachbegriffe pflegen](fachbegriffe-pflegen.md)). Ein Gerüst ohne Definition weist der
  Import ab, damit kein leerer Begriff in der Sammlung landet.

### Fachmethoden

Fachmethoden sind vorerst nur Namen — es gibt dafür noch keine eigenen Bausteine. Beim
Tippen schlägt die Plattform vor, was in den Curricula deines Fachs schon als Fachmethode
steht, mit der Zahl der Nennungen. So entsteht nicht „Titration", „Titrieren" und
„Säure-Base-Titration" nebeneinander. Ein Name darf auch in beiden Zeilen stehen: als
Begriff (kennen) und als Fachmethode (beherrschen).

### In der Unterrichtsplanung

Ist eine Unterrichtseinheit einem Kapitel zugeordnet, nutzen beide Wege der Planung die
Begriffe dieses Kapitels: Die Leiste **„Kompetenzen und Fachbegriffe"** im Stundenentwurf
schlägt die vor, die die Stunde behandelt, und der Stundenassistent stützt sich darauf,
wenn du ihn nach den Begriffen der Stunde fragst.

Hast du einen **eigenen Stundenassistenten**, kennt er die Anleitung dazu noch nicht: Leg ihn
neu an, damit er den aktuellen schulweiten Prompt übernimmt
([Ein eigener Stundenassistent](unterrichtsplanung.md#ein-eigener-stundenassistent)).

---

## Titel und Jahrgangsband ändern

Beides änderst du im Bearbeitungsmodus direkt im Kopf: den **Titel** durch Klick darauf,
das **Jahrgangsband** im Feld daneben.

Die **Bildungsplan-Fassung** steht dort nur zur Anzeige. Sie lässt sich nicht frei
umstellen, weil an ihr sämtliche Kompetenzverweise hängen — ein Wechsel per Hand würde sie
stillschweigend auf eine andere Fassung zeigen lassen. Dafür gibt es den geprüften Weg im
nächsten Abschnitt.

---

## Auf eine neue Bildungsplan-Fassung wechseln

Erscheint eine überarbeitete Fassung des Bildungsplans, wandert sie **stufenweise** ein —
nicht in allen Jahrgängen gleichzeitig. Dein Curriculum wird deshalb **nicht** automatisch
umgestellt.

In der Ansicht gibt es dafür **„Bildungsplan aktualisieren"**. Du bekommst zuerst eine
**Vorschau**, erst danach passiert etwas. Drei mögliche Ergebnisse:

| Ergebnis | Bedeutung |
|---|---|
| **Keine Aktualisierung nötig** | Das Curriculum liegt schon auf der aktuellen Fassung. |
| **Aktualisieren** | Die neue Fassung gilt für dein ganzes Jahrgangsband — das Curriculum wird umgestellt. |
| **Kopie anlegen** | Die neue Fassung gilt erst für einen Teil des Bandes. Es entsteht eine **Kopie** auf der neuen Fassung; das Original bleibt für die Jahrgänge, die noch nicht gewechselt haben. |

**Was dabei mit den Kompetenzen geschieht:**

- Gleiche Nummer, im Wesentlichen gleicher Text → wird auf die neue Fassung umgehängt.
- Nicht mehr vorhanden oder inhaltlich geändert → bleibt stehen und wird **durchgestrichen
  mit ⚠ markiert**.

Die Markierung ist eine Bitte um Prüfung, kein Fehler: Du musst entscheiden, wodurch die
Kompetenz zu ersetzen ist. Nichts wird stillschweigend gelöscht.

---

## Exportieren

Über **Export** erhältst du das Curriculum als:

- **PDF** — zum Ausdrucken, für Konferenzen und die Fachschaftsakte; Begriffe und
  Fachmethoden stehen als eigene Zeilen unter der Konkretisierung
- **DOCX** (Word) oder **ODT** (LibreOffice) — zum Weiterbearbeiten außerhalb der Plattform,
  im Querformat und mit Formeln als bearbeitbare Formeln
- **YAML** — die maschinenlesbare Fassung; Begriffe und Fachmethoden gehen als Namen mit
  und werden in einer anderen Plattform gegen deren Bibliothek abgeglichen

Das YAML ist die einzige Form, die sich wieder einlesen lässt. Änderungen in Word oder
LibreOffice kommen nicht zurück in die Plattform — etwa um ein Curriculum in
eine Übungsumgebung zu übertragen. Das erledigt die Administration
([Runbook](../runbooks/curriculum-transfer.md)).

---

## Häufige Fragen

**Ich sehe eine Kompetenz durchgestrichen mit ⚠. Habe ich etwas falsch gemacht?**
Nein. Das Curriculum wurde auf eine neue Bildungsplan-Fassung aktualisiert, und diese
Kompetenz gibt es dort nicht mehr oder sie wurde geändert. Ersetze sie, wenn du
Gelegenheit hast.

**Kann ich ein Curriculum kopieren, statt es neu anzulegen?**
Beim Fassungswechsel entsteht in einem Fall automatisch eine Kopie (siehe oben). Ein freies
Duplizieren gibt es derzeit nicht.

**Warum kann ich die Bildungsplan-Fassung nicht einfach umstellen?**
Weil daran alle Kompetenzverweise hängen. Der Weg über „Bildungsplan aktualisieren"
vergleicht jede Kompetenz einzeln und markiert, was nicht passt — das Umstellen von Hand
täte das nicht.

**Ich habe versehentlich etwas gelöscht.**
Änderungen werden beim Speichern übernommen; eine Rücknahme gibt es im Curriculum-Editor
nicht. Bei größeren Umbauten lohnt sich vorher ein YAML-Export als Sicherung.

**Warum ist ein Begriff gestrichelt, obwohl es ihn gibt?**
Entweder heißt er in der Bibliothek anders — dann lohnt ein Alias am Begriff —, oder er
gehört zu einem Fach, das weder dein Fach noch eines seiner Bezugsfächer ist. Bei gelben
Begriffen gibt es mehrere Fassungen; wähle die gemeinte.

**Wer sieht mein Curriculum?**
Alle Lehrkräfte der Schule. Es ist ein Fachschaftsdokument, kein persönlicher Entwurf.
