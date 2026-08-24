# Runbook: Curricula zwischen Instanzen übertragen

Ein Schulcurriculum aus einer Instanz **exportieren** und in einer anderen **einspielen** —
typischerweise aus dem Produktivsystem nach promptLab oder auf eine Entwicklungsinstanz.

> **Wozu.** Zum Ausprobieren von Assistenten, Planungswerkzeugen oder Bildungsplan-Editionen
> braucht eine Testinstanz realistische Curricula. Sie von Hand nachzubauen ist die
> eigentliche Hürde — dieser Weg nimmt sie ab.

**Rollen:** Der **Export** ist eine Lehrkraft-Funktion in der Oberfläche. Der **Import** ist
ein Admin-Vorgang auf der Kommandozeile des Backend-Containers; es gibt dafür bewusst keine
Oberfläche — er schreibt tief in den Wissensgraph und gehört in dieselbe Hand wie der
Bildungsplan-Import.

---

## 1. Exportieren (Lehrkraft, Oberfläche)

Curriculum öffnen → **Export** → **YAML**.

Die Datei heißt `curriculum_<fach>_<jahrgang>_<datum>.yaml` und enthält den Kopf
(Fach, Schulart, Jahrgangsband, Bildungsplan-Edition), das Vorwort sowie alle Kapitel,
Lernsequenzen und Einträge.

**Wichtig für die Übertragbarkeit:** Kompetenzen stehen im Export als **Nummern**
(`3.2.2.1(1)`), nicht als Knoten-IDs. Nur deshalb lässt sich die Datei in einer anderen
Instanz überhaupt einspielen — dort haben dieselben Kompetenzen andere IDs. Aufgelöst
werden die Nummern beim Import.

Der PDF-Export daneben ist für Menschen gedacht und **nicht** wieder einlesbar.

---

## 2. Voraussetzungen in der Zielinstanz

Beides muss **vor** dem Import stehen:

| Voraussetzung | Prüfen mit |
|---|---|
| Das **Fach** existiert (gleicher `fach_code`) | `/settings` → Fächer, oder `scripts/seed_subjects.py` |
| Der **Bildungsplan** des Fachs ist importiert | Wissensgraph → Bildungsplan des Fachs öffnen |

Fehlt das Fach, bricht der Import ab. Fehlt der Bildungsplan, bricht er ebenfalls ab — mit
einer Meldung, die Fach und Edition nennt.

