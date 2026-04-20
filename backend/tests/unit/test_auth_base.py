import pytest
import yaml

from pydantic import ValidationError

from app.auth.base import AuthAdapter, LoginChallenge, NormalizedIdentity
from app.auth.config import AuthConfig


class TestNormalizedIdentity:
    def test_valid_roles(self):
        for role in ("student", "teacher", "admin"):
            grade = "9b" if role == "student" else None
            ident = NormalizedIdentity(external_id="testuser", roles=[role], grade=grade)
            assert ident.roles == [role]

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            NormalizedIdentity(external_id="x", roles=["principal"], grade=None)

    def test_grade_only_for_student(self):
        with pytest.raises(ValidationError, match="grade"):
            NormalizedIdentity(external_id="x", roles=["teacher"], grade="10a")


class TestAuthConfig:
    def test_iserv_variant(self):
        yaml_str = """
adapter: iserv
iserv:
  base_url: https://iserv.example.de
  client_id: test
  redirect_uri: https://ki.example.de/auth/callback
group_role_map:
  - group: lehrer
    role: teacher
"""
        config = AuthConfig.model_validate(yaml.safe_load(yaml_str))
        assert config.adapter == "iserv"
        assert config.iserv["client_id"] == "test"
        assert config.group_role_map[0].role == "teacher"

    def test_yaml_test_variant(self):
        config = AuthConfig.model_validate({"adapter": "yaml_test", "yaml_test": {"users_file": "x.yaml"}})
        assert config.adapter == "yaml_test"
        assert config.yaml_test["users_file"] == "x.yaml"

    def test_adapter_specific_config_passed_through_as_dict(self):
        config = AuthConfig.model_validate({"adapter": "iserv", "iserv": {"base_url": "https://x.de"}})
        assert config.iserv["base_url"] == "https://x.de"
        assert config.yaml_test == {}


class TestAuthAdapter:
    def test_abc_cannot_be_instantiated(self):
        with pytest.raises(TypeError):
            AuthAdapter()

    @pytest.mark.asyncio
    async def test_stub_adapter_fulfills_interface(self):
        class StubAdapter(AuthAdapter):
            @property
            def mode(self):
                return "direct"

            async def get_login_challenge(self):
                return LoginChallenge(type="form")

            async def exchange_code(self, code, state):
                raise NotImplementedError

            async def authenticate_direct(self, username, password):
                return None

        adapter = StubAdapter()
        assert adapter.mode == "direct"
        challenge = await adapter.get_login_challenge()
        assert challenge.type == "form"
