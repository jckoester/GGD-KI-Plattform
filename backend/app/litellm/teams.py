from typing import Optional

from app.config import settings

TEACHER_TEAM_ID = "lehrkraefte"
STUDENT_TEAM_PREFIX = "jahrgang-"
VALID_GRADES: frozenset[int] = frozenset(settings.student_grades)


def normalize_grade(grade: int | str | None) -> Optional[int]:
    if grade is None:
        return None
    try:
        return int(grade)
    except (TypeError, ValueError):
        return None


def get_target_team_id(roles: list[str], grade: int | str | None) -> str:
    """
    Leitet die Phase-1 Zielteam-ID aus Rollen/Jahrgang ab.
    teacher hat Vorrang vor student.
    """
    if "teacher" in roles:
        return TEACHER_TEAM_ID

    if "student" in roles:
        grade_int = normalize_grade(grade)
        if grade_int is None:
            raise ValueError("Kein gültiger year/grade für student vorhanden")
        if grade_int not in VALID_GRADES:
            raise ValueError(f"Nicht unterstützter grade für Team: {grade_int}")
        return f"{STUDENT_TEAM_PREFIX}{grade_int}"

    raise ValueError(f"Kein Zielteam ableitbar für roles={roles}")


def is_phase1_team(team_id: str) -> bool:
    if team_id == TEACHER_TEAM_ID:
        return True
    if team_id.startswith(STUDENT_TEAM_PREFIX):
        try:
            return int(team_id[len(STUDENT_TEAM_PREFIX) :]) in VALID_GRADES
        except ValueError:
            return False
    return False
