# Fachbegriffe aus einem Obsidian-Ordner einspielen

Aus Markdown-Dateien werden `begriff`- und `stoffsteckbrief`-Knoten samt Kanten. Es ist
ein **Einspielvorgang**, kein Synchronisierungsdienst: Er läuft, wenn jemand ihn startet.

**Die Arbeit liegt in `app/context/fachbegriffe_import.py`**, nicht im Skript.
`backend/scripts/seed_fachbegriffe.py` ist die Admin-Hülle: Ordner einlesen, Service
rufen, Bericht ausgeben. Den zweiten Weg auf denselben Kern baut Paket 10 als
Upload-Dialog für die Fachschaften.

⚠️ **Die Eingabe des Service ist ein Bündel, kein Ordner** — `Pfad → Bytes`. Wo die
Bytes herkommen, entscheidet der Aufrufer: Das Skript liest ein Verzeichnis, der
Endpunkt entpackt ein Zip. Der Kern kennt kein Dateisystem, und ein Test hält fest, dass
beide Wege auf demselben Bündel **dieselbe Bilanz** ergeben.

> **Was in eine Datei gehört, steht nicht hier.** Die inhaltlichen Regeln — wie eine
> Definition aussieht, was eine Fehlvorstellung ist, wann ein Steckbrief statt eines
> Begriffs — pflegt die Fachschaft in `_Format.md` im Vault. Diese Seite beschreibt die
> **Schnittstelle**: welche Schlüssel das Skript liest, wie es sich bei einem zweiten
> Lauf verhält und was sein Bericht bedeutet.

## Aufruf

```bash
cd backend
venv/bin/python scripts/seed_fachbegriffe.py --quelle "/Pfad/zum/Ordner" --fach CH
venv/bin/python scripts/seed_fachbegriffe.py --quelle … --fach CH --dry-run
venv/bin/python scripts/seed_fachbegriffe.py --quelle … --fach CH --ueberschreiben
```

`--fach` gilt nur für Dateien **ohne** eigene `fach:`-Angabe; die Angabe in der Datei hat
Vorrang. Nimmt Kürzel, Slug oder Namen.

**Danach die Einbettung nachziehen** — das Skript sagt es am Ende selbst:

```bash
venv/bin/python scripts/embedding_backfill.py --content-type begriff --content-type stoffsteckbrief
```

⚠️ Ohne diesen zweiten Lauf sind geänderte Knoten **nicht auffindbar**: Das Skript
verwirft den Vektor, dessen Eingabe sich geändert hat, und legt keinen neuen an.

## Was aus einer Datei gelesen wird

**Welche Dateien überhaupt gelesen werden:** `*.md` auf oberster Ebene, ohne führenden
Unterstrich. ⚠️ Der Unterstrich ist nicht Kosmetik: `_Format.md` hat kein Frontmatter und
liefe sonst bei **jedem** Lauf als „nicht lesbar" in den Bericht — und ein Bericht, in dem
immer dieselbe Warnung steht, wird nicht mehr gelesen. Alles unter `_Abb/` wird nicht
übersprungen, sondern über die Pfadangabe in `illustrationen` gesucht.

**Aus dem Frontmatter:** Steuerschlüssel (`id`, `knotentyp`, `titel`, `fach`, `aliase`,
`bildungsplan`) und Beziehungen (`oberbegriff`, `verwandt`, `voraussetzung`,
`vertieft_in`, `teilchen`, `ghs`) werden ausgewertet und **nicht** an den Knoten
geschrieben.

⚠️ **Für die Metadaten gilt eine Whitelist:** übernommen wird, was im Feldschema des
Typs steht (`app/context/taxonomy.yaml`), plus `eigenschaften`, `ghs` und
`illustrationen`. Alles andere fällt weg — stillschweigend, weil es Steuerinformation
ist. Das ist die Stelle, an der ein Feld verschwindet, das jemand im Vault erfunden hat
(und die Stelle, an der ein gestrichenes Feld beim nächsten Lauf von selbst aus der
Datenbank verschwindet).