Fehlen **einzelne Kompetenzen** (etwa weil die Zielinstanz eine andere Edition führt),
bricht der Import **nicht** ab: Das Curriculum entsteht, die betroffenen Verweise bleiben
leer und werden gemeldet. Siehe [Abschnitt 4](#4-warnungen-lesen).

---

## 3. Importieren (Admin, Kommandozeile)

**Immer zuerst im Trockenlauf.** Er löst alles auf und meldet jedes Problem, schreibt aber
nichts:

```bash
docker compose exec backend python -m scripts.import_curriculum \
  --file /tmp/curriculum_ch_8_2026-08-08.yaml --dry-run
```

Sieht die Ausgabe gut aus, denselben Aufruf ohne `--dry-run` wiederholen:

```bash
docker compose exec backend python -m scripts.import_curriculum \
  --file /tmp/curriculum_ch_8_2026-08-08.yaml
```

Ein ganzes Verzeichnis auf einmal:

```bash
docker compose exec backend python -m scripts.import_curriculum \
  --directory /tmp/curricula/ --continue-on-error
```

| Schalter | Wirkung |
|---|---|
| `--dry-run` | Nur prüfen, am Ende zurückrollen |
| `--directory` | Alle `.yaml`/`.yml` eines Verzeichnisses |
| `--continue-on-error` | Nach einem Fehlschlag mit der nächsten Datei weitermachen (ohne ihn bricht der Lauf ab) |
| `--owner` | Besitzer-Pseudonym der Knoten (Vorgabe `system`) |
| `--bp-version` | Bildungsplan-Edition aus der Datei überschreiben — siehe unten |

### Wenn die Editionen nicht zusammenpassen

Häufigster Stolperstein beim Einspielen eines Produktiv-Exports in eine Testinstanz:

```
Kein Fachplan für Fach 'M' und Edition '2016.V2' gefunden. Die Edition '2016.V2' ist in
dieser Instanz vorhanden, aber **archiviert** — vermutlich, weil danach eine andere
Edition importiert wurde. Aktiv ist derzeit: 2016.
```

Die Meldung nennt beides: was die Datei verlangt und was die Instanz aktiv führt. Zwei
Wege:

1. **Sauber:** Die passende Edition in der Zielinstanz importieren
   (`bildungsplan_suffix` in `subjects.yaml` prüfen, dann
   [Bildungsplan-Import](bildungsplan-import.md)). Danach greift der Curriculum-Import
   ohne Zutun.
2. **Schnell:** Mit der aktiven Edition erzwingen —
   `--bp-version 2016`. Das ist für Test- und Entwicklungsinstanzen gedacht.

> ⚠️ **Bei `--bp-version` die Warnungen lesen.** Kompetenznummern können sich zwischen
> Editionen unterscheiden; was nicht passt, bleibt unverknüpft und wird gemeldet. Für ein
> Produktivsystem ist Weg 1 der richtige.

Jede Datei wird **einzeln** festgeschrieben. Scheitert die dritte von fünf, bleiben die
ersten beiden importiert.

**Der Import ist wiederholbar.** Dieselbe Datei zweimal einzuspielen erzeugt kein zweites
Curriculum, sondern aktualisiert das vorhandene. Erkannt wird es an Bildungsplan und
Jahrgangsband — nicht am Dateinamen.

---

## 4. Warnungen lesen

Am Ende steht eine Zeile wie:

```
Fertig: 1 Curricula importiert, 47 Knoten
  3 Kompetenzverweis(e) konnten nicht aufgelöst werden — die betroffenen Stellen
  bleiben ohne Verknüpfung. Fehlt der Bildungsplan dieses Fachs in dieser Instanz?
```

Darüber steht je Fall eine Zeile:

| Meldung | Bedeutung |
|---|---|
| `IK 3.2.2.1(1) nicht gefunden für LS …` | Die inhaltsbezogene Kompetenz gibt es in dieser Instanz nicht — meist eine andere Bildungsplan-Edition |
| `PK 2.2.5 nicht gefunden für LS …` | dasselbe für prozessbezogene Kompetenzen |
| `LP '…-…-…' nicht gefunden in …` | Ein Leitperspektiven-Verweis, der schon im Export nicht als Code aufgelöst werden konnte (siehe Grenzen unten) |
| `Cross-Fach-IK-Verweis … zeigt auf einen Knoten, den es in dieser Instanz nicht gibt` | Ein Verweis aus den Hinweisen auf ein **anderes Fach**. Er steht als Knoten-ID im Text und lässt sich zwischen Instanzen nicht übersetzen — der Verweis entfällt, der Text bleibt |

**Null Warnungen sind das Ziel, aber kein Muss.** Für eine Testinstanz ist ein Curriculum
mit ein paar fehlenden Verweisen brauchbar; nur sollte man wissen, welche fehlen — sonst
sieht es vollständig aus und ist es nicht.

Fällt die Zahl hoch aus (Dutzende), stimmt meist die **Edition** nicht: Quell- und
Zielinstanz führen unterschiedliche Bildungsplan-Fassungen desselben Fachs. Dann erst den
passenden Bildungsplan importieren (siehe [Bildungsplan-Import](bildungsplan-import.md))
und den Curriculum-Import wiederholen.

---

## 5. Grenzen

**Leitperspektiven ohne `code`.** Trägt ein Leitperspektiven-Knoten kein `code`-Feld, bleibt
im Export die rohe Knoten-ID stehen, die in der Zielinstanz ins Leere zeigt. Betrifft
einzelne Verweise, nicht das Curriculum als Ganzes.

**Verweise auf eigenes Material** (`node:…`-Token in den Hinweisen) zeigen auf Knoten der
Quellinstanz und werden beim Import nicht mit übertragen. Das Curriculum bleibt nutzbar,
die Materialverknüpfung fehlt.

**Kein Rückweg für PDF.** Nur der YAML-Export ist wieder einlesbar.

---

## 6. Was der Import *nicht* ist

Er ist **kein** Bildungsplan-Import. Der Bildungsplan (die Landesvorgabe: Leitideen,
inhalts- und prozessbezogene Kompetenzen) kommt über
[`bildungsplan-import.md`](bildungsplan-import.md) und ist die **Voraussetzung** hierfür.
Das Schulcurriculum ist die schuleigene Umsetzung darauf.

Er ist auch **keine** Migration auf eine neue Bildungsplan-Edition. Dafür gibt es in der
Curriculum-Ansicht „Auf neue Edition aktualisieren" — eine geprüfte Aktion, die
Kompetenzverweise einzeln vergleicht, statt sie neu zu raten.
