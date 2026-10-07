# Fachbegriffe einspielen und wieder herausholen

Aus Markdown-Dateien werden `begriff`- und `stoffsteckbrief`-Knoten samt Kanten, und aus
Knoten wieder Dateien. Es ist ein **Einspielvorgang**, kein Synchronisierungsdienst: Er
läuft, wenn jemand ihn startet.

**Die Arbeit liegt in `app/context/fachbegriffe_import.py`**, nicht im Skript. Darauf
sitzen zwei Hüllen:

| Weg | Wer | Eingabe |
|---|---|---|
| `backend/scripts/seed_fachbegriffe.py` | Admin auf der Kommandozeile | ein Ordner |
| „Aus Dateien“ auf der Fachseite → `POST /context/fachbegriffe/import` | Lehrkräfte des Fachs | Formular-Upload |

Beide rufen `importiere()` und drucken bzw. liefern dieselbe `Bilanz`; ein Test hält
fest, dass sie auf demselben Bündel dieselben Zahlen ergeben.

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

## Der Upload-Endpunkt

```
POST /context/fachbegriffe/import?fach=chemie&probelauf=true&ueberschreiben=false
Content-Type: multipart/form-data      ·      Feld `dateien` (mehrfach)
```

**Rechte** (Entscheidung D2): Lehrkraft **und** Mitglied einer Fachschaftsgruppe des
Fachs, oder Admin. ⚠️ Strenger als `/curricula/new`: Gibt es zum Fach gar keine
Fachschaft, ist das hier ein 403 und kein „dann eben ohne Prüfung" — der Import hängt
seine Knoten an genau diese Gruppe und meldete sonst jede Datei als übersprungen.

**Ein Fach.** Der Lauf ist an das Fach gebunden, für das die Rechte geprüft wurden.
Eine Datei ohne `fach:` landet dort; eine Datei mit einem **anderen** `fach:` wird
gemeldet und übersprungen — nicht umgehängt.

**`probelauf` ist vorgabemäßig `true`.** Er schreibt nichts (die Transaktion wird
verworfen) und liefert denselben Bericht wie der echte Lauf. Darauf steht die Vorschau
im Dialog: Was im Probelauf steht, ist das, was der echte Lauf täte.

**`ueberschreiben` nennt Dateinamen, keinen Wahrheitswert** (mehrfach angeben). Das
Skript kennt `--ueberschreiben` für alle; im Dialog fällt die Entscheidung je Zeile
verschieden aus — an einem Knoten hat jemand gearbeitet, am nächsten nicht. Eine **leere**
Liste heißt „alle behalten", nicht „nichts ausgewählt, also alles".

**Was angenommen wird:** `.md`, `.svg` und `.zip`. Im Zip zählen `*.md` auf oberster
Ebene und `_Abb/*`; eine gemeinsame erste Ordnerebene (so packt der Finder) wird
abgeschnitten. Eine einzeln hochgeladene `.svg` landet unter `_Abb/` — nennt das
Frontmatter sie ohne Ordner, findet der Import sie trotzdem (gesucht wird erst der
Pfad, dann der bloße Dateiname).

