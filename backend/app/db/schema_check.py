"""Steht die Datenbank auf dem Stand, den der Code erwartet?

**Der Ausfall, den das verhindert.** Am 09.09.2026 stand die Entwicklungsdatenbank
auf `0056`, der Code auf `0057`. Jede Knotenliste und jede Detailansicht antwortete
mit einem 500er — `relation "node_aliases" does not exist` —, während der
Prüflauf grün war: Die Integrationstests fahren ihre **eigene** Datenbank bei
jedem Lauf auf den Kopf hoch und sehen die betriebene nie. Ein grüner Prüflauf
sagt also nichts über die Datenbank, gegen die die Anwendung tatsächlich läuft.

Der Fehler äußerte sich erst beim Anklicken, an einer beliebigen Stelle, mit einer
Meldung über eine fehlende Tabelle — nicht über eine fehlende Migration. Diese
Prüfung dreht das um: Sie fragt beim Start und nennt das Problem beim Namen.

**Warum hart.** Eine Datenbank hinter dem Code ist kein Randfall, den man
weiterlaufen lassen möchte: Was fehlt, ist erst bekannt, wenn jemand darauf tritt,
und bis dahin sieht die Anwendung gesund aus. Dieselbe Begründung wie bei der
Taxonomie-Startprüfung (ADR-018).
"""
import logging
from pathlib import Path

import sqlalchemy as sa

from app.core.paths import ANWENDUNGSWURZEL

logger = logging.getLogger(__name__)


class SchemaVeraltet(RuntimeError):
    """Die Datenbank steht nicht auf dem erwarteten Migrationsstand."""


def _alembic_ini() -> Path:
    """`backend/alembic.ini` im Entwicklungsbaum, `/app/alembic.ini` im Container.

    Bewusst über `app.core.paths` statt über eine eigene `parents[…]`-Rechnung: Die
    beiden Anordnungen unterscheiden sich um eine Ebene, und jede Rechnung von Hand
    geht in einer davon daneben (ein Wächtertest hält das fest).
    """
    return ANWENDUNGSWURZEL / "alembic.ini"


def _skript_verzeichnis():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(_alembic_ini())))


def kopf_revisionen() -> set[str]:
    """Die Kopf-Revisionen laut den Migrationsdateien."""
    return set(_skript_verzeichnis().get_heads())


def bekannte_revisionen() -> set[str]:
    """Alle Revisionen, die dieser Code kennt — nicht nur die Köpfe."""
    return {s.revision for s in _skript_verzeichnis().walk_revisions()}


def abweichung(
    db_stand: set[str], kopf: set[str], bekannt: set[str] | None = None
) -> str | None:
    """Die Meldung zum Unterschied — oder ``None``, wenn alles passt.

    Rein, damit die Fallunterscheidung ohne Datenbank prüfbar bleibt.

    **Warum `bekannt` gebraucht wird.** „Datenbank hinterher" und „Datenbank voraus"
    sehen im reinen Mengenvergleich gleich aus — `{'0056'}` gegen `{'0057'}` und
    `{'0058'}` gegen `{'0057'}` unterscheiden sich nicht in ihrer Form. Der
    Unterschied steht woanders: Kennt *dieser* Code die Revision der Datenbank? Wenn
    ja, fehlt hier nur ein `upgrade`. Wenn nein, hat eine neuere Fassung migriert,
    und ein `upgrade` hilft nicht — dann läuft der falsche Stand.
    """
    if db_stand == kopf:
        return None

    befehl = "cd backend && alembic upgrade head"
    if not db_stand:
        return (
            "Die Datenbank kennt keine Migration (Tabelle alembic_version ist leer "
            f"oder fehlt). Erwartet: {sorted(kopf)}. Anwenden mit: {befehl}"
        )

    unbekannt = db_stand - (bekannt or db_stand)
    if unbekannt:
        return (
            f"Die Datenbank steht auf {sorted(db_stand)}; die Revision(en) "
            f"{sorted(unbekannt)} kennt dieser Code nicht. Die Datenbank wurde von "
            "einer neueren Fassung migriert — hier läuft ein älterer Stand. Ein "
            "`upgrade` hilft nicht."
        )

    return (
        f"Die Datenbank steht auf {sorted(db_stand)}, der Code erwartet "
        f"{sorted(kopf)}. Anwenden mit: {befehl}"
    )


async def pruefe_beim_start(session_factory) -> None:
    """Startprüfung. Wirft :class:`SchemaVeraltet` bei Abweichung.

    Ist die Datenbank nicht erreichbar oder der Stand nicht lesbar, bleibt es bei
    einer Warnung: Dann ist unbekannt, ob etwas fehlt, und eine Vermutung wäre eine
    schlechtere Auskunft als keine. Die übrigen Startprüfungen scheitern in dem Fall
    ohnehin an derselben Verbindung.
    """
    try:
        kopf = kopf_revisionen()
        bekannt = bekannte_revisionen()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Migrationsstand nicht prüfbar (Alembic-Konfiguration): %s", exc)
        return

    try:
        async with session_factory() as db:
            treffer = await db.execute(sa.text("SELECT version_num FROM alembic_version"))
            db_stand = {row[0] for row in treffer.all()}
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Migrationsstand nicht prüfbar (%s) — Tabelle alembic_version noch nicht da? "
            "Die Prüfung entfällt.", exc,
        )
        return

    meldung = abweichung(db_stand, kopf, bekannt)
    if meldung:
        raise SchemaVeraltet(meldung)

    logger.info("Datenbank auf Migrationsstand %s.", sorted(kopf))
