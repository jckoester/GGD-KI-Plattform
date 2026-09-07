#!/usr/bin/env python3
"""
Generates frontend/src/lib/taxonomy.js from backend/app/context/taxonomy.yaml.
Run: python scripts/generate_taxonomy.py
Called automatically by: npm run prebuild

Die Quelle liegt seit 02.09.2026 im Backend statt in `config/` — sie ist Systemdatei,
keine Betreiber-Konfiguration (ADR-018). Wer diesen Pfad ändert, denkt an
`frontend/Dockerfile`: Der Frontend-Build kopiert die Datei einzeln in seinen Kontext.
"""

from pathlib import Path
import yaml

ROOT = Path(__file__).parent.parent
YAML_PATH = ROOT / "backend" / "app" / "context" / "taxonomy.yaml"
OUT_PATH = ROOT / "frontend" / "src" / "lib" / "taxonomy.js"
#: Zweite Ausgabe: die Symbol-Zuordnung. Eigene Datei, damit `taxonomy.js` frei von
#: Komponenten-Importen bleibt — es wird auch dort eingebunden, wo lucide nichts zu
#: suchen hat (Tests, reine Datenmodule).
ICONS_OUT_PATH = ROOT / "frontend" / "src" / "lib" / "node_icons.js"


def main():
    with open(YAML_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    cats = data["categories"]

    content_types = {
        cat: [ct["key"] for ct in info["content_types"]]
        for cat, info in cats.items()
    }

    scope_anchor_types = [
        ct["key"]
        for info in cats.values()
        for ct in info["content_types"]
        if ct.get("scope_anchor")
    ]

    bp_curriculum_types = data.get("bp_curriculum_content_types", [])

    ruhende_types = [
        ct["key"]
        for info in cats.values()
        for ct in info["content_types"]
        if ct.get("ui_status") == "ruhend"
    ]

    schuljahresende_types = [
        ct["key"]
        for info in cats.values()
        for ct in info["content_types"]
        if ct.get("valid_until_default") == "schuljahresende"
    ]

    # Sammlungs-Ansichten und Feldschemata (AP5a). Reihenfolge = Reihenfolge in der
    # YAML; die Sidebar zeigt die Sammlungen in genau dieser Folge.
    collections = {
        ct["key"]: ct["collection"]
        for info in cats.values()
        for ct in info["content_types"]
        if ct.get("collection")
    }
    feld_schemata = {
        ct["key"]: ct["felder"]
        for info in cats.values()
        for ct in info["content_types"]
        if ct.get("felder")
    }

    category_labels = {cat: info["label_de"] for cat, info in cats.items()}

    category_colors = {cat: info["color"] for cat, info in cats.items()}

    content_type_labels = {
        ct["key"]: ct["label_de"]
        for info in cats.values()
        for ct in info["content_types"]
    }

    scope_defaults = {
        ct["key"]: [
            ct["scope_defaults"]["read_scope"],
            ct["scope_defaults"]["write_scope"],
        ]
        for info in cats.values()
        for ct in info["content_types"]
    }

    lines = [
        "// GENERATED FILE — do not edit manually.",
        "// Source:      backend/app/context/taxonomy.yaml",
        "// Regenerate:  python scripts/generate_taxonomy.py",
        "//              (runs automatically via npm run prebuild / npm run dev)",
        "",
        f"export const CONTENT_TYPES = {_js(content_types)}",
        "",
        f"export const SCOPE_ANCHOR_CONTENT_TYPES = new Set({_js(scope_anchor_types)})",
        "",
        "// Importierte Bildungsplan-/Curriculum-Knotentypen — aus der freien /knowledge-Liste",
        "// serverseitig ausgeschlossen (exclude_content_type). Quelle: taxonomy.yaml (C2).",
        f"export const BP_CURRICULUM_CONTENT_TYPES = {_js(bp_curriculum_types)}",
        "",
        "// Typen mit `ui_status: ruhend` — erscheinen in keiner Auswahl, keinem Filter und",
        "// keiner Such-Facette (ADR-019 F6). Vorhandene Knoten bleiben sicht- und suchbar;",
        "// zum Filtern die Helfer in `knotentypen.js` verwenden, nicht diese Menge direkt.",
        f"export const RUHENDE_CONTENT_TYPES = new Set({_js(ruhende_types)})",
        "",
        "// Typen, deren `valid_until` beim Anlegen aufs Schuljahresende vorbelegt wird",
        "// (`before_insert`-Regel in app/db/models.py). Das Formular sagt das dazu — ein",
        "// leeres Feld heißt hier nicht „läuft nie ab\".",
        f"export const SCHULJAHRESENDE_CONTENT_TYPES = new Set({_js(schuljahresende_types)})",
        "",
        "// Typen mit gepflegter Sammlungsansicht (/knowledge/collections/<typ>).",
        "// Beschreibung, Spalten, Filter und Content-Label je Typ; Reihenfolge = YAML.",
        f"export const COLLECTIONS = {_js(collections)}",
        "",
        "// Metadaten-Feldschema je Typ — dieselbe Beschreibung, aus der das Backend prüft",
        "// (app/context/metadata.py). Der Editor baut sein Formular daraus.",
        f"export const FELD_SCHEMATA = {_js(feld_schemata)}",
        "",
        f"export const CATEGORY_LABELS = {_js(category_labels)}",
        "",
        f"export const CATEGORY_COLORS = {_js(category_colors)}",
        "",
        f"export const CONTENT_TYPE_LABELS = {_js(content_type_labels)}",
        "",
        f"export const SCOPE_DEFAULTS = {_js(scope_defaults)}",
        "",
    ]

    OUT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"Written: {OUT_PATH}")

    _schreibe_icons(cats)