| Grenze | Vorgabe | Stellschraube | Verhalten |
|---|---|---|---|
| Dateien je Lauf | 500 | `FACHBEGRIFFE_IMPORT_MAX_FILES` | 413 |
| Bündel gesamt (entpackt) | 20 MB | `FACHBEGRIFFE_IMPORT_MAX_BYTES` | 413 |
| einzelne `.md`/`.svg` | 2 MB | `FACHBEGRIFFE_IMPORT_MAX_FILE_BYTES` | 413 |
| `..`, absolute Pfade, `\` im Zip | — | — | 400, ganzes Archiv |
| fremde Endung einzeln gewählt | — | — | 415 |
| fremde Endung **im Zip** | — | — | übergangen, im Bericht |
| Anfragen je Person | 20 / 5 min | `fachbegriffe_import` in `rate_limits.yaml` | 429 |

⚠️ **Keine dieser Zahlen steht im Code.** Wie groß ein Bündel sein darf, ist eine
Einstellung des Servers; `Grenzen` in `fachbegriffe_upload.py` hat deshalb **keine**
Vorgabewerte, sondern wird aus `app/config.py` gefüllt (`aus_konfiguration()`). Stünde
dort eine Zahl, gäbe es zwei Wahrheiten, und die im Modul gewänne stillschweigend.

⚠️ **Der Reverse-Proxy muss mitwachsen.** `NGINX_MAX_BODY_SIZE` (Vorgabe `24m`) begrenzt
den Anfragekörper, bevor er das Backend erreicht. Ist er kleiner, bekommt die Fachschaft
ein nacktes 413 vom nginx statt eines Satzes, der sagt, was zu tun ist —
`tests/unit/test_upload_grenzen_passen.py` hält beide zusammen. Für Betreiber steht das
in [Upload-Grenzen](../admin/konfiguration.md#upload-grenzen).

⚠️ **Jedes SVG wird geprüft, nicht umgeschrieben** (`app/context/svg_pruefung.py`) — auf
**beiden** Wegen: im Dialog schon beim Entpacken, und seit 0.14.1 für jeden Weg dort, wo
das SVG gespeichert wird (`lade_svg`). Bis dahin speicherte das Skript ungeprüft, was im
Ordner lag; ein Admin sieht vor dem Import aber nicht jede Datei an.
Abgewiesen wird, was Verhalten mitbringt oder nach außen zeigt: `<script>`,
`<foreignObject>`, Animationselemente, `on…`-Attribute, `javascript:`, `href`/`url()`
außerhalb des Dokuments, Entity-Deklarationen, ein fehlender SVG-Namensraum. **Eine
Ausnahme** (0.14.1): ein eingebettetes Rasterbild an `<image>` —
`data:image/png|jpeg|gif|webp;base64,…`. Es lädt nichts nach; bis 0.14.0 galt es als
Verweis nach außen, und die Orbital-Abbildungen der Chemie fielen beim Dialog-Import weg.
Ein eingebettetes **SVG** (`data:image/svg+xml`) bleibt verboten: Es ginge an der Prüfung
vorbei, und der PDF-Export löste darin Verweise nach außen auf. Die
Abbildung fällt dann weg, **der Knoten bleibt** — dieselbe Verhältnismäßigkeit wie bei
einem verworfenen Metadatenfeld, und der Grund steht im Bericht.

Ein Sanitisierer, der das Bild „repariert", gäbe der Autorin etwas anderes zurück, als
sie hochgeladen hat, ohne dass sie es erführe. Bis Paket 9 kamen alle SVGs aus eigenen
Werkzeugen; `app/render/export.py` trägt diese Annahme im Kopf und verweist jetzt
hierher.

**Nach dem Import sind die Knoten da, aber noch nicht über die Bedeutung auffindbar:**
Geänderte Knoten verlieren ihren Vektor, neue haben keinen. Beides holt der nächtliche
Backfill (03:15). Bis dahin finden sie die Namens- und Aliassuche, **nicht** aber die
Vorab-Suche im Chat — die arbeitet über Vektoren.

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

⚠️ **`pruefstatus` wird gelesen, aber nicht geschrieben.** Er ist der Arbeitsstand der
Fachschaft im Vault; die Plattform kennt keinen Freigabestatus — Import **ist** Freigabe
(ADR-019, Nachtrag 27.09.2026). Der Bericht nennt jede Datei, die einen anderen Wert als
`fachlich_geprueft` trägt, und die Vorschau fragt nach. Verhindern tut sie nichts: Ob ein
Entwurf reif ist, weiß die Fachschaft, nicht die Software.

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

## Der Dialog

„Aus Dateien" und „Als Zip" stehen unter **Fächer → Fach → „weiterer Kontext"**
(`/subjects/<fach>?tab=kontext`), im Kopf von `KnowledgeNodeList`.

⚠️ **Nicht in der Sammlung, obwohl sie dort zuerst saßen** (Befund Jan, 27.09.2026).
Drei Gründe, der mittlere ist der schwerste:

1. Auf der Fachseite steht das **Fach schon fest**. In der Sammlung musste man es erst
   oben wählen; wer über die Sidebar kam, landete auf einem grauen Knopf.
2. **Ein Bündel enthält beide Typen.** Die Sammlung ist typgebunden — ein Import, der in
   „Fachbegriff" angestoßen wird, legt auch Stoffsteckbriefe an, und die tauchen in der
   Liste darunter nicht auf. Der Tab zeigt alle Kontexttypen des Fachs.
3. Der Tab wird **nur für Lehrkräfte** gerendert; die Sammlung steht auch
   Schüler:innen offen.

⚠️ **Der Knopf hängt an einem Prop, nicht am Einbau.** `KnowledgeNodeList` steht auch
unter `/knowledge` (ganz ohne Fach) und im Gruppen-Tab (eine Unterrichtsgruppe, nicht
die Fachschaft). Nur die Fachseite gibt `importFach` mit; die Regel steht in
`zeigeDateiwerkzeuge()`. Dass die Komponente sie **benutzt**, prüft eine
Quelltextprüfung in `fachbegriffe_import.test.js` — das Projekt hat keine
Komponententests, und genau diese Lücke hat in Paket 9 schon einmal eine Gegenprobe
grün gehalten.

Zwei Schritte: **Vorschau, dann einspielen.** Derselbe Aufruf, einmal ohne und einmal
mit Wirkung.

⚠️ **Die Reihenfolge der Gruppen in der Vorschau ist keine Kosmetik.** „In der
Oberfläche bearbeitet" steht oben, weil es das Einzige ist, wozu die Vorschau eine
**Frage** stellt; alles andere ist Bericht. Hinter dreißig „unverändert"-Zeilen würde die
Frage überlesen, und der nächste Lauf überschriebe entweder zu viel oder ließe eine
Überarbeitung liegen.

Die Regeln der Vorschau stehen in `frontend/src/lib/fachbegriffe_import.js`, nicht in der
Komponente — welche Zeile eine Frage stellt, wann „einspielen" lohnt und was nach dem
Lauf verlinkt wird, sind Entscheidungen. ⚠️ Eine davon ist leicht zu übersehen:
`lohntSich()` rechnet die **Auswahl** mit, nicht nur den Bericht. Ein Probelauf meldet
für einen behaltenen Knoten „0 aktualisiert" — ohne die Auswahl wäre der Knopf genau
dann aus, wenn er gebraucht wird.

`IMPORTIERBARE_TYPEN` dort ist dieselbe Liste wie `TYPEN` hier;
`tests/unit/test_seed_fachbegriffe.py` hält beide zusammen.

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
| `dateien[]` | Eine Zeile je gelesener Datei: `zustand` (`neu` · `aktualisiert` · `unveraendert` · `uebersprungen` · `uebergangen`), Titel, Knoten-ID, `pruefstatus`. Die Summen oben sind ihre Summe — beides entsteht an derselben Stelle, damit Tabelle und Kopfzeile nicht auseinanderlaufen |
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

## Der Rückweg: Export

```
GET /context/fachbegriffe/export?fach=chemie     → Zip, Rechte wie beim Import
GET /context/nodes/<uuid>/markdown               → eine Datei, Leserecht genügt
```

Eine Fachschaft darf in Dateien pflegen **oder** in der Oberfläche (Entscheidung D1).
Ohne Rückweg wäre die zweite von jeder späteren Massenänderung abgeschnitten. Der Code
liegt in `app/context/fachbegriffe_export.py` — die Umkehrung von `lies_datei`.

**Was der Export ist: der Stand des Speichers.** Nicht die Datei von vorgestern. Was
beim Lesen aufgelöst wurde, kommt nicht zurück:

| | |
|---|---|
| Verweise auf Begriffe **ohne Knoten** | Sie sind nie zu einer Kante geworden (Entscheidung E3) und fehlen. ⚠️ Im Chemie-Pilot sind das **251 Wikilinks** — wer damit einen gepflegten Vault überschreibt, verliert genau die Arbeitsliste für die Breite |
| `pruefstatus` | wird nicht gespeichert |
| `[[Verweis]]` im Fließtext | wurde beim Lesen zu Klartext |
| `## Offene Fragen` | wird beim Lesen verworfen |

