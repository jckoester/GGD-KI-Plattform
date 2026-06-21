import pytest
import yaml
from app.auth.base import AuthAdapter, LoginChallenge, NormalizedIdentity
from app.auth.config import AuthConfig
from pydantic import ValidationError


class TestNormalizedIdentity:
    def test_valid_roles(self):
        for role in ("student", "teacher", "admin"):
            grade = "9b" if role == "student" else None
            ident = NormalizedIdentity(
                external_id="testuser", roles=[role], grade=grade
            )
            assert ident.roles == [role]

    def test_invalid_role(self):
        with pytest.raises(ValidationError):
            NormalizedIdentity(external_id="x", roles=["principal"], grade=None)

    def test_review_role_standalone_valid(self):
        # review (Schulsozialarbeit) darf ohne Basisrolle gültig sein
        ident = NormalizedIdentity(external_id="sozial01", roles=["review"], grade=None)
        assert ident.roles == ["review"]

    def test_review_role_additive_to_teacher_valid(self):
        ident = NormalizedIdentity(
            external_id="x", roles=["teacher", "review"], grade=None
        )
        assert "review" in ident.roles

    def test_pure_extra_role_without_login_role_rejected(self):
        # budget/statistics sind keine eigenständigen Login-Rollen
        with pytest.raises(ValidationError, match="Login-Rolle"):
            NormalizedIdentity(external_id="x", roles=["budget"], grade=None)

    def test_grade_only_for_student(self):
        with pytest.raises(ValidationError, match="grade"):
            NormalizedIdentity(external_id="x", roles=["teacher"], grade="10a")


class TestAuthConfig:
    def test_oauth_variant(self):
        yaml_str = """
adapter: oauth
oauth:
  base_url: https://iserv.example.de
  client_id: test
  redirect_uri: https://ki.example.de/auth/callback
group_role_map:
  - group: lehrer
    role: teacher
"""
        config = AuthConfig.model_validate(yaml.safe_load(yaml_str))
        assert config.adapter == "oauth"
        assert config.oauth["client_id"] == "test"
        assert config.group_role_map[0].role == "teacher"

    def test_yaml_test_variant(self):
        config = AuthConfig.model_validate(
            {"adapter": "yaml_test", "yaml_test": {"users_file": "x.yaml"}}
        )
        assert config.adapter == "yaml_test"
        assert config.yaml_test["users_file"] == "x.yaml"

    def test_adapter_specific_config_passed_through_as_dict(self):
        config = AuthConfig.model_validate(
            {"adapter": "oauth", "oauth": {"base_url": "https://x.de"}}
        )
        assert config.oauth["base_url"] == "https://x.de"
        assert config.yaml_test == {}

    def test_group_role_map_review(self):
        config = AuthConfig.model_validate(
            {
                "adapter": "yaml_test",
                "yaml_test": {"users_file": "x.yaml"},
                "group_role_map": [{"group": "ki-reviewer", "role": "review"}],
            }
        )
        assert config.group_role_map[0].role == "review"
        assert config.group_role_map_dict["ki-reviewer"] == "review"


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
