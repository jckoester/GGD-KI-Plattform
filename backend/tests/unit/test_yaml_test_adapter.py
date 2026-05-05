import yaml
from pathlib import Path

import pytest

from app.auth.adapters.yaml_test import YamlTestAdapter, YamlTestConfig
from app.auth.base import NormalizedIdentity


@pytest.fixture
def temp_users_file(tmp_path: Path):
    users_data = {
        "users": [
            {
                "username": "schueler10a",
                "password_hash": "$2b$12$/9DdLzVyejpZ6KJBopnYZubL.saVp.X0zOjhPUtLpa9tDLime0GrS",
                "roles": ["student"],
                "grade": "10a",
            },
            {
                "username": "lehrer01",
                "password_hash": "$2b$12$oK3VKqm5UJo/iEQv2iInR.nCUA3jBrZwu7v7dLvmQIovz1dZtiEl2",
                "roles": ["teacher"],
                "grade": None,
            },
            {
                "username": "admin",
                "password_hash": "$2b$12$j42wD/P9FYGN/7XhfbTVtuqP.tRwIk8DU1XNK6wOGZLqQwyvT5XaS",
                "roles": ["teacher", "admin"],
                "grade": None,
            },
        ]
    }
    users_file = tmp_path / "test_users.yaml"
    with open(users_file, "w") as f:
        yaml.dump(users_data, f)
    return str(users_file)


@pytest.fixture
def yaml_adapter(temp_users_file: str):
    return YamlTestAdapter(raw={"users_file": temp_users_file}, group_role_map={})


class TestYamlTestAdapter:
    @pytest.mark.asyncio
    async def test_valid_credentials_student(self, yaml_adapter: YamlTestAdapter):
        identity = await yaml_adapter.authenticate_direct("schueler10a", "schueler10a")
        assert identity is not None
        assert identity.external_id == "schueler10a"
        assert identity.roles == ["student"]
        assert identity.grade == "10a"

    @pytest.mark.asyncio
    async def test_valid_credentials_teacher(self, yaml_adapter: YamlTestAdapter):
        identity = await yaml_adapter.authenticate_direct("lehrer01", "lehrer01")
        assert identity is not None
        assert identity.external_id == "lehrer01"
        assert identity.roles == ["teacher"]
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_valid_credentials_admin(self, yaml_adapter: YamlTestAdapter):
        identity = await yaml_adapter.authenticate_direct("admin", "admin")
        assert identity is not None
        assert identity.external_id == "admin"
        assert identity.roles == ["teacher", "admin"]
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_wrong_password(self, yaml_adapter: YamlTestAdapter):
        identity = await yaml_adapter.authenticate_direct("lehrer01", "falsches_passwort")
        assert identity is None

    @pytest.mark.asyncio
    async def test_unknown_user(self, yaml_adapter: YamlTestAdapter):
        identity = await yaml_adapter.authenticate_direct("unknown", "password")
        assert identity is None

    def test_mode_is_direct(self, yaml_adapter: YamlTestAdapter):
        assert yaml_adapter.mode == "direct"

    @pytest.mark.asyncio
    async def test_get_login_challenge_returns_form(self, yaml_adapter: YamlTestAdapter):
        challenge = await yaml_adapter.get_login_challenge()
        assert challenge.type == "form"
        assert challenge.redirect_url is None
        assert challenge.state is None

    @pytest.mark.asyncio
    async def test_exchange_code_raises(self, yaml_adapter: YamlTestAdapter):
        with pytest.raises(NotImplementedError, match="YamlTestAdapter unterstützt kein OIDC"):
            await yaml_adapter.exchange_code("code", "state")


class TestYamlTestConfig:
    def test_config_parsing(self):
        config = YamlTestConfig(users_file="/path/to/users.yaml")
        assert config.users_file == "/path/to/users.yaml"


# =============================================================================
# Tests für sso_groups
# =============================================================================

