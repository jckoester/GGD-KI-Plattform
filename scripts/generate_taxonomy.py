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


def _js(obj, indent=2) -> str:
    """Minimal JSON-to-JS serializer (dicts -> objects, lists -> arrays)."""
    import json

    return json.dumps(obj, ensure_ascii=False, indent=indent)


if __name__ == "__main__":
    main()
