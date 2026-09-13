import re
from typing import Literal

import yaml
from pydantic import BaseModel, computed_field, model_validator

from app.core.paths import aufloesen


class GroupRoleMapping(BaseModel):
    group: str
    role: Literal["student", "teacher", "admin", "review"]


class SsoGroupPatterns(BaseModel):
    """Reguläre Ausdrücke (je mindestens eine Capture-Group) für SSO-Gruppenmuster.

    **Benannte Gruppen (optional).** Zwei Namen haben eine Bedeutung:

    * ``(?P<fach>…)`` — das Fachkürzel. Ohne sie rät die Plattform: Sie nimmt das
      letzte punktgetrennte Segment (``unterricht.8a.mathematik`` → ``mathematik``).
      Das setzt voraus, dass die Schule ihre Gruppen so benennen *kann* — wer sie aus
      dem Stundenplan übernimmt, kann das oft nicht (``unterricht.ch2-ks-11``).
    * ``(?P<bezeichnung>…)`` — der Anzeigename der Gruppe. Ohne sie gilt Gruppe 1;
      sind benannte Gruppen im Spiel und fehlt ``bezeichnung``, bleibt die volle
      SSO-Kennung stehen. Das ist unschön, aber nie falsch.

    Für ``unterricht.<fach><nr>-<kürzel>-<klasse>`` also etwa::

        teaching_group: '^unterricht\\.(?P<bezeichnung>(?P<fach>[a-z]+)\\d*-.+)$'

    Das ``\\d*`` schneidet die Kursziffer ab (``ch2`` → ``ch``); das Fach selbst wird
    anschließend über ``subjects.slug`` **oder** ``subjects.sso_aliases`` aufgelöst.
    """

    subject_department: str | None = None  # z.B. "^FS\\.(.+)$"
    school_class: str | None = None  # z.B. "^Klasse\\.(.+)$"
    teaching_group: str | None = None  # z.B. "^unterricht\\.(.+)$"

    @model_validator(mode="after")
    def check_capture_groups(self) -> "SsoGroupPatterns":
        for field_name in ("subject_department", "school_class", "teaching_group"):
            pattern = getattr(self, field_name)
            if pattern is not None:
                try:
                    compiled = re.compile(pattern)
                except re.error as e:
                    raise ValueError(f"{field_name} ist kein gültiges Regex: {e}")
                if compiled.groups < 1:
                    raise ValueError(
                        f"{field_name} muss genau eine Capture-Group enthalten"
                    )
        return self


class SsoConfig(BaseModel):
    groups: SsoGroupPatterns = SsoGroupPatterns()
    allow_manual_teaching_groups: bool = True


class AuthConfig(BaseModel):
    adapter: Literal["oauth", "yaml_test"]
    oauth: dict = {}
    yaml_test: dict = {}
    group_role_map: list[GroupRoleMapping] = []
    sso: SsoConfig = SsoConfig()

    @computed_field
    @property
    def group_role_map_dict(
        self,
    ) -> dict[str, Literal["student", "teacher", "admin", "review"]]:
        """Konvertiert die Liste der GroupRoleMapping in ein Dictionary für schnellen Lookup."""
        result: dict[str, str] = {}
        for mapping in self.group_role_map:
            result[mapping.group] = mapping.role
        return result


def load_auth_config(path: str) -> AuthConfig:
    """Lädt die Auth-Konfiguration. Relative Pfade werden zentral aufgelöst.

    Die Auflösung sitzt hier und nicht an den fünf Aufrufstellen: Sonst hängt es davon
    ab, welche man erwischt, und eine neue vergisst sie.
    """
    with open(aufloesen(path)) as f:
        data = yaml.safe_load(f)
    return AuthConfig.model_validate(data)