Deshalb liegt in **jedem** Bündel ein `_Export-Hinweise.txt` mit genau dieser Liste —
auch wenn sonst nichts aufgefallen ist. Der Unterstrich hält es beim Wiedereinlesen
draußen.

⚠️ **Jede Datei prüft sich selbst.** Nach dem Schreiben liest `lies_datei` sie zurück
und vergleicht den Stand-Hash mit dem des Knotens. Stimmt er nicht, stünde beim nächsten
Import „aktualisiert", obwohl sich nichts geändert hat — und niemand wüsste, warum. Der
Befund landet im Beipackzettel. Das passiert bei Knoten, die nie durch eine Datei
gegangen sind: eine `##`-Überschrift im Text, eine mehrzeilige Fehlvorstellung.

**Der Rundreise-Wächter** (`tests/integration/test_fachbegriffe_rundreise.py`) geht den
Kreis: importieren → exportieren → wieder importieren. Gleich bleiben müssen Knoten,
**Kanten** und Aliase. Kanten stecken nicht im Stand-Hash — ohne diese Zeile fiele ihr
Verlust nicht auf.

⚠️ **Auch Kanten, die nicht vom Import stammen, gehen mit.** Wer in der Oberfläche
verknüpft hat, soll das im Export wiederfinden; sonst wäre der Rückweg löchrig, und
genau dagegen gibt es ihn. Die Folge: Nach einem Rundgang gehört auch diese Verbindung
der Datei, und ein späterer Import ohne sie löscht sie.

