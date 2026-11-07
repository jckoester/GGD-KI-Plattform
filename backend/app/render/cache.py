"""Persistenter SVG-Cache (Tabelle `rendered_svg`) für Server-Rendering (Phase 17).

Content-adressiert per Hash der Render-Quelle. Nur Erfolge werden gecacht (der Service
cacht keine Fehler-Platzhalter). Altersbasiert aufgeräumt (`cleanup_rendered_svg`).
"""
import hashlib
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RenderedSvg


#: Ausgabe-Fassung je Renderer (0.30). Wer die Zeichnung eines Renderers ändert, erhöht hier
#: die Zahl — sonst liefert der Cache weiter das alte Bild zur gleichen Quelle. Renderer ohne
#: Eintrag behalten ihren bisherigen Schlüssel.
RENDERER_FASSUNG: dict[str, int] = {
    # 2 — 03.11.2026: Elektronenpaare nach der gelesenen Beschriftung, Vorgabe Valenzstrich
    # 3 — 03.11.2026: Moleküle als flache Gruppen statt verschachtelter <svg>, Stile als
    #     Attribute (Export: weasyprint, Word, LibreOffice); geladenes C behält seine Ladung
    "smiles": 3,
    # 2 — 06.11.2026 (0.36): Achsen-Standards (`PlotStil`): Achsen durch den Ursprung mit Pfeil,
    #     schöne Teilstriche, gleiche Skalierung, gekappter y-Bereich, Plattformfarben
    "plot": 2,
    # 1 — 07.11.2026 (0.37): europäische Symbole, Umgebung ergänzt, Präambel/`[american]` entfernt
    # 2 — 07.11.2026 (0.37): Schalter als Schulsymbol (`switch` → `nos`, Öffner → `ncs`)
    "circuit": 2,
}


def svg_hash(kind: str, source: str) -> str:
    """Stabiler Hash über (kind, source[, Fassung]) — trennt circuit/plot mit gleicher Quelle."""
    fassung = RENDERER_FASSUNG.get(kind)
    zusatz = f"\x00v{fassung}" if fassung else ""
    return hashlib.sha256(f"{kind}\x00{source}{zusatz}".encode("utf-8")).hexdigest()


async def get_cached_svg(db: AsyncSession, hash_: str) -> str | None:
    result = await db.execute(select(RenderedSvg.svg).where(RenderedSvg.hash == hash_))
    return result.scalar_one_or_none()


async def set_cached_svg(db: AsyncSession, hash_: str, svg: str) -> None:
    # Idempotent: gleicher Hash = gleicher Input → bereits vorhandenen Eintrag behalten.
    stmt = (
        pg_insert(RenderedSvg)
        .values(hash=hash_, svg=svg)
        .on_conflict_do_nothing(index_elements=["hash"])
    )
    await db.execute(stmt)
    await db.commit()


async def cleanup_rendered_svg(db: AsyncSession, max_age_days: int) -> int:
    """Löscht Cache-Einträge älter als max_age_days. Gibt die Anzahl zurück."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    result = await db.execute(delete(RenderedSvg).where(RenderedSvg.created_at < cutoff))
    await db.commit()
    return result.rowcount or 0
