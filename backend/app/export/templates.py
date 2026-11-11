"""Schulweite Export-Vorlagen der Material-Werkstatt (Phase 19, Schritt 6).

Zwei Vorlagen-Mechanismen, je Ausgabeformat:
- **PDF** über eigenes CSS: schulweit ergänzbar, liegt als Text in `site_config` (`export_css`)
  und wird beim PDF-Export als `extra_css` in die Standard-Vorlage injiziert.
- **DOCX/ODT** über Pandoc `--reference-doc`: eine hochgeladene Referenzdatei je Format, liegt
  auf Disk (`settings.export_template_dir`).

Fehlt eine Vorlage, greift die eingebaute Default-Optik (kein Hard-Fail). Persönliche Vorlagen
(pro Lehrkraft) sind bewusst v1-out-of-scope (Todo).
"""
from __future__ import annotations

import io
import logging
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.core.paths import aufloesen
from app.db.models import SiteConfig

logger = logging.getLogger(__name__)

EXPORT_CSS_KEY = "export_css"
# Herkunftszeile am Ende exportierter Dokumente. Vorgabe **aus**: Ein Update soll
# das Aussehen bereits genutzter Vorlagen nicht von sich aus verändern; ob die
# Angabe erscheinen soll, entscheidet die Schule.
EXPORT_PROVENANCE_KEY = "export_provenance"
REFERENCE_FORMATS = ("docx", "odt")



# ── PDF-CSS (site_config) ─────────────────────────────────────────────────────

async def get_export_css(db: AsyncSession) -> str:
    result = await db.execute(select(SiteConfig.value).where(SiteConfig.key == EXPORT_CSS_KEY))
    return result.scalar_one_or_none() or ""


async def set_export_css(db: AsyncSession, css: Optional[str], updated_by: Optional[str]) -> None:
    now = datetime.now(timezone.utc)
    stmt = (
        pg_insert(SiteConfig)
        .values(key=EXPORT_CSS_KEY, value=css, updated_at=now, updated_by=updated_by)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": css, "updated_at": now, "updated_by": updated_by},
        )
    )
    await db.execute(stmt)
    await db.commit()


# ── DOCX/ODT-Referenzdokumente (Disk) ─────────────────────────────────────────

