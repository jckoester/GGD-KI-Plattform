import re
import yaml
from typing import Literal

from pydantic import BaseModel, computed_field, model_validator


class GroupRoleMapping(BaseModel):
    group: str
    role: Literal["student", "teacher", "admin"]


class SsoGroupPatterns(BaseModel):
    """Reguläre Ausdrücke (je eine Capture-Group) für SSO-Gruppenmuster."""
    subject_department: str | None = None  # z.B. "^FS\\.(.+)$"
    school_class: str | None = None        # z.B. "^Klasse\\.(.+)$"
    teaching_group: str | None = None      # z.B. "^unterricht\\.(.+)$"

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


class AuthConfig(BaseModel):
    adapter: Literal["iserv", "yaml_test"]
    iserv: dict = {}
    yaml_test: dict = {}
    group_role_map: list[GroupRoleMapping] = []
    sso: SsoConfig = SsoConfig()  # NEU

    @computed_field
    @property
    def group_role_map_dict(self) -> dict[str, Literal["student", "teacher", "admin"]]:
        """Konvertiert die Liste der GroupRoleMapping in ein Dictionary für schnellen Lookup."""
        result: dict[str, str] = {}
        for mapping in self.group_role_map:
            result[mapping.group] = mapping.role
        return result


def load_auth_config(path: str) -> AuthConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return AuthConfig.model_validate(data)
