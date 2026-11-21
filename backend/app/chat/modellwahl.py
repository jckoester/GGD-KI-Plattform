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
