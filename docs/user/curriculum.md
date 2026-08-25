# Schulcurriculum

*(nur für Lehrkräfte)*

Das Schulcurriculum ist die schuleigene Umsetzung des Bildungsplans: Es legt fest, in
welcher Reihenfolge, mit welchem Zeitansatz und mit welchen Schwerpunkten die Kompetenzen
eines Fachs unterrichtet werden.

> **Bildungsplan ≠ Curriculum.** Der **Bildungsplan** ist die Landesvorgabe — er steht fest
> und lässt sich hier nicht ändern. Das **Curriculum** ist Ihre Fachschaftsarbeit darauf:
> Kapitel, Lernsequenzen, Konkretisierungen, Material.

Sie erreichen Curricula über **Wissen → Curricula** oder direkt von der Fachseite aus.

---

## Wer darf was

Ein Curriculum gehört der **Fachschaft**, nicht einer einzelnen Person.

| | |
|---|---|
| **Ansehen** | alle Lehrkräfte |
| **Bearbeiten** | Mitglieder der Fachschaft, dazu Admins |

Wenn Sie ein Curriculum nur lesen können, obwohl es Ihr Fach ist, fehlt Ihnen
wahrscheinlich die Fachschaftsmitgliedschaft — das klärt die Administration.

---

## Ein Curriculum anlegen

**Wissen → Curricula → Neu**, dann zwei Angaben:

1. **Bildungsplan** des Fachs auswählen. Damit steht auch die Fassung fest (z. B. BP 2016
   oder die überarbeitete Fassung V2).
2. **Jahrgangsstufe oder Stufenband** eintragen — freie Eingabe: `7`, `7/8`, `5–6`.

Den Rest bauen Sie im Editor auf.

> Erscheint Ihr Fach nicht in der Auswahl, ist sein Bildungsplan in dieser Installation
> noch nicht eingelesen. Das ist eine Aufgabe der Administration, keine Einstellung, die
> Sie ändern können.

---

## Aufbau: Kapitel, Lernsequenzen, Einträge

```
Curriculum  (Fach + Jahrgangsband)
└── Kapitel            z. B. „Kreise und Körper"        · Stundenansatz
    └── Lernsequenz    z. B. „Satz des Pythagoras"      · Stundenansatz
        └── Eintrag    Kompetenzen + Konkretisierung + Hinweise + Material
```

**Kapitel** gliedern das Schuljahr, **Lernsequenzen** die Kapitel. Ein Kapitel lässt sich
über den Pfeil im Kopf **einklappen** — bei langen Curricula die schnellste Art, den
Überblick zu behalten.

Die **Stundenansätze** addiert die Ansicht mit; oben sehen Sie die Gesamtsumme. So merken
Sie früh, wenn die Planung nicht ins Schuljahr passt.

---

## Kompetenzen verknüpfen

In jedem Eintrag verknüpfen Sie Kompetenzen des Bildungsplans:

- **IK** — inhaltsbezogene Kompetenzen (was inhaltlich behandelt wird)
- **PK** — prozessbezogene Kompetenzen (welche Arbeitsweisen geübt werden)

Beide Felder durchsuchen den Bildungsplan **Ihres Fachs in der passenden Fassung** — Sie
müssen sich also nicht darum kümmern, ob eine Kompetenz zur richtigen Edition gehört.

**„Partiell" ankreuzen**, wenn eine Kompetenz an dieser Stelle nur teilweise bedient wird.
Das ist kein Schönheitsfehler, sondern die ehrliche Auskunft: Dieselbe Kompetenz taucht
dann an mehreren Stellen auf, und keine behauptet, sie allein abzudecken.

### Hinweise und Leitperspektiven

Im Feld **Hinweise** schreiben Sie Freitext. Mit `@` verweisen Sie zusätzlich auf
**Leitperspektiven** und ihre Aspekte, mit `#` auf Kompetenzen **anderer Fächer** — das ist
der Weg, fächerverbindende Bezüge sichtbar zu machen.

### Material

Im Feld **Material** steht Freitext, Links — und mit `@` Verweise auf Bausteine aus dem
[Kontextspeicher](kontext.md): Arbeitsblätter, Aufgaben, Präsentationen, Methodenblätter
und fachliche Konzepte.

Bildungsplan-Kompetenzen erscheinen hier bewusst **nicht** — dafür gibt es die IK- und
PK-Felder. Zwei Wege für dieselbe Verknüpfung wären nur verwirrend.

---

## Titel und Jahrgangsband ändern

Beides ändern Sie im Bearbeitungsmodus direkt im Kopf: den **Titel** durch Klick darauf,
das **Jahrgangsband** im Feld daneben.

Die **Bildungsplan-Fassung** steht dort nur zur Anzeige. Sie lässt sich nicht frei
umstellen, weil an ihr sämtliche Kompetenzverweise hängen — ein Wechsel per Hand würde sie
stillschweigend auf eine andere Fassung zeigen lassen. Dafür gibt es den geprüften Weg im
nächsten Abschnitt.

---

## Auf eine neue Bildungsplan-Fassung wechseln

Erscheint eine überarbeitete Fassung des Bildungsplans, wandert sie **stufenweise** ein —
nicht in allen Jahrgängen gleichzeitig. Ihr Curriculum wird deshalb **nicht** automatisch
umgestellt.

In der Ansicht gibt es dafür **„Bildungsplan aktualisieren"**. Sie bekommen zuerst eine
**Vorschau**, erst danach passiert etwas. Drei mögliche Ergebnisse:

| Ergebnis | Bedeutung |
|---|---|
| **Keine Aktualisierung nötig** | Das Curriculum liegt schon auf der aktuellen Fassung. |
| **Aktualisieren** | Die neue Fassung gilt für Ihr ganzes Jahrgangsband — das Curriculum wird umgestellt. |
| **Kopie anlegen** | Die neue Fassung gilt erst für einen Teil des Bandes. Es entsteht eine **Kopie** auf der neuen Fassung; das Original bleibt für die Jahrgänge, die noch nicht gewechselt haben. |

**Was dabei mit den Kompetenzen geschieht:**

- Gleiche Nummer, im Wesentlichen gleicher Text → wird auf die neue Fassung umgehängt.
- Nicht mehr vorhanden oder inhaltlich geändert → bleibt stehen und wird **durchgestrichen
  mit ⚠ markiert**.

Die Markierung ist eine Bitte um Prüfung, kein Fehler: Sie müssen entscheiden, wodurch die
Kompetenz zu ersetzen ist. Nichts wird stillschweigend gelöscht.

---

## Exportieren

Über **Export** erhalten Sie das Curriculum als:

- **PDF** — zum Ausdrucken, für Konferenzen und die Fachschaftsakte
- **YAML** — die maschinenlesbare Fassung

Das YAML ist die einzige Form, die sich wieder einlesen lässt — etwa um ein Curriculum in
eine Übungsumgebung zu übertragen. Das erledigt die Administration
([Runbook](../runbooks/curriculum-transfer.md)).

---

## Häufige Fragen

**Ich sehe eine Kompetenz durchgestrichen mit ⚠. Habe ich etwas falsch gemacht?**
Nein. Das Curriculum wurde auf eine neue Bildungsplan-Fassung aktualisiert, und diese
Kompetenz gibt es dort nicht mehr oder sie wurde geändert. Ersetzen Sie sie, wenn Sie
Gelegenheit haben.

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

**Wer sieht mein Curriculum?**
Alle Lehrkräfte der Schule. Es ist ein Fachschaftsdokument, kein persönlicher Entwurf.
