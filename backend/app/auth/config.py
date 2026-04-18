import yaml
from typing import Literal

from pydantic import BaseModel


class GroupRoleMapping(BaseModel):
    group: str
    role: Literal["student", "teacher", "admin"]


class AuthConfig(BaseModel):
    adapter: Literal["iserv", "yaml_test"]
    iserv: dict = {}
    yaml_test: dict = {}
    group_role_map: list[GroupRoleMapping] = []


def load_auth_config(path: str) -> AuthConfig:
    with open(path) as f:
        data = yaml.safe_load(f)
    return AuthConfig.model_validate(data)
