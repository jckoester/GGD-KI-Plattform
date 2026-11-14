from sqlalchemy import bindparam, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession


async def get_preferences(db: AsyncSession, pseudonym: str) -> dict:
    result = await db.execute(
        text("SELECT preferences FROM user_preferences WHERE pseudonym = :pseudonym"),
        {"pseudonym": pseudonym},
    )
    row = result.fetchone()
    return row[0] if row else {}


async def patch_preferences(db: AsyncSession, pseudonym: str, updates: dict) -> dict:
    result = await db.execute(
        text("SELECT preferences FROM user_preferences WHERE pseudonym = :pseudonym"),
        {"pseudonym": pseudonym},
    )
    row = result.fetchone()
    current = row[0] if row else {}
    merged = {**current, **updates}
    await db.execute(
        text("""
            INSERT INTO user_preferences (pseudonym, preferences)
            VALUES (:pseudonym, :preferences)
            ON CONFLICT (pseudonym) DO UPDATE SET preferences = EXCLUDED.preferences
        """).bindparams(bindparam("preferences", type_=JSONB())),
        {"pseudonym": pseudonym, "preferences": merged},
    )
    await db.commit()
    return merged


# Grenzen der **Anzeige**zahl im Vorschlagsfenster. Untergrenze, damit eine Liste
# überhaupt Auswahl bietet; Obergrenze, damit sie das Eingabefeld nicht zudeckt.
ANZEIGE_MIN = 5
ANZEIGE_MAX = 30
ANZEIGE_VORGABE = 8


async def anzeige_limit(db: AsyncSession, pseudonym: str) -> int:
    """Wie viele Kontextvorschläge angezeigt werden (`context_search_limit`).

    ⚠️ Betrifft **nur die Anzeige**, nicht die Suchtiefe des Assistenten — die steht
    zentral in `ASSISTANT_CONTEXT_LIMIT`. Die 8 waren ursprünglich gewählt, um das
    Vorschlagsfenster nicht zu überfrachten; für einen Assistenten ist das eine
    Kosten-, keine Platzfrage.

    Gibt eine **Zahl** zurück, nicht das Einstellungs-Dict. Das ist keine Bequemlichkeit:
    Die Einstellungen enthalten unter anderem das WebUntis-Kürzel, und modellnahe Module
    (Chat, Kontextspeicher) dürfen damit nicht in Berührung kommen — sonst könnte es
    unbemerkt in einen Prompt geraten. Ein Test in `test_calendar_kuerzel.py` hält fest,
    dass `get_preferences` außerhalb dieses Moduls gar nicht mehr gelesen wird.

    Der Schlüsselname `context_search_limit` bleibt historisch — ihn umzubenennen würde
    die Einstellung aller Nutzer:innen auf die Vorgabe zurücksetzen.
    """
    prefs = await get_preferences(db, pseudonym)
    try:
        wert = int(prefs.get("context_search_limit", ANZEIGE_VORGABE))
    except (TypeError, ValueError):
        return ANZEIGE_VORGABE
    return max(ANZEIGE_MIN, min(ANZEIGE_MAX, wert))


# ── Hinweise auf Neuerungen (0.17, `app/neuigkeiten`) ────────────────────────
#
# Wie `anzeige_limit`: Das Einstellungs-Dict verlässt dieses Modul nicht. Die Neuigkeiten
# brauchen nur zwei Werte daraus — die Darstellungsstufe und die weggeklickten Hinweise.

NEUIGKEITEN_SCHLUESSEL = "neuigkeiten_gelesen"


async def ui_stufe(db: AsyncSession, pseudonym: str, rollen: list[str]) -> int | None:
    """Die wirksame Darstellungsstufe (`stufe_fuer`); ``None``: Für die Rolle gibt es keine."""
    from app.ui.levels import stufe_fuer

    return stufe_fuer(await get_preferences(db, pseudonym), rollen)


async def neuigkeiten_gelesen(db: AsyncSession, pseudonym: str) -> set[str]:
    """Die Kennungen der Hinweise, die die Person weggeklickt hat."""
    wert = (await get_preferences(db, pseudonym)).get(NEUIGKEITEN_SCHLUESSEL)
    return {str(x) for x in wert} if isinstance(wert, list) else set()


async def neuigkeit_gelesen_merken(db: AsyncSession, pseudonym: str, kennung: str) -> None:
    """Hängt die Kennung an — doppelt wird nichts, ein zweiter Aufruf ändert nichts."""
    gelesen = await neuigkeiten_gelesen(db, pseudonym)
    if kennung in gelesen:
        return
    await patch_preferences(db, pseudonym, {NEUIGKEITEN_SCHLUESSEL: sorted(gelesen | {kennung})})


# ── Urheber in der Assistenten-Freigabe (0.27, Plan F4) ──────────────────────
#
# Admins sehen bei eingereichten Assistenten das Stundenplan-Kürzel der Lehrkraft, falls sie
# eins hinterlegt hat (Jan, 31.10.2026). Ein zweiter Zweck für eine freiwillige Angabe —
# deshalb steht er beim Kürzel auf der Seite „Unterricht“ und in der Admin-Doku. Wie die
# übrigen Leser hier: nur der eine Wert, nie das Dict, und nichts davon geht an ein Modell.


async def stundenplan_kuerzel(db: AsyncSession, pseudonyme: list[str]) -> dict[str, str]:
    """Kürzel je Pseudonym — nur, wer eins hinterlegt hat."""
    from app.calendar.service import KUERZEL_PREFERENCE_KEY

    if not pseudonyme:
        return {}
    zeilen = (await db.execute(
        text("SELECT pseudonym, preferences ->> :schluessel FROM user_preferences "
             "WHERE pseudonym = ANY(:pseudonyme)"),
        {"schluessel": KUERZEL_PREFERENCE_KEY, "pseudonyme": list(pseudonyme)},
    )).all()
    return {p: k.strip() for p, k in zeilen if k and k.strip()}


# ── Stand der Einrichtung (0.43, `app/einrichtung`) ──────────────────────────
#
# Wie oben: Das Einstellungs-Dict verlässt dieses Modul nicht. Die Einrichtung braucht
# ihren eigenen Stand und, ob ein Kürzel gesetzt ist — nicht das Kürzel selbst.

EINRICHTUNG_SCHLUESSEL = "einrichtung"


async def einrichtung_lesen(db: AsyncSession, pseudonym: str) -> tuple[dict | None, bool]:
    """Gespeicherter Stand der Einrichtung (oder ``None``) und ob ein Stundenplan-Kürzel gesetzt ist."""
    from app.calendar.service import KUERZEL_PREFERENCE_KEY

    prefs = await get_preferences(db, pseudonym)
    stand = prefs.get(EINRICHTUNG_SCHLUESSEL)
    kuerzel = prefs.get(KUERZEL_PREFERENCE_KEY)
    return (stand if isinstance(stand, dict) else None,
            isinstance(kuerzel, str) and bool(kuerzel.strip()))


async def einrichtung_speichern(db: AsyncSession, pseudonym: str, stand: dict) -> None:
    await patch_preferences(db, pseudonym, {EINRICHTUNG_SCHLUESSEL: stand})
