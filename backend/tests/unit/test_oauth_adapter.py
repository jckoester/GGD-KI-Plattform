import hashlib
import hmac
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from app.auth.adapters.oauth import OAuthAdapter, OAuthConfig, _as_str_list
from app.config import Settings


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.auth_iserv_client_secret = "test_client_secret"
    settings.school_secret = "test_school_secret"
    settings.auth_debug_userinfo = False
    return settings


@pytest.fixture
def oauth_config_dict():
    return {
        "base_url": "https://iserv.example.de",
        "client_id": "test_client_id",
        "redirect_uri": "https://ki.example.de/auth/callback",
        "grade_group_pattern": r"^jahrgang\.(\d{1,2})$",
    }


@pytest.fixture
def oauth_adapter(mock_settings, oauth_config_dict):
    return OAuthAdapter(
        raw=oauth_config_dict,
        settings=mock_settings,
        group_role_map={
            "ki-admins": "admin",
            "lehrer": "teacher",
            "schueler": "student",
        },
    )


@pytest.fixture
def oauth_adapter_no_pattern(mock_settings, oauth_config_dict):
    config = {**oauth_config_dict, "grade_group_pattern": None}
    return OAuthAdapter(raw=config, settings=mock_settings, group_role_map={})


def _make_mock_client(token_response, userinfo_response):
    async def mock_post(*args, **kwargs):
        return token_response

    async def mock_get(*args, **kwargs):
        return userinfo_response

    client = MagicMock()
    client.post = mock_post
    client.get = mock_get
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


def _mock_token(access_token="test_token"):
    resp = MagicMock()
    resp.json.return_value = {"access_token": access_token}
    resp.raise_for_status = MagicMock()
    return resp


def _mock_userinfo(username, groups, roles=None):
    resp = MagicMock()
    body = {"preferred_username": username, "groups": groups}
    if roles is not None:
        body["roles"] = roles
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


class TestOAuthConfig:
    def test_valid_config(self, oauth_config_dict):
        config = OAuthConfig.model_validate(oauth_config_dict)
        assert config.base_url == "https://iserv.example.de"
        assert config.client_id == "test_client_id"

    def test_invalid_pattern_no_capture_group(self):
        with pytest.raises(
            ValueError,
            match="grade_group_pattern muss genau eine Capture-Group enthalten",
        ):
            OAuthConfig(
                base_url="https://iserv.example.de",
                client_id="client_id",
                redirect_uri="https://ki.example.de/auth/callback",
                grade_group_pattern=r"^jahrgang\.\d{1,2}$",
            )

    def test_invalid_pattern_syntax(self):
        with pytest.raises(
            ValueError, match="grade_group_pattern ist kein gültiges Regex"
        ):
            OAuthConfig(
                base_url="https://iserv.example.de",
                client_id="client_id",
                redirect_uri="https://ki.example.de/auth/callback",
                grade_group_pattern="[invalid",
            )

    def test_none_pattern_is_valid(self):
        config = OAuthConfig(
            base_url="https://iserv.example.de",
            client_id="client_id",
            redirect_uri="https://ki.example.de/auth/callback",
            grade_group_pattern=None,
        )
        assert config.grade_group_pattern is None

    def test_default_scope_includes_iserv_groups(self, oauth_config_dict):
        """Ohne explizite Angabe wird der IServ-Scope `iserv:groups` angefordert."""
        config = OAuthConfig.model_validate(oauth_config_dict)
        assert "iserv:groups" in config.scope.split()
        assert "iserv:roles" in config.scope.split()

    def test_scope_is_configurable(self):
        config = OAuthConfig(
            base_url="https://iserv.example.de",
            client_id="c",
            redirect_uri="https://ki.example.de/auth/callback",
            scope="openid groups roles",
        )
        assert config.scope == "openid groups roles"


