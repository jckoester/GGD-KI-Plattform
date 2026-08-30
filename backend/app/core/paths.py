"""Relative Pfade aus der Konfiguration auflösen — in beiden Verzeichnislayouts.

Die Anwendung läuft in zwei Anordnungen, die sich um **eine Ebene** unterscheiden:

    Entwicklung:  <repo>/backend/app/…      Config: <repo>/config      Ablage: <repo>/data
    Container:    /app/app/…                Config: /app/config        Ablage: /app/data

Das Image kopiert den *Inhalt* von `backend/` nach `/app`; die Ebene `backend/` entfällt
dabei. Bis 08/2026 rechnete jedes betroffene Modul seine Wurzel selbst aus
(`Path(__file__).resolve().parents[3]`, in einem Fall `[4]`). Im Entwicklungsbaum stimmte
das, im Container ergab dieselbe Rechnung `/` — aus `config/pedagogy.yaml` wurde
`/config/pedagogy.yaml`. Nichts stürzte ab; die Dateien galten schlicht als nicht
vorhanden, und mit ihnen fielen Jugendschutz, Krisenerkennung und Leitplanken still aus.

**Warum die Suche nach einem `config`-Verzeichnis nicht genügt:** `backend/config/` gibt es
ebenfalls (mit `assistant_schema.json`). Ein Aufstieg, der beim ersten `config/` haltmacht,
bliebe im Entwicklungsbaum eine Ebene zu tief hängen.

Entschieden wird die **Anordnung**, einmal beim Import — nicht der einzelne Pfad:

* Liegt zwei Ebenen über dem `app`-Paket eine `docker-compose.yml`, ist das der
  Entwicklungsbaum, und dort ist die Repo-Wurzel gemeint.
* Sonst gilt das Elternverzeichnis des Pakets. Das ist der Container.

**Warum nicht „nimm die Wurzel, unter der die Datei existiert":** Das war der erste
Entwurf, und er ging daneben. `backend/data/` existiert im Entwicklungsbaum als
Überbleibsel früherer Läufe; `data/artifacts` landete damit unter `backend/data/artifacts`
statt neben der `docker-compose.yml`, wo es der Cron und das Volume erwarten. Eine Regel,
die von zufällig herumliegenden Verzeichnissen abhängt, entscheidet auf zwei Rechnern
verschieden — und das ist genau die Sorte Fehler, die hier vermieden werden soll.

Die Rechnung hängt an **diesem** Modul, nicht am aufrufenden. Ein Modul tiefer oder höher
im Baum ändert daran nichts — genau der Fehler, der in `api/admin/guardrail.py` als
`parents[4]` stand und leicht zu `parents[3]` verrutscht wäre.
"""
from pathlib import Path
from typing import Union

# …/backend/app bzw. /app/app — parents[1] von app/core/paths.py
_APP_PAKET = Path(__file__).resolve().parents[1]


def _basis() -> Path:
    """Das Verzeichnis, auf das sich relative Pfade aus der Konfiguration beziehen.

    Die `docker-compose.yml` ist der Marker: Sie liegt in der Repo-Wurzel und wird nicht
    ins Image kopiert (der Build-Kontext ist `backend/`). Fehlt sie, ist die Anordnung
    die des Containers.
    """
    entwicklungsbaum = _APP_PAKET.parent.parent
    if (entwicklungsbaum / "docker-compose.yml").is_file():
        return entwicklungsbaum
    return _APP_PAKET.parent


BASIS = _basis()


def aufloesen(pfad: Union[str, Path]) -> Path:
    """Absoluter Pfad bleibt unverändert; relativer wird an :data:`BASIS` verankert.

    Ein relativer Pfad, den es nicht gibt, wird **nicht** zum Fehler — die Aufrufer melden
    das selbst, und zwar mit einem Pfad, der zur Anordnung passt.
    """
    p = Path(pfad)
    return p if p.is_absolute() else BASIS / p