Zwei Zuordnungen, die das Format nicht eindeutig hergibt und die deshalb festgelegt
sind: `is_a` schreibt sich bei `stoffsteckbrief` als `stoffklasse`, sonst als
`oberbegriff` (dieselbe Relation, das Wort der Fachschaft ist ein anderes). Und eine
Kante mit mehreren Lesarten (`arten`, etwa Vertiefung **und** Abgrenzung) wird unter
**jeder** davon geschrieben — nur die Gewinner-Art zurückzuschreiben verlöre die andere
bei jedem Rundgang.

## Die Vorlage

„Vorlage herunterladen" im Dialog liefert
`GET /context/fachbegriffe/vorlage` — die Dateien aus
`app/context/templates/fachbegriffe/`: zwei Fassungen eines Begriffs, ein
Stoffsteckbrief, eine Abbildung und `_Format.md` als Kurzfassung.

⚠️ **Sie liegen als echte Dateien neben dem Code, nicht als Zeichenketten darin** — und
`tests/integration/test_fachbegriffe_rundreise.py` **spielt sie ein** statt sie
anzusehen: drei neue Knoten, null Warnungen, keine offenen Ziele, und der Rundgang
Export→Import geht auf. Eine Vorlage, die das Format nicht mehr trifft, ist schlimmer
als keine: Wer ihr folgt, bekommt Warnungen und sucht den Fehler bei sich.

Die Kurzfassung in `_Format.md` und die Anwenderdoku
[`docs/user/fachbegriffe-pflegen.md`](../user/fachbegriffe-pflegen.md) sagen teils
dasselbe. Bewusst: Die eine liegt beim Bearbeiten daneben, die andere in der Anwendung.
Die Kurzfassung bleibt kurz und verweist am Anfang auf die andere — wer etwas Neues
erklärt, tut es dort.

## Zusammenhänge

- **Der Import ist die Freigabe.** Es gibt keinen Entwurfszustand; was eingespielt wird,
  steht sofort in Sammlung, Suche und im Kontext passender Chats (ADR-019, Nachtrag vom
  27.09.2026).
- **Wie die Knoten gefunden werden** und was davon beim Modell ankommt:
  [kontextsuche.md](kontextsuche.md).
- **Einen weiteren Knotentyp einspielen** heißt zuerst, ihn anzulegen:
  [neuer-knotentyp.md](neuer-knotentyp.md).
