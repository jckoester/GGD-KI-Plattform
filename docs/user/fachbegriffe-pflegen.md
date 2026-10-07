# Fachbegriffe pflegen

Fachbegriffe und Stoffsteckbriefe sind **Schulinhalt, kein Softwareinhalt**. Die
Plattform liefert keine Begriffssätze mit; sie liefert den Weg, auf dem eine Fachschaft
ihre eigenen Begriffe hinein- und wieder herausbekommt.

Diese Seite richtet sich an Lehrkräfte, die diesen Bestand pflegen. Sie beschreibt das
Dateiformat und die beiden Wege — einspielen und wieder herausholen.

> **Wozu der Aufwand?** Ein gepflegter Fachbegriff wirkt an drei Stellen: Er ist über
> Namen und Suchbegriffe auffindbar, er steht in der Sammlung zum Nachschlagen, und ein
> Assistent bekommt ihn ungefragt dazugelegt, wenn eine Frage dazu passt. Die letzte
> Stelle ist die wichtigste: Dort entscheidet Ihr Text, ob die KI die Sprache Ihrer
> Fachschaft spricht oder ihre eigene.

## Zwei Wege, einer davon zurück

Sie können Ihre Begriffe **in Dateien pflegen** (etwa in einem Obsidian-Vault) und
einspielen, oder Sie pflegen sie **in der Oberfläche** im Editor. Beides geht, und Sie
können wechseln: Der Export gibt Ihnen den Bestand jederzeit wieder als Dateien.

Beides finden Sie unter **Fächer → Ihr Fach → „weiterer Kontext"**:

| Schaltfläche | Was sie tut |
|---|---|
| **Aus Dateien** | Dateien wählen, Vorschau ansehen, einspielen |
| **Als Zip** | den ganzen Bestand des Fachs als Dateien sichern |
| **+ Neuer Knoten** | einen einzelnen Eintrag im Editor anlegen |

Einen einzelnen Eintrag holen Sie in seiner Detailansicht über **Als Markdown** heraus.

**Wer darf das?** Lehrkräfte des Fachs — genauer: wer in der **Fachschaftsgruppe** des
Fachs ist. Eine Rolle „Fachschaftsleitung" gibt es nicht; innerhalb der Fachschaft sind
alle gleichberechtigt.

> Die Fachschaftsgruppe übernimmt die Plattform aus Ihrem Schulkonto. Wenn Sie das Fach
> unterrichten, die Schaltfläche aber mit einer Absage antwortet, fehlt diese Gruppe —
> das ist eine Sache der Administration, nicht Ihres Kontos.

## Eine Datei ist ein Eintrag

Am schnellsten geht es mit der **Vorlage**: Im Dialog „Aus Dateien" steht „Vorlage
herunterladen" — ein kleines Paket mit zwei Musterbegriffen, einem Stoffsteckbrief und
einer Kurzfassung dieser Seite. Ändern Sie darin Titel und Inhalt, und Sie haben Ihre
erste eigene Datei.

Eine Datei besteht aus einem **Kopf** zwischen zwei Zeilen aus drei Strichen und einem
**Textteil** in Abschnitten:

```markdown
---
knotentyp: begriff
titel: Energie
fassung: Grundfassung
ab_klasse: 6
bevorzugter_begriff: Energie
aliase: [Energieform, Power]
vertieft_in: ["[[Energie (Erhaltung)]]"]
---

## Definition

Energie ist die Fähigkeit eines Körpers oder Systems, Arbeit zu verrichten.

## Erklärung

…
```

Zeilen im Kopf, die mit `#` beginnen, sind Anmerkungen und werden nicht eingespielt.

### Der Kopf

| Feld | Bedeutung |
|---|---|
| `knotentyp` | `begriff` oder `stoffsteckbrief`. **Pflicht** — fehlt er, gehört die Datei nicht hierher und wird übergangen |
| `titel` | der Anzeigename. Gleichnamige Einträge sind erlaubt und normal |
| `id` | die Kennung, an der die Plattform den Eintrag wiedererkennt (siehe unten) |
| `fassung` | unterscheidet gleichnamige Einträge |
| `ab_klasse` | **nur** bei Begriffen mit mehreren Fassungen |
| `fach` | können Sie weglassen; eingespielt wird in das Fach, dessen Seite Sie offen haben |
| `bevorzugter_begriff` | die Bezeichnung, mit der ein Assistent antwortet |
| `aliase` | Suchbegriffe (siehe unten) |
| `genus`, `plural` | Artikel und Mehrzahl — eine Hilfe für alle, die Deutsch als Zweitsprache lernen |
| `bildungsplan` | Fundstellen, Schema `<Fachkürzel> <Abschnitt> (<Nummer>)` |
| `oberbegriff`, `verwandt`, `voraussetzung`, `vertieft_in` | Verbindungen zu anderen Einträgen, als `[[Dateiname]]` |
| `illustrationen` | Abbildungen mit Datei und Beschreibung |
| `quelle` | woher der Entwurf stammt |

