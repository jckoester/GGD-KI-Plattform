from datetime import datetime
from typing import Optional

from fastapi import HTTPException

VALID_AUDIENCES = {"student", "teacher", "all"}
VALID_SCOPES = {
    "private", "subject_department", "teachers", "activity_group",
    "teaching_group", "grade", "all_students", "all",
}
GROUP_SCOPES = {"subject_department", "activity_group", "teaching_group"}


def validate_assistant_fields(
    name: Optional[str] = None,
    system_prompt: Optional[str] = None,
    audience: Optional[str] = None,
    scope: Optional[str] = None,
    scope_group_id: Optional[int] = None,
    min_grade: Optional[int] = None,
    max_grade: Optional[int] = None,
    available_from: Optional[datetime] = None,
    available_until: Optional[datetime] = None,
) -> None:
    """Validiert Business-Regeln für Assistenten. Wirft HTTPException(422)."""
    if name is not None and not name.strip():
        raise HTTPException(status_code=422, detail="name darf nicht leer sein")
    if system_prompt is not None and not system_prompt.strip():
        raise HTTPException(status_code=422, detail="system_prompt darf nicht leer sein")
    if audience is not None and audience not in VALID_AUDIENCES:
        raise HTTPException(status_code=422, detail="Ungültiger audience-Wert")
    if scope is not None and scope not in VALID_SCOPES:
        raise HTTPException(status_code=422, detail="Ungültiger scope-Wert")
    if scope is not None and scope in GROUP_SCOPES and scope_group_id is None:
        raise HTTPException(
            status_code=422, detail="Gruppen-Scope erfordert eine scope_group_id"
        )
    if scope is not None and scope not in GROUP_SCOPES and scope_group_id is not None:
        raise HTTPException(
            status_code=422, detail="scope_group_id darf nur bei Gruppen-Scopes gesetzt sein"
        )
    if audience == "teacher" and scope in {"all_students", "all"}:
        raise HTTPException(
            status_code=422,
            detail="teacher-Assistenten dürfen nicht für Schüler:innen sichtbar sein",
        )
    if available_from is not None and available_until is not None:
        if available_from >= available_until:
            raise HTTPException(
                status_code=422, detail="available_from muss vor available_until liegen"
            )
    if min_grade is not None and max_grade is not None:
        if min_grade > max_grade:
            raise HTTPException(
                status_code=422, detail="min_grade darf nicht größer als max_grade sein"
            )
