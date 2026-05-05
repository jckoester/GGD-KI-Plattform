import hashlib
import hmac

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.auth.adapters.iserv import IServAdapter, IServConfig
from app.config import Settings


@pytest.fixture
def mock_settings():
    settings = MagicMock(spec=Settings)
    settings.auth_iserv_client_secret = "test_client_secret"
    settings.school_secret = "test_school_secret"
    return settings


@pytest.fixture
def iserv_config_dict():
    return {
        "base_url": "https://iserv.example.de",
        "client_id": "test_client_id",
        "redirect_uri": "https://ki.example.de/auth/callback",
        "grade_group_pattern": r"^jahrgang\.(\d{1,2})$",
    }


@pytest.fixture
def iserv_adapter(mock_settings, iserv_config_dict):
    return IServAdapter(
        raw=iserv_config_dict,
        settings=mock_settings,
        group_role_map={"ki-admins": "admin", "lehrer": "teacher", "schueler": "student"},
    )


@pytest.fixture
def iserv_adapter_no_pattern(mock_settings, iserv_config_dict):
    config = {**iserv_config_dict, "grade_group_pattern": None}
    return IServAdapter(raw=config, settings=mock_settings, group_role_map={})


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


def _mock_userinfo(username, groups):
    resp = MagicMock()
    resp.json.return_value = {"preferred_username": username, "groups": groups}
    resp.raise_for_status = MagicMock()
    return resp


class TestIServConfig:
    def test_valid_config(self, iserv_config_dict):
        config = IServConfig.model_validate(iserv_config_dict)
        assert config.base_url == "https://iserv.example.de"
        assert config.client_id == "test_client_id"

    def test_invalid_pattern_no_capture_group(self):
        with pytest.raises(ValueError, match="grade_group_pattern muss genau eine Capture-Group enthalten"):
            IServConfig(
                base_url="https://iserv.example.de",
                client_id="client_id",
                redirect_uri="https://ki.example.de/auth/callback",
                grade_group_pattern=r"^jahrgang\.\d{1,2}$",
            )

    def test_invalid_pattern_syntax(self):
        with pytest.raises(ValueError, match="grade_group_pattern ist kein gültiges Regex"):
            IServConfig(
                base_url="https://iserv.example.de",
                client_id="client_id",
                redirect_uri="https://ki.example.de/auth/callback",
                grade_group_pattern="[invalid",
            )

    def test_none_pattern_is_valid(self):
        config = IServConfig(
            base_url="https://iserv.example.de",
            client_id="client_id",
            redirect_uri="https://ki.example.de/auth/callback",
            grade_group_pattern=None,
        )
        assert config.grade_group_pattern is None


class TestIServAdapter:
    def test_mode_is_redirect(self, iserv_adapter):
        assert iserv_adapter.mode == "redirect"

    @pytest.mark.asyncio
    async def test_get_login_challenge_returns_redirect(self, iserv_adapter):
        challenge = await iserv_adapter.get_login_challenge()
        assert challenge.type == "redirect"
        assert challenge.redirect_url is not None
        assert "client_id=test_client_id" in challenge.redirect_url
        assert "redirect_uri=" in challenge.redirect_url
        assert "state=" in challenge.redirect_url
        assert challenge.state is not None

    @pytest.mark.asyncio
    async def test_state_contains_valid_hmac(self, iserv_adapter):
        challenge = await iserv_adapter.get_login_challenge()
        state = challenge.state
        assert state is not None
        nonce, received_sig = state.rsplit(".", 1)
        expected_sig = hmac.new(
            iserv_adapter._school_secret.encode(),
            nonce.encode(),
            hashlib.sha256,
        ).hexdigest()
        assert hmac.compare_digest(expected_sig, received_sig)

    @pytest.mark.asyncio
    async def test_exchange_code_success(self, iserv_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("testuser", ["schueler", "jahrgang.10"]),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert identity.external_id == "testuser"
        assert identity.roles == ["student"]
        assert identity.grade == "10"

    @pytest.mark.asyncio
    async def test_exchange_code_maps_group_to_role(self, iserv_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("teacher_user", ["lehrer"]),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert identity.roles == ["teacher"]
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_exchange_code_extracts_grade(self, iserv_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("student_user", ["schueler", "jahrgang.10"]),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert identity.roles == ["student"]
        assert identity.grade == "10"

    @pytest.mark.asyncio
    async def test_extract_grade_no_pattern(self, iserv_adapter_no_pattern):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("user1", ["jahrgang.10", "other"]),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter_no_pattern.get_login_challenge()
            identity = await iserv_adapter_no_pattern.exchange_code("test_code", challenge.state)
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_extract_grade_no_match(self, iserv_adapter):
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("user1", ["klasse.10a", "other"]),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert identity.grade is None

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state(self, iserv_adapter):
        with pytest.raises(ValueError, match="State-Signatur ungültig"):
            await iserv_adapter.exchange_code("code", "invalid.state")

    @pytest.mark.asyncio
    async def test_exchange_code_invalid_state_format(self, iserv_adapter):
        with pytest.raises(ValueError, match="Ungültiges State-Format"):
            await iserv_adapter.exchange_code("code", "nostatehere")

    @pytest.mark.asyncio
    async def test_exchange_code_token_error(self, iserv_adapter):
        token_resp = MagicMock()
        token_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=MagicMock()
        )
        mock_client = _make_mock_client(token_resp, MagicMock())
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            with pytest.raises(httpx.HTTPStatusError):
                await iserv_adapter.exchange_code("test_code", challenge.state)

    @pytest.mark.asyncio
    async def test_authenticate_direct_raises(self, iserv_adapter):
        with pytest.raises(NotImplementedError, match="IServAdapter unterstützt kein direktes Login"):
            await iserv_adapter.authenticate_direct("user", "pass")

    @pytest.mark.asyncio
    async def test_sso_groups_passed_to_identity(self, iserv_adapter):
        """IServAdapter übergibt SSO-Gruppen unverändert an NormalizedIdentity."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("testuser", ["FS.Mathematik", "Klasse.8a", "lehrer"]),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert "FS.Mathematik" in identity.sso_groups
        assert "Klasse.8a" in identity.sso_groups
        assert "lehrer" in identity.sso_groups
        assert len(identity.sso_groups) == 3

    @pytest.mark.asyncio
    async def test_sso_groups_empty_when_no_groups(self, iserv_adapter):
        """Ohne groups-Claim ist sso_groups leer."""
        mock_client = _make_mock_client(
            _mock_token(),
            _mock_userinfo("testuser", []),
        )
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert identity.sso_groups == []

    @pytest.mark.asyncio
    async def test_sso_groups_empty_when_no_groups_key(self, iserv_adapter):
        """Fehlender groups-Claim ergibt leere sso_groups."""
        resp = MagicMock()
        resp.json.return_value = {"preferred_username": "testuser"}
        resp.raise_for_status = MagicMock()
        mock_client = _make_mock_client(_mock_token(), resp)
        with patch("app.auth.adapters.iserv.httpx.AsyncClient", return_value=mock_client):
            challenge = await iserv_adapter.get_login_challenge()
            identity = await iserv_adapter.exchange_code("test_code", challenge.state)
        assert identity.sso_groups == []