Stoffsteckbriefe haben zusätzlich `formel`, `smiles`, `trivialnamen`, `stoffklasse`,
`teilchen`, `eigenschaften`, `nachweis` und `ghs`.

> **Ein Feld, das die Plattform nicht kennt, verschwindet** — mit einer Zeile im
> Bericht. Der Eintrag selbst bleibt: Über einen falschen Artikel die Definition und
> zehn Verbindungen zu verlieren, stünde in keinem Verhältnis.

### Der Textteil

| Abschnitt | Wohin |
|---|---|
| `## Definition` | der Anfang des Eintrags. Kurz, ein Merksatz |
| `## Erklärung`, `## Beispiele` | der weitere Text, in dieser Reihenfolge |
| `## Abgrenzung` | Verbindungen mit Erklärung. Jede Zeile braucht mindestens einen `[[Verweis]]`; gibt es nichts abzugrenzen: `- (keine)` |
| `## Fehlvorstellungen` | häufige Irrtümer |
| `## Offene Fragen` | wird **nicht** eingespielt — Platz für Notizen an die Fachschaft |

Einen anderen Abschnitt übernimmt die Plattform in den Text, meldet ihn aber als
Abweichung. Das ist Absicht: Ihn stillschweigend fallen zu lassen wäre der schlimmere
Fehler.

## Fünf Dinge, die den Unterschied machen

**1. Das Wichtigste zuerst.** Ein Assistent bekommt von langen Einträgen nur den Anfang
zu sehen. Die Definition sollte höchstens etwa 250 Zeichen lang sein, und der erste
Absatz der Erklärung trägt die zentrale Unterscheidung. Beispiele sind Zusatz für die
Detailansicht — verlassen Sie sich nicht darauf, dass sie ankommen.

**2. Aliase sind Suchbegriffe, keine Antwortbegriffe.** Hier gehört alles hinein, womit
jemand nach dem Begriff *fragt*: Synonyme, Schreibweisen anderer Quellen, Formelzeichen
— **auch unsaubere oder fachlich falsche Wörter**, die Schüler:innen benutzen. Sie
machen den Eintrag auffindbar. Geantwortet wird immer mit `bevorzugter_begriff`.

Ist ein Alias fachlich falsch, gehört die Richtigstellung als Fehlvorstellung daneben.

**3. Fehlvorstellungen im Wortlaut der Schüler:innen.** „Die Blasen in kochendem Wasser
sind Luft" wirkt, „Aggregatzustandsänderung wird häufig fehlinterpretiert" nicht. Ein
Assistent spricht die vermerkten Irrtümer an, wenn sie zur Frage passen — er zählt sie
nicht auf.

**4. Zwei Fassungen statt eines Kompromisses.** Bedeutet ein Begriff in Klasse 8 etwas
anderes als in Klasse 10, legen Sie **zwei** Einträge an, unterscheiden Sie sie über
`fassung` und verbinden Sie sie mit `vertieft_in`. Ein Eintrag, der beides zugleich zu
sagen versucht, ist für beide Jahrgänge falsch.

**5. Keine Verweise nach außen.** „Siehe Buch S. 42" oder „wie im Unterricht besprochen"
kann ein Assistent nicht auflösen.

## Verweise, die ins Leere zeigen

`[[Oxidationsmittel]]` verweist auf die **Datei** dieses Namens in Ihrem Paket. Gibt es
sie noch nicht, entsteht keine Verbindung — und das ist kein Fehler, sondern der
Normalfall beim Aufbau. Der Bericht listet solche Verweise nach Häufigkeit auf: Das ist
Ihre Arbeitsliste für die nächste Runde. Sobald das Ziel da ist, schließt der nächste
Lauf die Lücke von selbst.

## Abbildungen

Legen Sie SVG-Dateien in einen Unterordner `_Abb/`, tragen Sie sie unter
`illustrationen` mit einer **Beschreibung** ein und setzen Sie `![[dateiname.svg]]` an
die Stelle im Text, an der die Abbildung erklärt wird.

Die Beschreibung ist kein Beiwerk. Sie ist das, was ein Assistent über das Bild weiß —
er sieht die Zeichnung nicht — und das, was ein Screenreader vorliest.

> **Nur SVG, und nur ohne Beiwerk.** Zeichnungen mit Skripten, eingebetteten Dokumenten
> oder Verweisen auf fremde Server werden abgewiesen. Der Eintrag wird trotzdem
> eingespielt, nur ohne das Bild; der Grund steht im Bericht.

## Einspielen: erst Vorschau, dann bestätigen

„Aus Dateien" nimmt einzelne `.md`-Dateien, einzelne `.svg` oder ein **Zip-Paket** mit
allem darin. Danach folgt eine **Vorschau** — und bis Sie bestätigen, ist nichts
geschrieben.

Die Vorschau zeigt je Datei, was geschähe:

| | |
|---|---|
| **In der Oberfläche bearbeitet** | siehe unten — hier fragt die Vorschau nach |
| **Nicht eingespielt** | die Datei konnte nicht zugeordnet werden; der Grund steht unter „Hinweise" |
| **Neu** | kommt hinzu |
| **Wird aktualisiert** | die Datei gewinnt |
| **Unverändert** | steht schon genau so im Speicher |

Dazu die Hinweise und die Verweise ins Leere.

> **Einspielen heißt veröffentlichen.** Es gibt keinen Entwurfszustand: Was eingespielt
> ist, sehen alle, die das Fach lesen dürfen — auch Schüler:innen. Der Prüfschritt liegt
> **vor** dem Einspielen. Tragen Ihre Dateien ein Feld `pruefstatus`, wird es nicht
> übernommen; die Vorschau weist aber darauf hin, wenn etwas nicht als geprüft markiert
> ist.

### Wenn jemand in der Oberfläche gearbeitet hat

Hat jemand einen Eintrag seit dem letzten Einspielen im Editor bearbeitet, wird er
**nicht** überschrieben. Er erscheint in der Vorschau ganz oben, und Sie entscheiden je
Zeile: behalten (die Vorgabe) oder mit der Datei überschreiben.

Das ist der Grund, warum diese Gruppe oben steht — sie ist das Einzige, wozu die
Vorschau eine Frage stellt.

### Wann die Einträge auffindbar sind

Über **Namen und Suchbegriffe** sofort. Damit ein Assistent sie auch **inhaltlich**
findet, muss die Plattform sie erst verarbeiten; das beginnt gleich nach dem Einspielen
und dauert wenige Augenblicke. Klappt es einmal nicht — etwa weil der KI-Dienst gerade
nicht erreichbar ist —, holt die Plattform es in der Nacht nach.

## Umbenennen und die Kennung `id`

Jeder Eintrag hat eine **Kennung**, an der die Plattform ihn wiedererkennt. Sie brauchen
sie nicht zu setzen: Beim ersten Einspielen wird eine vergeben (aus Fachkürzel und
Dateiname, etwa `ch-oxidation-sauerstoffaufnahme`), und der Export trägt sie in die
Datei ein.

> ⚠️ **Solange keine `id` in Ihrer Datei steht, hängt die Identität am Dateinamen.**
> Benennen Sie die Datei dann um, entsteht beim nächsten Einspielen ein **zweiter**
> Eintrag. Wollen Sie umbenennen, tragen Sie vorher die Kennung ein, die der Bericht
> nennt — oder exportieren Sie einmal, dann steht sie überall drin.

Erlaubt sind Kleinbuchstaben, Ziffern und Bindestriche. Eine Kennung, die davon
abweicht, wird verworfen und gemeldet; die Datei wird trotzdem gelesen.

## Herausholen: Export

„Als Zip" gibt Ihnen den Bestand des Fachs als Dateien — dasselbe Format, das der Import
liest. Ein einzelner Eintrag geht über „Als Markdown" in seiner Detailansicht.

> ⚠️ **Der Export ersetzt Ihren Arbeitsordner nicht.** Er ist der Stand des
> Wissensspeichers, nicht Ihre Datei von vorgestern. Nicht mitkommen können:
>
> - **Verweise auf Begriffe, die es noch nicht gibt.** Sie sind zu keiner Verbindung
>   geworden und daher im Speicher nicht abgebildet. Wer damit einen gepflegten Ordner
>   überschreibt, verliert genau die Arbeitsliste für die Breite.
> - `pruefstatus`, Verweise im Fließtext und der Abschnitt „Offene Fragen".
>
> Dieselbe Liste liegt dem Paket als `_Export-Hinweise.txt` bei. Zum Sichern und
> Weitergeben taugt der Export; zum Zurückspielen in einen gepflegten Ordner erst, wenn
> der Bestand vollständig ist.

## Was schiefgehen kann

| Meldung | Was zu tun ist |
|---|---|
| „nicht lesbar" | Der Kopf ist kaputt — meist ein Anführungszeichen zu viel. Enthält ein Wert selbst Anführungszeichen, nehmen Sie einfache: `'…'` |
| „Fach „X" unbekannt" / „importiert wird nach Y" | Die Datei nennt ein anderes Fach. Zeile löschen oder das richtige Fach öffnen |
| „keine `id` ableitbar" | Der Dateiname besteht nur aus Sonderzeichen. Datei umbenennen oder `id:` setzen |
| „Kennung … gehört schon zu …" | Zwei Dateien beanspruchen dieselbe Kennung |
| „Abbildung abgelehnt" | Die SVG enthält Skripte oder Verweise nach außen |
| „größer als …" / „entpackt … MB" | Das Paket ist zu groß. In mehreren Läufen einspielen |

## Verwandte Seiten

- [Kontextspeicher](kontext.md) — wie Bausteine im Chat wirken
- [Fächer und Gruppen](faecher.md)
