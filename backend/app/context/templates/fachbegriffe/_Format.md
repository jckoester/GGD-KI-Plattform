# Fachbegriffe pflegen — Kurzfassung

Diese Datei beginnt mit einem Unterstrich und wird beim Einspielen übergangen. Sie
gehört zur Vorlage, nicht zum Bestand.

**Ausführlich** steht alles in der Hilfe der Plattform unter „Fachbegriffe pflegen".
Hier nur das Nötigste zum Loslegen.

## Eine Datei ist ein Eintrag

Oben ein Kopf zwischen zwei Zeilen aus drei Strichen (`---`), darunter der Text in
Abschnitten mit `##`. Zeilen im Kopf, die mit `#` beginnen, sind Anmerkungen.

## Der Kopf

| Feld | Bedeutung |
|---|---|
| `knotentyp` | `begriff` oder `stoffsteckbrief` — **Pflicht** |
| `titel` | Anzeigename. Gleichnamige Einträge sind erlaubt |
| `id` | Kennung, an der der Eintrag wiedererkannt wird. Wird beim ersten Einspielen vergeben; der Export trägt sie ein |
| `fassung` | unterscheidet gleichnamige Einträge („Grundfassung" / „Erhaltung") |
| `ab_klasse` | nur bei Begriffen mit mehreren Fassungen |
| `bevorzugter_begriff` | die Bezeichnung, mit der der Assistent antwortet |
| `aliase` | **Suchbegriffe**, auch schiefe. Keine Antwortbegriffe |
| `genus`, `plural` | Artikel und Mehrzahl |
| `bildungsplan` | Fundstellen, Schema `<Fachkürzel> <Abschnitt> (<Nr.>)` |
| `oberbegriff`, `verwandt`, `voraussetzung`, `vertieft_in` | Verweise `[[Dateiname]]` |
| `illustrationen` | Datei unter `_Abb/` plus Beschreibung |
| `quelle` | Herkunft des Entwurfs |

Stoffsteckbriefe zusätzlich: `formel`, `smiles`, `trivialnamen`, `stoffklasse`,
`teilchen`, `eigenschaften`, `nachweis`, `ghs`.

## Der Text

| Abschnitt | Wohin |
|---|---|
| `## Definition` | Anfang des Eintrags. Kurz, ein Merksatz |
| `## Erklärung`, `## Beispiele` | weiter im Eintrag |
| `## Abgrenzung` | Verbindungen mit Hinweis. Jede Zeile braucht mindestens einen `[[Verweis]]`; ohne: `- (keine)` |
| `## Fehlvorstellungen` | Irrtümer im Wortlaut der Schüler:innen |
| `## Offene Fragen` | wird **nicht** eingespielt |

## Fünf Schreibregeln

1. **Das Wichtigste zuerst.** Ein Assistent bekommt nur den Anfang zu sehen — die
   Definition höchstens etwa 250 Zeichen, danach die zentrale Unterscheidung.
2. **Heißt der Begriff verbreitet auch anders?** Dann gehört ein Satz dazu in die
   Definition.
3. **Was richtiggestellt werden muss, gehört unter „Fehlvorstellungen".** Nur dort
   kommt es sicher an.
4. **Beispiele sind Zusatz**, kein Träger zentraler Aussagen.
5. **Keine Verweise nach außen** („siehe Buch S. 42") — der Assistent kann ihnen nicht
   folgen.
