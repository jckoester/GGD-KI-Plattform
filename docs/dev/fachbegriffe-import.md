# Fachbegriffe aus einem Obsidian-Ordner einspielen

`backend/scripts/seed_fachbegriffe.py` liest einen Ordner mit Markdown-Dateien und legt
daraus `begriff`- und `stoffsteckbrief`-Knoten samt Kanten an. Es ist ein
**Einspielskript**, kein Synchronisierungsdienst: Es läuft, wenn jemand es startet.

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

**Aus dem Frontmatter:** Steuerschlüssel (`knotentyp`, `titel`, `fach`, `aliase`,
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

## Idempotenz — was ein zweiter Lauf tut

Das Skript schreibt zwei Schlüssel an jeden Knoten:

- **`seed_quelle`** — der Dateiname. Darüber findet der nächste Lauf denselben Knoten
  wieder, auch wenn sich der Titel geändert hat.
- **`seed_hash`** — der Stand, den der letzte Lauf hinterlassen hat (Titel, Text,
  Metadaten, Aliase).

Daraus ergeben sich drei Fälle:

| Lage | Was passiert |
|---|---|
| Hash der Datei = Hash am Knoten | **unverändert** — nichts wird geschrieben, auch `updated_at` bleibt stehen |
| Knoten trägt noch den Hash des letzten Laufs, Datei hat sich geändert | **aktualisiert** — der Vault gewinnt |
| Knoten weicht vom gemerkten Hash ab | **übersprungen** und benannt — seit dem letzten Lauf hat jemand in der Oberfläche gearbeitet; `--ueberschreiben` setzt sich darüber hinweg |

⚠️ **Der dritte Fall ist der Grund für den Hash.** Ohne ihn gäbe ein Re-Import die
Arbeit lautlos preis, die eine Lehrkraft im Editor investiert hat.

## Der Bericht

| Zeile | Bedeutung |
|---|---|
| `n neu, n aktualisiert, n unverändert` | siehe Tabelle oben |
| `n übersprungen` | in der Oberfläche geändert — Liste der Dateien folgt |
| `n Kanten, davon n angefasst` | Soll-Ist-Abgleich; gelöschte Kanten sind mitgezählt |
| `Feld \`x\` verworfen — …` | Das Feld steht im Schema, sein **Wert** passt nicht. Der Knoten bleibt, das Feld fehlt |
| `Wikilink-Ziel ohne Knoten` | Ein `[[Verweis]]` auf etwas, das es (noch) nicht gibt — die Arbeitsliste für die nächste Ausbaustufe |
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