@pytest.fixture
def temp_users_file_with_sso_groups(tmp_path: Path):
    users_data = {
        "users": [
            {
                "username": "lehrer01",
                "password_hash": "$2b$12$oK3VKqm5UJo/iEQv2iInR.nCUA3jBrZwu7v7dLvmQIovz1dZtiEl2",
                "roles": ["teacher"],
                "grade": None,
                "sso_groups": ["FS.Mathematik", "Klasse.8a", "unterricht.8a.Mathematik"],
            },
            {
                "username": "schueler05",
                "password_hash": "$2b$12$sABfBDqt5QFSJqgtEoLgLes0eQ8QRLaLw0E7VFp38pqrUrcPACK96",
                "roles": ["student"],
                "grade": "5",
                "sso_groups": ["Klasse.5", "unterricht.5.Mathematik"],
            },
            {
                "username": "admin",
                "password_hash": "$2b$12$j42wD/P9FYGN/7XhfbTVtuqP.tRwIk8DU1XNK6wOGZLqQwyvT5XaS",
                "roles": ["teacher", "admin"],
                "grade": None,
                # kein sso_groups-Feld → sollte [] werden
            },
        ]
    }
    users_file = tmp_path / "test_users.yaml"
    with open(users_file, "w") as f:
        yaml.dump(users_data, f)
    return str(users_file)


@pytest.fixture
def yaml_adapter_with_sso_groups(temp_users_file_with_sso_groups: str):
    return YamlTestAdapter(raw={"users_file": temp_users_file_with_sso_groups}, group_role_map={})


class TestYamlTestAdapterSsoGroups:
    """Tests für sso_groups in YamlTestAdapter."""

    @pytest.mark.asyncio
    async def test_sso_groups_loaded_from_yaml(self, yaml_adapter_with_sso_groups: YamlTestAdapter):
        """YamlTestAdapter lädt sso_groups aus der YAML-Datei."""
        user = yaml_adapter_with_sso_groups._users["lehrer01"]
        assert user.sso_groups == ["FS.Mathematik", "Klasse.8a", "unterricht.8a.Mathematik"]

    @pytest.mark.asyncio
    async def test_sso_groups_default_empty(self, yaml_adapter_with_sso_groups: YamlTestAdapter):
        """Nutzer ohne sso_groups-Feld bekommt leere Liste."""
        user = yaml_adapter_with_sso_groups._users["admin"]
        assert user.sso_groups == []

    @pytest.mark.asyncio
    async def test_sso_groups_in_identity(self, yaml_adapter_with_sso_groups: YamlTestAdapter):
        """sso_groups werden in NormalizedIdentity übergeben."""
        identity = await yaml_adapter_with_sso_groups.authenticate_direct("lehrer01", "lehrer01")
        assert identity is not None
        assert "FS.Mathematik" in identity.sso_groups
        assert "Klasse.8a" in identity.sso_groups
        assert "unterricht.8a.Mathematik" in identity.sso_groups

    @pytest.mark.asyncio
    async def test_sso_groups_in_identity_student(self, yaml_adapter_with_sso_groups: YamlTestAdapter):
        """sso_groups werden für Schüler korrekt übertragen."""
        # Das Passwort für schueler05 in der Test-YAML ist "schueler.pw"
        identity = await yaml_adapter_with_sso_groups.authenticate_direct("schueler05", "schueler.pw")
        assert identity is not None
        assert "Klasse.5" in identity.sso_groups
        assert "unterricht.5.Mathematik" in identity.sso_groups

    @pytest.mark.asyncio
    async def test_sso_groups_empty_in_identity(self, yaml_adapter_with_sso_groups: YamlTestAdapter):
        """Nutzer ohne sso_groups hat leere Liste in Identity."""
        identity = await yaml_adapter_with_sso_groups.authenticate_direct("admin", "admin")
        assert identity is not None
        assert identity.sso_groups == []