def template_dir() -> Path:
    d = aufloesen(settings.export_template_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def reference_path(fmt: str) -> Optional[Path]:
    """Pfad des reference-docs (falls vorhanden) — für Pandoc `--reference-doc`."""
    if fmt not in REFERENCE_FORMATS:
        return None
    path = template_dir() / f"reference.{fmt}"
    return path if path.exists() else None


# ── Eingebaute Vorlage: Pandocs eigene, auf A4 ────────────────────────────────
#
# ⚠️ Pandocs mitgelieferte reference.odt ist **US-Letter** (8.5 × 11 in), die reference.docx legt
# gar kein Seitenformat fest — Word nimmt dann seine Voreinstellung, mit US-Einstellung Letter.
# Bis 0.38 kamen Werkstatt-Dokumente ohne Schulvorlage deshalb so heraus; der Stundenentwurf war
# A4, weil `python-docx` das Format ausdrücklich setzte. Seit 0.39 erzeugt der Server beim ersten
# Gebrauch eine Abwandlung von Pandocs Vorlage — A4, Ränder 2 cm oben/unten, 2,5 cm links/rechts
# wie im PDF — statt eine Binärdatei mitzuliefern, die zu einer anderen Pandoc-Fassung gehört.

_A4_DOCX = (
    '<w:pgSz w:w="11906" w:h="16838" />'
    '<w:pgMar w:top="1134" w:right="1418" w:bottom="1134" w:left="1418" '
    'w:header="709" w:footer="709" w:gutter="0" />'
)
_eingebaut: dict[str, Path] = {}


def _a4(fmt: str, xml: str) -> str:
    if fmt == "docx":
        if "<w:pgSz" in xml:
            return xml
        return xml.replace("</w:sectPr>", _A4_DOCX + "</w:sectPr>", 1)
    for alt, neu in (
        ('fo:page-width="8.5in"', 'fo:page-width="21cm"'),
        ('fo:page-height="11in"', 'fo:page-height="29.7cm"'),
        ('fo:margin-top="1in"', 'fo:margin-top="2cm"'),
        ('fo:margin-bottom="1in"', 'fo:margin-bottom="2cm"'),
        ('fo:margin-left="1in"', 'fo:margin-left="2.5cm"'),
        ('fo:margin-right="1in"', 'fo:margin-right="2.5cm"'),
    ):
        xml = xml.replace(alt, neu, 1)
    return xml


def _zip_mit_ersetzung(roh: bytes, name: str, ersetzen) -> bytes:
    """Schreibt das ZIP neu, Reihenfolge und Kompression je Eintrag bleiben (ODT: `mimetype` zuerst,
    unkomprimiert)."""
    quelle = zipfile.ZipFile(io.BytesIO(roh))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as ziel:
        for info in quelle.infolist():
            daten = quelle.read(info.filename)
            if info.filename == name:
                daten = ersetzen(daten.decode("utf-8")).encode("utf-8")
            ziel.writestr(info, daten, compress_type=info.compress_type)
    return out.getvalue()


def eingebaute_vorlage(fmt: str) -> Optional[Path]:
    """Pandocs Vorlage auf A4 — einmal je Prozess erzeugt. None ohne Pandoc."""
    if fmt not in REFERENCE_FORMATS:
        return None
    if fmt in _eingebaut and _eingebaut[fmt].is_file():
        return _eingebaut[fmt]
    from app.export import pandoc

    try:
        roh = pandoc._ausfuehren(
            [pandoc._pandoc_bin(), "--print-default-data-file", f"reference.{fmt}"], b"",
        )
    except pandoc.PandocError:
        logger.warning("Eingebaute %s-Vorlage nicht erzeugt (Pandoc fehlt oder Fehler)", fmt)
        return None
    eintrag = "word/document.xml" if fmt == "docx" else "styles.xml"
    pfad = Path(tempfile.mkdtemp(prefix="ggd-vorlage-")) / f"reference.{fmt}"
    pfad.write_bytes(_zip_mit_ersetzung(roh, eintrag, lambda xml: _a4(fmt, xml)))
    _eingebaut[fmt] = pfad
    return pfad


def vorlage(fmt: str) -> Optional[str]:
    """Die Vorlage für Pandoc `--reference-doc`: die der Schule, sonst die eingebaute (A4).

    Gilt seit 0.39 für alle Office-Exporte — Werkstatt, Stundenentwurf, Curriculum.
    """
    pfad = reference_path(fmt) or eingebaute_vorlage(fmt)
    return str(pfad) if pfad else None


def has_reference(fmt: str) -> bool:
    return reference_path(fmt) is not None


def save_reference(fmt: str, data: bytes) -> None:
    if fmt not in REFERENCE_FORMATS:
        raise ValueError(f"kein referenzierbares Format: {fmt!r}")
    (template_dir() / f"reference.{fmt}").write_bytes(data)


def delete_reference(fmt: str) -> bool:
    if fmt not in REFERENCE_FORMATS:
        return False
    path = template_dir() / f"reference.{fmt}"
    if path.exists():
        path.unlink()
        return True
    return False


# ── Herkunftszeile (site_config) ──────────────────────────────────────────────

async def get_export_provenance(db: AsyncSession) -> bool:
    """Soll exportierten Dokumenten eine Herkunftszeile angehängt werden?"""
    result = await db.execute(
        select(SiteConfig.value).where(SiteConfig.key == EXPORT_PROVENANCE_KEY)
    )
    return (result.scalar_one_or_none() or "").strip().lower() in ("1", "true", "on", "an")


async def set_export_provenance(
    db: AsyncSession, aktiv: bool, updated_by: Optional[str]
) -> None:
    now = datetime.now(timezone.utc)
    wert = "on" if aktiv else "off"
    stmt = (
        pg_insert(SiteConfig)
        .values(key=EXPORT_PROVENANCE_KEY, value=wert, updated_at=now, updated_by=updated_by)
        .on_conflict_do_update(
            index_elements=["key"],
            set_={"value": wert, "updated_at": now, "updated_by": updated_by},
        )
    )
    await db.execute(stmt)
    await db.commit()