class TestOAuthAdapter:
    def test_mode_is_redirect(self, oauth_adapter):
        assert oauth_adapter.mode == "redirect"

    @pytest.mark.asyncio
    async def test_get_login_challenge_returns_redirect(self, oauth_adapter):
        challenge = await oauth_adapter.get_login_challenge()
        assert challenge.type == "redirect"
        assert challenge.redirect_url is not None
        assert "client_id=test_client_id" in challenge.redirect_url
        assert "redirect_uri=" in challenge.redirect_url
        assert "state=" in challenge.redirect_url
        assert "scope=" in challenge.redirect_url
        assert "groups" in challenge.redirect_url  # groups-Scope wird angefordert
        assert challenge.state is not None

    @pytest.mark.asyncio
    async def test_state_contains_valid_hmac(self, oauth_adapter):
        challenge = await oauth_adapter.get_login_challenge()
        state = challenge.state
        assert state is not None
        nonce, received_sig = state.rsplit(".", 1)
        expected_sig = hmac.new(
            oauth_adapter._school_secret.encode(),
            nonce.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(expected_sig, received_sig)

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, oauth_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("testuser", ["schueler", "jahrgang.10"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert identity.external_id == "testuser"
        assert identity.roles == ["student"]
        assert identity.grade == "10"

    @pytest.mark.asyncio
    async def test_exchange_code_maps_group_to_role(self, oauth_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("teacher_user", ["lehrer"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert identity.roles == ["teacher"]
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_exchange_code_extracts_grade(self, oauth_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("student_user", ["schueler", "jahrgang.10"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert identity.roles == ["student"]
        assert identity.grade == "10"

    @pytest.mark.asyncio
    async def test_extract_grade_no_pattern(self, oauth_adapter_no_pattern):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("user1", ["jahrgang.10", "other"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter_no_pattern.get_login_challenge()
            identity = await oauth_adapter_no_pattern.exchange_code(
                "test_code", challenge.state
            )
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_extract_grade_no_match(self, oauth_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("user1", ["klasse.10a", "other"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state(self, oauth_adapter):
        with pytest.raises(ValueError, match="State-Signatur ungültig"):
            await oauth_adapter.exchange_code("code", "invalid.state")

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state_format(self, oauth_adapter):
        with pytest.raises(ValueError, match="Ungültiges State-Format"):
            await oauth_adapter.exchange_code("code", "nostatehere")

    @pytest.mark.asyncio
    async def test_exchange_code_token_error(self, oauth_adapter):
        token_resp = MagicMock()
        token_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=MagicMock()
        )
        mock_client = _make_mock_client(token_resp, MagicMock())
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            with pytest.raises(httpx.HTTPStatusError):
                await oauth_adapter.exchange_code("test_code", challenge.state)

    @pytest.mark.asyncio
    async def test_authenticate_direct_raises(self, oauth_adapter):
        with pytest.raises(
            NotImplementedError, match="OAuthAdapter unterstützt kein direktes Login"
        ):
            await oauth_adapter.authenticate_direct("user", "pass")

    @pytest.mark.asyncio
    async def test_sso_groups_passed_to_identity(self, oauth_adapter):
        """OAuthAdapter übergibt SSO-Gruppen unverändert an NormalizedIdentity."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("testuser", ["FS.Mathematik", "Klasse.8a", "lehrer"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert "FS.Mathematik" in identity.sso_groups
        assert "Klasse.8a" in identity.sso_groups
        assert "lehrer" in identity.sso_groups
        assert len(identity.sso_groups) == 3

    @pytest.mark.asyncio
    async def test_sso_groups_empty_when_no_groups(self, oauth_adapter):
        """Ohne groups-Claim ist sso_groups leer."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("testuser", []),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert identity.sso_groups == []

    @pytest.mark.asyncio
    async def test_sso_groups_empty_when_no_groups_key(self, oauth_adapter):
        """Fehlender groups-Claim ergibt leere sso_groups."""
        resp = MagicMock()
        resp.json.return_value = {"preferred_username": "testuser"}
        resp.raise_for_status = MagicMock()
        mock_client = _make_mock_client(_mock_token(), resp)
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            challenge = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("test_code", challenge.state)
        assert identity.sso_groups == []


# =============================================================================
# Rollen-Matching: Gruppen + Rollen, case-insensitiv (Kollegium / IServ-Rollen)
# =============================================================================


def _adapter_with_map(mock_settings, config, role_map):
    return OAuthAdapter(raw=config, settings=mock_settings, group_role_map=role_map)


class TestRoleMatching:
    @pytest.mark.asyncio
    async def test_iserv_role_claim_maps_to_role(self, oauth_adapter):
        """Die IServ-Rolle `Lehrer` (roles-Claim) trifft die Config `lehrer`."""
        mock_client = _make_mock_client(
            _mock_token(), _mock_userinfo("t", groups=[], roles=["Lehrer"])
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["teacher"]

    @pytest.mark.asyncio
    async def test_group_match_is_case_insensitive(self, oauth_adapter):
        """Gruppen-Schreibweise egal: `LEHRER` trifft Config `lehrer`."""
        mock_client = _make_mock_client(
            _mock_token(), _mock_userinfo("t", groups=["LEHRER"])
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["teacher"]

    @pytest.mark.asyncio
    async def test_kollegium_group_maps_to_teacher(self, mock_settings, oauth_config_dict):
        """Schul-spezifische Gruppe `Kollegium` → teacher (IServ liefert klein)."""
        adapter = _adapter_with_map(
            mock_settings, oauth_config_dict, {"Kollegium": "teacher"}
        )
        mock_client = _make_mock_client(
            _mock_token(), _mock_userinfo("t", groups=["kollegium"])
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await adapter.get_login_challenge()
            identity = await adapter.exchange_code("c", ch.state)
        assert identity.roles == ["teacher"]

    @pytest.mark.asyncio
    async def test_groups_and_roles_are_unioned(self, oauth_adapter):
        """Gruppen UND Rollen matchen: ki-admins (Gruppe) + Lehrer (Rolle)."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("t", groups=["ki-admins"], roles=["Lehrer"]),
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert set(identity.roles) == {"admin", "teacher"}

    @pytest.mark.asyncio
    async def test_sso_roles_passed_to_identity(self, oauth_adapter):
        """Der rohe roles-Claim landet unverändert in sso_roles (Diagnose)."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("t", groups=["Kollegium"], roles=["Lehrer", "Administrator"]),
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.sso_roles == ["Lehrer", "Administrator"]
        assert identity.sso_groups == ["Kollegium"]

    @pytest.mark.asyncio
    async def test_unmapped_group_falls_back_to_student(self, oauth_adapter):
        """Bug-Fall vor Config-Fix: `Kollegium` ungemappt → student-Fallback."""
        mock_client = _make_mock_client(
            _mock_token(), _mock_userinfo("t", groups=["Kollegium"])
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["student"]

    @pytest.mark.asyncio
    async def test_grade_extraction_is_case_insensitive(self, oauth_adapter):
        """Jahrgang case-insensitiv: `JAHRGANG.10` → grade 10."""
        mock_client = _make_mock_client(
            _mock_token(), _mock_userinfo("t", groups=["schueler", "JAHRGANG.10"])
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["student"]
        assert identity.grade == "10"

    @pytest.mark.asyncio
    async def test_grade_dropped_for_non_student(self, oauth_adapter):
        """Lehrkraft mit jahrgang-Gruppe: grade wird verworfen (Invariante)."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("t", groups=["jahrgang.10"], roles=["Lehrer"]),
        )
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["teacher"]
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_reads_iserv_prefixed_claim_keys(self, oauth_adapter):
        """Claims unter `iserv:groups`/`iserv:roles` werden ebenfalls gelesen."""
        resp = MagicMock()
        resp.json.return_value = {
            "preferred_username": "t",
            "iserv:groups": ["Kollegium", "FS.Mathematik"],
            "iserv:roles": ["Lehrer"],
        }
        resp.raise_for_status = MagicMock()
        mock_client = _make_mock_client(_mock_token(), resp)
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["teacher"]
        assert identity.sso_groups == ["Kollegium", "FS.Mathematik"]
        assert identity.sso_roles == ["Lehrer"]

    @pytest.mark.asyncio
    async def test_object_shaped_claims_do_not_crash(self, oauth_adapter):
        """Gruppen/Rollen als Objekte (statt Strings) brechen den Login nicht."""
        resp = MagicMock()
        resp.json.return_value = {
            "preferred_username": "t",
            "groups": [{"name": "Kollegium"}, {"act": "fs.mathematik"}],
            "roles": [{"name": "Lehrer"}],
        }
        resp.raise_for_status = MagicMock()
        mock_client = _make_mock_client(_mock_token(), resp)
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await oauth_adapter.get_login_challenge()
            identity = await oauth_adapter.exchange_code("c", ch.state)
        assert identity.roles == ["teacher"]  # über die Rolle "Lehrer"
        assert identity.sso_groups == ["Kollegium", "fs.mathematik"]
        assert identity.sso_roles == ["Lehrer"]

    @pytest.mark.asyncio
    async def test_real_iserv_shape_end_to_end(self, mock_settings, oauth_config_dict):
        """Realistische IServ-userinfo: ROLE_TEACHER → teacher, Gruppen = act-Werte."""
        adapter = _adapter_with_map(
            mock_settings,
            oauth_config_dict,
            {"ROLE_TEACHER": "teacher", "ROLE_STUDENT": "student", "ki-admins": "admin"},
        )
        resp = MagicMock()
        resp.json.return_value = {
            "preferred_username": "t",
            "iserv:groups": {
                "1": {"id": "1", "act": "kollegium", "name": "Kollegium"},
                "2": {"id": "2", "act": "fs.mathematik", "name": "FS Mathematik"},
                "3": {"id": "3", "act": "klasse.8d", "name": "Klasse 8D"},
            },
            "iserv:roles": ["ROLE_TEACHER", "ROLE_ADMIN"],
        }
        resp.raise_for_status = MagicMock()
        mock_client = _make_mock_client(_mock_token(), resp)
        with patch("app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client):
            ch = await adapter.get_login_challenge()
            identity = await adapter.exchange_code("c", ch.state)
        # ROLE_TEACHER → teacher; ROLE_ADMIN bewusst NICHT gemappt → kein admin
        assert identity.roles == ["teacher"]
        assert identity.sso_groups == ["kollegium", "fs.mathematik", "klasse.8d"]
        assert identity.sso_roles == ["ROLE_TEACHER", "ROLE_ADMIN"]


class TestAsStrList:
    def test_list_of_strings_passthrough(self):
        assert _as_str_list(["a", "b"]) == ["a", "b"]

    def test_single_string_wrapped(self):
        assert _as_str_list("a") == ["a"]

    def test_objects_name_field_extracted(self):
        assert _as_str_list([{"name": "Kollegium"}, {"act": "fs.x"}]) == ["Kollegium", "fs.x"]

    def test_dict_of_objects_prefers_act(self):
        """IServ-Gruppenformat: Map id→Objekt, `act` wird bevorzugt."""
        value = {
            "id1": {"id": "id1", "act": "fs.mathematik", "name": "FS Mathematik"},
            "id2": {"id": "id2", "act": "kollegium", "name": "Kollegium"},
        }
        assert _as_str_list(value) == ["fs.mathematik", "kollegium"]

    def test_single_object_dict(self):
        assert _as_str_list({"act": "kollegium", "name": "Kollegium"}) == ["kollegium"]

    def test_none_and_garbage_yield_empty(self):
        assert _as_str_list(None) == []
        assert _as_str_list(123) == []
        assert _as_str_list([1, 2, {"foo": "bar"}]) == []


# =============================================================================
# Step-up-Re-Authentifizierung (Phase 12, Schritt 5)
# =============================================================================

import base64 as _b64
import json as _json


def _fake_id_token(auth_time):
    header = _b64.urlsafe_b64encode(b'{"alg":"none"}').decode().rstrip("=")
    payload = _b64.urlsafe_b64encode(
        _json.dumps({"auth_time": auth_time}).encode()
    ).decode().rstrip("=")
    return f"{header}.{payload}.sig"


def _mock_token_with_id(auth_time, access_token="t"):
    resp = MagicMock()
    body = {"access_token": access_token}
    if auth_time is not None:
        body["id_token"] = _fake_id_token(auth_time)
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    return resp


class TestOAuthStepup:
    @pytest.mark.asyncio
    async def test_get_stepup_challenge_forces_login(self, oauth_adapter):
        ch = await oauth_adapter.get_stepup_challenge("su.abc.def.nonce.sig")
        assert ch.type == "redirect"
        assert "prompt=login" in ch.redirect_url
        assert "max_age=0" in ch.redirect_url
        assert "state=su." in ch.redirect_url
        assert "client_id=test_client_id" in ch.redirect_url

    @pytest.mark.asyncio
    async def test_exchange_code_fresh_extracts_auth_time(self, oauth_adapter):
        mock_client = _make_mock_client(
            _mock_token_with_id(1_700_000_000),
            _mock_userinfo("testuser", ["schueler"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            fresh = await oauth_adapter.exchange_code_fresh("code", "su.state")
        assert fresh.identity.external_id == "testuser"
        assert fresh.auth_time == 1_700_000_000

    @pytest.mark.asyncio
    async def test_exchange_code_fresh_without_id_token(self, oauth_adapter):
        mock_client = _make_mock_client(
            _mock_token_with_id(None),
            _mock_userinfo("testuser", ["schueler"]),
        )
        with patch(
            "app.auth.adapters.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            fresh = await oauth_adapter.exchange_code_fresh("code", "su.state")
        assert fresh.auth_time is None
        assert fresh.identity.external_id == "testuser"