def _schreibe_icons(cats: dict) -> None:
    """Erzeugt `node_icons.js` aus den `icon:`-Angaben der Taxonomie.

    **Warum erzeugt statt gepflegt.** Bis 09/2026 stand die Zuordnung von Hand im
    Frontend und deckte 11 von 41 Typen ab; der Rest fiel still auf das
    Kategorie-Symbol zurück, sodass in artefakt-lastigen Listen fast jede Zeile
    dasselbe Paket trug. Zwei Orte für dieselbe Typangabe laufen auseinander —
    hier steht sie einmal, in der Taxonomie.

    **Warum statische Importe.** `lucide-svelte` bringt 1686 Komponenten mit. Einen
    Namen zur Laufzeit aufzulösen (`import * as icons`) zöge sie alle ins Bundle.
    Deshalb erzeugt der Generator die Importliste — ein Name, den es nicht gibt,
    bricht dann den Build, statt still auf ein Ersatzsymbol zu fallen.
    """
    typ_icons = {
        ct["key"]: ct["icon"]
        for info in cats.values()
        for ct in info["content_types"]
    }
    kat_icons = {name: info["icon"] for name, info in cats.items()}

    # Sortiert und dedupliziert: Der Import ist reine Technik, seine Reihenfolge
    # soll nicht davon abhängen, in welcher Reihenfolge die Typen in der YAML stehen.
    komponenten = sorted({*typ_icons.values(), *kat_icons.values(), "Circle"})

    zeilen = [
        "// GENERIERT aus backend/app/context/taxonomy.yaml — nicht von Hand ändern.",
        "// Neu erzeugen: python scripts/generate_taxonomy.py",
        "//",
        "// Ein eigenes Symbol je Knotentyp: Die Form unterscheidet den Typ, die Farbe",
        "// die Kategorie (`CATEGORY_COLORS` in taxonomy.js). Gepflegt wird das Symbol",
        "// am Typ in der Taxonomie, nicht hier.",
        "",
        "import {",
        *(f"    {name}," for name in komponenten),
        "} from 'lucide-svelte'",
        "",
        "/** content_type → Symbol. Vollständig über alle Typen der Taxonomie. */",
        "export const NODE_ICONS = {",
        *(f"    {typ}: {icon}," for typ, icon in typ_icons.items()),
        "}",
        "",
        "/** Rückfall je Kategorie — greift nur, wenn ein Knoten keinen content_type hat. */",
        "export const CATEGORY_ICONS = {",
        *(f"    {kat}: {icon}," for kat, icon in kat_icons.items()),
        "}",
        "",
        "/** Letzter Rückfall, wenn auch die Kategorie fehlt. */",
        "export const FALLBACK_ICON = Circle",
        "",
    ]
    ICONS_OUT_PATH.write_text("\n".join(zeilen), encoding="utf-8")
    print(f"Written: {ICONS_OUT_PATH}  ({len(typ_icons)} Typen, {len(komponenten)} Symbole)")


def _js(obj, indent=2) -> str:
    """Minimal JSON-to-JS serializer (dicts -> objects, lists -> arrays)."""
    import json

    return json.dumps(obj, ensure_ascii=False, indent=indent)


if __name__ == "__main__":
    main()
