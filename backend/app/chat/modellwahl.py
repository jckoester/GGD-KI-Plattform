"""Wer im Chat welches Modell wählen darf (0.51, Päckchen AV).

**Schüler:innen bleiben beim Modell des Assistenten** (AV, Regel von Jan 21.11.2026). Dessen
Prompt ist für dieses Modell gemessen. Im freien Chat wählen sie weiter aus dem, was ihr
Jahrgang freigegeben hat. **Lehrkräfte** dürfen auch im Assistenten-Chat umstellen (F2:
bei allen Assistenten).

Bis 0.51 hielt das allein die Oberfläche durch (`chat/+page.svelte` schickte mit Assistent
kein Modell). Das Backend übernahm ein mitgeschicktes `model_id` von jeder Person, solange
es freigegeben war. Ein mitgeschicktes Modell einer Schüler:in wird jetzt **still verworfen**
und ins Log geschrieben (F6): Die Oberfläche schickt es nie, eine Ablehnung träfe nur einen
Chat, der dann abbräche.

Die Vorschau zählt als Schüler:in: Ihr Token trägt nur die Rolle `student`.
"""
import logging

from app.auth.jwt import JwtPayload

logger = logging.getLogger(__name__)


def darf_im_assistenten_waehlen(user: JwtPayload) -> bool:
    """Lehrkräfte (und Admins, die immer auch Lehrkraft sind) — nicht Schüler:innen, nicht die Vorschau."""
    return "teacher" in (user.roles or [])


def wahl_im_assistenten(model_id: str | None, user: JwtPayload, assistant_id=None) -> str | None:
    """Das mitgeschickte Modell, wenn diese Person es bei aktivem Assistenten wählen darf, sonst ``None``."""
    if not model_id or darf_im_assistenten_waehlen(user):
        return model_id
    logger.info("Modellwahl im Assistenten-Chat verworfen (keine Lehrkraft) assistant_id=%s model_id=%s",
                assistant_id, model_id)
    return None


def braucht_funktionen_text(modell: str) -> str:
    return (f"Dieser Assistent braucht ein Modell mit Funktionen (⚙). „{modell}“ kann keine "
            "Funktionen aufrufen — wähle ein Modell mit ⚙.")


def fehlen_funktionen(assistant, modell: str, des_assistenten: str, funktionsaufrufe: dict) -> bool:
    """Hat jemand für einen Assistenten mit Fähigkeiten ein Modell gewählt, das keine Funktionen kann?

    (AV F3.) Bis 0.51 schickte der Chat die Funktionen dann einfach nicht mit: Ein Planungs-
    oder Curriculum-Assistent lief ohne Lesen und Schreiben, ohne Hinweis.

    - Nur ein **gewähltes** Modell zählt. Läuft der Assistent mit seinem eigenen Modell, bleibt
      es beim bisherigen Verhalten — sonst bräche ein so eingerichteter Assistent für alle,
      auch für Schüler:innen, die nichts wählen können.
    - ``None`` (unbekannt) sperrt nicht, wie überall bei den Modell-Eigenschaften.
    """
    if assistant is None or not (assistant.tool_groups or []) or modell == des_assistenten:
        return False
    return funktionsaufrufe.get(modell) is False


# ── Bevorzugte Modelle der Lehrkraft (0.51, AV Schritt 3, F4) ──────────────────
#
# Zwei Schlüssel in `user_preferences.preferences`: eines für freie Chats, eines für
# Planungs-Assistenten (`plant`). Nur für Lehrkräfte (F8). Geprüft beim Speichern; ob die Wahl
# beim Anlegen eines Chats noch gilt (Freigabe geändert, Modell entfernt), prüft Schritt 4.

BEVORZUGT_FREI = "modell_frei"
BEVORZUGT_PLANUNG = "modell_planung"
BEVORZUGT_SCHLUESSEL = (BEVORZUGT_FREI, BEVORZUGT_PLANUNG)


async def pruefe_bevorzugtes_modell(schluessel: str, wert, user: JwtPayload) -> str | None:
    """Das Modell, wie es gespeichert wird (``None`` = keine Vorliebe). Wirft ``ValueError``
    (unzulässig) oder ``PermissionError`` (keine Lehrkraft)."""
    from app.config import settings
    from app.litellm.modell_eigenschaften import alle_eigenschaften
    from app.litellm.team_models import erlaubte_modelle_fuer

    if not darf_im_assistenten_waehlen(user):
        raise PermissionError("Bevorzugte Modelle gibt es für Lehrkräfte.")
    if wert in (None, ""):
        return None
    if not isinstance(wert, str):
        raise ValueError("Das Modell muss als Name angegeben werden.")
    modell = wert.strip()
    if any(modell.startswith(p) for p in settings.model_picker_hidden_prefixes):
        raise ValueError(f"„{modell}“ ist kein Chat-Modell.")
    erlaubt = await erlaubte_modelle_fuer(user.roles, getattr(user, "grade", None))
    if erlaubt is not None and modell not in erlaubt:
        raise ValueError(f"„{modell}“ ist für dich nicht freigeschaltet.")
    if schluessel == BEVORZUGT_PLANUNG:
        eigenschaften = (await alle_eigenschaften()).get(modell)
        if eigenschaften is not None and eigenschaften.funktionsaufrufe is False:
            raise ValueError(braucht_funktionen_text(modell).replace("Dieser Assistent braucht",
                                                                     "Planungs-Assistenten brauchen"))
    return modell
