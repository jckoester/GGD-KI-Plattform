from functools import lru_cache

from app.auth.base import AuthAdapter
from app.auth.config import load_auth_config
from app.config import settings


@lru_cache(maxsize=1)
def get_auth_adapter() -> AuthAdapter:
    auth_config = load_auth_config(settings.auth_config_path)
    group_role_map = auth_config.group_role_map_dict
    if auth_config.adapter == "iserv":
        from app.auth.adapters.iserv import IServAdapter
        return IServAdapter(auth_config.iserv, settings, group_role_map)
    elif auth_config.adapter == "yaml_test":
        from app.auth.adapters.yaml_test import YamlTestAdapter
        return YamlTestAdapter(auth_config.yaml_test, group_role_map)
    raise ValueError(f"Unbekannter Adapter: {auth_config.adapter}")
