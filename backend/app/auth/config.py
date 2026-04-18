import yaml
from typing import Literal

from pydantic import BaseModel, computed_field


class GroupRoleMapping(BaseModel):
    group: str
    role: Literal["student", "teacher", "admin"]


class AuthConfig(BaseModel):
    adapter: Literal["iserv", "yaml_test"]
    iserv: dict = {}
    yaml_test: dict = {}
    group_role_map: list[GroupRoleMapping] = []

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