**Aus dem Text**, nach Überschriften:

| Abschnitt | Wohin |
|---|---|
| vor der ersten Überschrift, oder `### Definition` | `content` |
| `### Erklärung`, `### Beispiele` | `content`, in Dateireihenfolge |
| `### Fehlvorstellungen` | `metadata.fehlvorstellungen` (Liste) |
| `### Abgrenzung` | Kanten `related_to` mit `art: abgrenzung` und `hinweis` |
| `### Offene Fragen` | verworfen — Arbeitsnotizen der Fachschaft |

`{{abbildung:datei.svg}}` im Text ist der Platzhalter für ein Bild aus
`illustrationen`; die Oberfläche setzt dort das SVG ein, das Modell bekommt die
`beschreibung`.

## Woran ein Knoten wiedererkannt wird

An seiner **`id`** — einer Kennung aus Kleinbuchstaben, Ziffern und Bindestrichen, je
Fach eindeutig, im Frontmatter der Datei:

```yaml
id: ch-oxidation-sauerstoffaufnahme
```

⚠️ **Bis Paket 9 war es der Dateiname**, und beim Pflegen im Vault ist Umbenennen keine
Ausnahme: Sobald die zweite Fassung dazukommt, wird aus `Oxidation.md` eben
`Oxidation (Sauerstoffaufnahme).md`. Der nächste Lauf legte dann einen **zweiten**
Knoten an, und beide standen in der Sammlung, die Schüler:innen sehen. Gemessen am
Pilot: umbenennen ohne `id` ergibt „1 neu, 35 unverändert", mit `id` „0 neu, 36
unverändert".

**Fehlt die `id`**, leitet der Lauf sie aus Fachkürzel und Dateiname ab —
`CH` + `Oxidation (Sauerstoffaufnahme)` → `ch-oxidation-sauerstoffaufnahme`; Umlaute
werden ausgeschrieben (`ä`→`ae`, `ß`→`ss`), alles Übrige wird zum Bindestrich. Die
Kennung steht danach am Knoten und im Bericht (`vergeben: …`); der Export schreibt sie in
die Datei zurück. Solange sie nur abgeleitet ist, gilt der alte Zustand weiter: Ein
Umbenennen erzeugt einen zweiten Knoten.

Steht im Frontmatter eine Kennung, die das Format verletzt (`CH-Oxidation`), wird sie
verworfen und gemeldet — die Datei selbst wird trotzdem gelesen. Eine ungültige Kennung
hat noch nie einen Knoten benannt; sie wie „nicht angegeben" zu behandeln kann deshalb
nichts verdoppeln, die Datei abzuweisen verlöre dagegen den ganzen Eintrag.

Ergibt der Dateiname keine Kennung (nur Sonderzeichen), meldet der Bericht das und
überspringt die Datei. Eine Kennung zu erfinden, die niemand wiedererkennt, wäre
schlechter als keine.

**Gesucht wird in dieser Reihenfolge:** `id`, dann — für den Übergang aus Paket 9 —
`seed_quelle`. Knoten von damals bekommen ihre Kennung beim nächsten Lauf nachgetragen,
auch wenn sonst nichts passiert; Alembic `0079` hat das für den Bestand schon erledigt.

## Idempotenz — was ein zweiter Lauf tut

Das Skript schreibt drei Schlüssel an jeden Knoten:

- **`seed_id`** — die Kennung von oben.
- **`seed_quelle`** — der Dateiname, aus dem der Knoten kam.
- **`seed_hash`** — der Stand, den der letzte Lauf hinterlassen hat (Titel, Text,
  Metadaten, Aliase).

⚠️ **`seed_id` zählt nicht zum Stand.** Identität ist kein Inhalt — und stünde die
Kennung im Hash, hielte der erste Lauf nach der Migration jeden nachgerüsteten Knoten
für handverändert und rührte keinen mehr an.

Daraus ergeben sich drei Fälle:

| Lage | Was passiert |
|---|---|
| Hash der Datei = Hash am Knoten | **unverändert** — nichts wird geschrieben, auch `updated_at` bleibt stehen |
| Knoten trägt noch den Hash des letzten Laufs, Datei hat sich geändert | **aktualisiert** — der Vault gewinnt |
| Knoten weicht vom gemerkten Hash ab | **übersprungen** und benannt — seit dem letzten Lauf hat jemand in der Oberfläche gearbeitet; `--ueberschreiben` setzt sich darüber hinweg |

⚠️ **Der dritte Fall ist der Grund für den Hash.** Ohne ihn gäbe ein Re-Import die
Arbeit lautlos preis, die eine Lehrkraft im Editor investiert hat.

## Wohin ein Wikilink zeigt

`[[Ziel]]` meint eine **Datei**, keinen Titel — gleichnamige Fassungen („Oxidation")
wären über den Titel nicht zu unterscheiden. Gesucht wird deshalb zuerst im **Bündel**.
Liegt das Ziel nicht darin (der Normalfall beim Hochladen einer einzelnen Datei),
greift der Lauf auf den Bestand des Fachs zurück: abgeleitete Kennung, dann
Herkunftsdatei, dann Titel. Tragen mehrere Knoten denselben Titel, entsteht **keine**
Kante — eine davon zu greifen wäre geraten.

Gefunden wird nur, was der Import auch schreibt (`begriff`, `stoffsteckbrief`) und nur
im selben Fach. Sonst hinge ein Chemiebegriff an einem gleichnamigen Curriculum-Kapitel.

## Der Bericht

| Zeile | Bedeutung |
|---|---|
| `n neu, n aktualisiert, n unverändert` | siehe Tabelle oben |
| `n übersprungen` | in der Oberfläche geändert — Liste der Dateien folgt |
| `vergeben: ch-…` | Die Datei hat kein `id:`; der Lauf hat eine Kennung abgeleitet |
| `n Kanten, davon n angefasst` | Soll-Ist-Abgleich; gelöschte Kanten sind mitgezählt |
| `Feld \`x\` verworfen — …` | Das Feld steht im Schema, sein **Wert** passt nicht. Der Knoten bleibt, das Feld fehlt |
| `Wikilink-Ziel ohne Knoten` | Ein `[[Verweis]]` auf etwas, das es (noch) nicht gibt — die Arbeitsliste für die nächste Ausbaustufe |
| `Ziel „x" ist im Bestand mehrdeutig` | Mehrere Knoten des Fachs tragen diesen Titel (zwei Fassungen). Im Bündel unterscheidet der Dateiname sie, außerhalb nicht — es entsteht keine Kante |
| `Fundstellen ohne Bildungsplan-Knoten` | Die `bildungsplan:`-Angabe trifft keine Kompetenz — meist ein Tippfehler in der Nummer |
| `Fundstellen zeigen auf **archivierte** Knoten` | Die Kante entsteht, wirkt aber nicht: Die Nachbarschaft zeigt nur Aktives. Im Dev-System betrifft das die ganze Edition CH.V3, die erst ab 2027/28 gilt |
| `n Vektoren verworfen` | So viele Knoten brauchen den Backfill-Lauf oben |

**Ein Lauf bricht nicht wegen eines Feldes ab.** Ein unbrauchbarer Wert kostet das Feld,
nicht den Knoten und schon gar nicht den Lauf — über einen falschen Artikel die
Definition, die Aliase und elf Kanten zu verlieren, stünde in keinem Verhältnis. Jedes
verworfene Feld steht im Bericht; **den liest man**.

## Zusammenhänge

- **Der Import ist die Freigabe.** Es gibt keinen Entwurfszustand; was eingespielt wird,
  steht sofort in Sammlung, Suche und im Kontext passender Chats (ADR-019, Nachtrag vom
  27.09.2026).
- **Wie die Knoten gefunden werden** und was davon beim Modell ankommt:
  [kontextsuche.md](kontextsuche.md).
- **Einen weiteren Knotentyp einspielen** heißt zuerst, ihn anzulegen:
  [neuer-knotentyp.md](neuer-knotentyp.md).
