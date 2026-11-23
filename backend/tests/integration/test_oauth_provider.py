"""OAuth-Provider für KI-Abos (0.55, Päckchen AX Schritt 2) — der ganze Ablauf gegen die echte
Datenbank, ohne HTTP (die Endpunkte des SDK kommen in Schritt 3). Erfordert TEST_DATABASE_URL."""
import base64
import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlsplit

import pytest
import pytest_asyncio
import sqlalchemy as sa
from jose import jwt
from mcp.server.auth.provider import AuthorizationParams, AuthorizeError, RegistrationError, TokenError
from mcp.shared.auth import OAuthClientInformationFull
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.auth import tokens
from app.auth.jwt import JwtPayload
from app.auth.vorschau import Vorschau
from app.db.models import OAuthClient, OAuthToken, PersonalAccessToken, PseudonymAudit
from app.mcp.auth import SCOPE
from app.mcp.oauth import (PRAEFIX_REFRESH, PRAEFIX_ZUGRIFF, OAuthFehler, Provider,
                           oauth_aufraeumen, redirect_erlaubt)

pytestmark = pytest.mark.asyncio

GEHEIM = "test-geheimnis"
URL = "https://ki.schule.test/api/mcp"
RUECK = "https://claude.ai/api/mcp/auth_callback"


@pytest_asyncio.fixture
async def fabrik(async_engine):
    return async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def welt(fabrik):
    """Eine Lehrkraft und ein registrierter Client; räumt beides wieder ab."""
    pseudo, cid = f"oa-{uuid.uuid4().hex[:10]}", f"c-{uuid.uuid4().hex}"
    async with fabrik() as db:
        db.add(PseudonymAudit(pseudonym=pseudo, role="teacher", roles=["teacher"], grade=None))
        await db.commit()
    provider = Provider(oeffentliche_url=URL, geheimnis=GEHEIM, sitzung=fabrik,
                        zustimmungsseite="https://ki.schule.test/oauth/consent")
    await provider.register_client(OAuthClientInformationFull(
        client_id=cid, client_secret="s3cret", client_name="Claude", redirect_uris=[RUECK],
        token_endpoint_auth_method="client_secret_post"))
    yield {"pseudo": pseudo, "cid": cid, "provider": provider}
    async with fabrik() as db:
        await db.execute(sa.delete(OAuthClient).where(OAuthClient.client_id.like("c-%")))
        await db.execute(sa.delete(PersonalAccessToken).where(PersonalAccessToken.pseudonym == pseudo))
        await db.execute(sa.delete(PseudonymAudit).where(PseudonymAudit.pseudonym == pseudo))
        await db.commit()


def _user(pseudo, *rollen, preview=None):
    return JwtPayload(sub=pseudo, roles=list(rollen), grade=None, jti="j", iat=0, exp=9999999999, preview=preview)


def _pkce():
    verifier = uuid.uuid4().hex + uuid.uuid4().hex
    return verifier, base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")


async def _bis_zum_code(w, state="xyz"):
    p = w["provider"]
    client = await p.get_client(w["cid"])
    _, challenge = _pkce()
    ziel = await p.authorize(client, AuthorizationParams(
        state=state, scopes=[SCOPE], code_challenge=challenge, redirect_uri=RUECK,
        redirect_uri_provided_explicitly=True, resource=URL))
    anfrage = parse_qs(urlsplit(ziel).query)["anfrage"][0]
    rueck = await p.code_ausstellen(anfrage, _user(w["pseudo"], "teacher"))
    return client, parse_qs(urlsplit(rueck).query), ziel


async def _verbinden(w):
    p = w["provider"]
    client, q, _ = await _bis_zum_code(w)
    code = await p.load_authorization_code(client, q["code"][0])
    return client, await p.exchange_authorization_code(client, code)


def test_redirect_regel():
    assert redirect_erlaubt("https://claude.ai/api/mcp/auth_callback")
    assert redirect_erlaubt("http://localhost:43123/callback")
    assert redirect_erlaubt("http://127.0.0.1:9/cb")
    assert not redirect_erlaubt("http://claude.ai/cb")
    assert not redirect_erlaubt("javascript:alert(1)")


async def test_registrieren_nur_sichere_redirects(welt):
    p = welt["provider"]
    client = await p.get_client(welt["cid"])
    assert (client.client_name, client.client_secret, [str(u) for u in client.redirect_uris]) == (
        "Claude", "s3cret", [RUECK])
    with pytest.raises(RegistrationError):
        await p.register_client(OAuthClientInformationFull(
            client_id=f"c-{uuid.uuid4().hex}", redirect_uris=["http://boese.test/cb"]))
    assert await p.get_client("gibt-es-nicht") is None


async def test_anfrage_zustimmung_und_code(welt):
    p = welt["provider"]
    _, q, ziel = await _bis_zum_code(welt)
    assert ziel.startswith("https://ki.schule.test/oauth/consent?anfrage=")
    assert q["state"] == ["xyz"] and len(q["code"][0]) >= 40
    anfrage = parse_qs(urlsplit(ziel).query)["anfrage"][0]
    assert await p.anfrage_anzeigen(anfrage) == {
        "programm": "Claude", "ruecksprung": "claude.ai", "scope": SCOPE,
        "berechtigung": tokens.SCOPE_BESCHRIFTUNG[SCOPE], "tage": 90}
    assert parse_qs(urlsplit(p.ablehnen(anfrage)).query)["error"] == ["access_denied"]


async def test_anfrage_gefaelscht_abgelaufen_falscher_scope(welt):
    p = welt["provider"]
    client = await p.get_client(welt["cid"])
    with pytest.raises(OAuthFehler):
        p.anfrage_lesen(jwt.encode({"typ": "oauth_anfrage"}, "falsches-geheimnis", algorithm="HS256"))
    with pytest.raises(OAuthFehler):
        p.anfrage_lesen(jwt.encode({"typ": "oauth_anfrage", "exp": 1}, GEHEIM, algorithm="HS256"))
    with pytest.raises(OAuthFehler):  # ein Sitzungs-JWT ist keine Anfrage
        p.anfrage_lesen(jwt.encode({"typ": "session", "exp": 9999999999}, GEHEIM, algorithm="HS256"))
    with pytest.raises(AuthorizeError):
        await p.authorize(client, AuthorizationParams(
            state=None, scopes=["context:write"], code_challenge="x", redirect_uri=RUECK,
            redirect_uri_provided_explicitly=True))


async def test_nur_lehrkraefte_nicht_in_der_vorschau(welt):
    p = welt["provider"]
    client = await p.get_client(welt["cid"])
    ziel = await p.authorize(client, AuthorizationParams(
        state=None, scopes=None, code_challenge="x", redirect_uri=RUECK, redirect_uri_provided_explicitly=True))
    anfrage = parse_qs(urlsplit(ziel).query)["anfrage"][0]
    vorschau = Vorschau(echte_rollen=["teacher"], gruppe_id=1, beginn=0, sitzung_ablauf=2**31)
    for user in (_user(welt["pseudo"], "student"), _user(welt["pseudo"], "student", preview=vorschau)):
        with pytest.raises(OAuthFehler):
            await p.code_ausstellen(anfrage, user)


async def test_code_einloesen_einmalig_und_nur_fuer_seinen_client(welt, fabrik):
    p = welt["provider"]
    client, q, _ = await _bis_zum_code(welt)
    fremd = client.model_copy(update={"client_id": "anderer"})
    assert await p.load_authorization_code(fremd, q["code"][0]) is None
    code = await p.load_authorization_code(client, q["code"][0])
    assert code.subject == welt["pseudo"] and code.scopes == [SCOPE]
    antwort = await p.exchange_authorization_code(client, code)
    assert antwort.access_token.startswith(PRAEFIX_ZUGRIFF) and antwort.refresh_token.startswith(PRAEFIX_REFRESH)
    assert antwort.expires_in == 3600 and antwort.scope == SCOPE
    with pytest.raises(TokenError):
        await p.exchange_authorization_code(client, code)
    async with fabrik() as db:
        v = (await db.execute(sa.select(PersonalAccessToken).where(
            PersonalAccessToken.pseudonym == welt["pseudo"]))).scalar_one()
        assert (v.name, v.oauth_client_id, v.token_hash) == ("Claude", welt["cid"], None)
        assert timedelta(days=89) < v.expires_at - datetime.now(timezone.utc) <= timedelta(days=90)
        hashes = (await db.execute(sa.select(OAuthToken.token_hash).where(OAuthToken.verbindung_id == v.id))).scalars().all()
        assert antwort.access_token not in hashes and len(hashes) == 2  # nur Hashes gespeichert


async def test_zugriff_prueft_wie_ein_zugangstoken(welt, fabrik):
    p = welt["provider"]
    _, antwort = await _verbinden(welt)
    zugang = await p.load_access_token(antwort.access_token)
    assert (zugang.subject, zugang.client_id, zugang.scopes, zugang.resource) == (
        welt["pseudo"], welt["cid"], [SCOPE], URL)
    assert await p.load_access_token(antwort.refresh_token) is None  # Refresh ist kein Zugriff
    assert await p.load_access_token(PRAEFIX_ZUGRIFF + "geraten") is None

    async with fabrik() as db:  # Rolle entzogen → gesperrt
        audit = await db.get(PseudonymAudit, welt["pseudo"])
        audit.role, audit.roles = "student", ["student"]
        await db.commit()
    assert await p.load_access_token(antwort.access_token) is None


async def test_zugangstoken_aus_aw_gelten_weiter(welt, fabrik):
    async with fabrik() as db:
        klartext, _ = await tokens.erzeuge(db, pseudonym=welt["pseudo"], name="Claude Code", scopes=[SCOPE],
                                           gueltig_bis=datetime.now(timezone.utc) + timedelta(days=1),
                                           rollen=["teacher"])
    zugang = await welt["provider"].load_access_token(klartext)
    assert zugang is not None and zugang.subject == welt["pseudo"]


async def test_zugriff_abgelaufen(welt, fabrik):
    _, antwort = await _verbinden(welt)
    async with fabrik() as db:
        await db.execute(sa.update(OAuthToken).where(OAuthToken.art == "zugriff")
                         .where(OAuthToken.token_hash == hashlib.sha256(antwort.access_token.encode()).hexdigest())
                         .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=1)))
        await db.commit()
    assert await welt["provider"].load_access_token(antwort.access_token) is None


async def test_refresh_rotiert_und_erkennt_diebstahl(welt):
    p = welt["provider"]
    client, erst = await _verbinden(welt)
    rt = await p.load_refresh_token(client, erst.refresh_token)
    zweit = await p.exchange_refresh_token(client, rt, [])
    assert zweit.refresh_token != erst.refresh_token
    assert await p.load_access_token(zweit.access_token) is not None
    # Der alte Refresh-Token kommt noch einmal: gestohlen — die ganze Verbindung endet.
    assert await p.load_refresh_token(client, erst.refresh_token) is None
    assert await p.load_access_token(zweit.access_token) is None
    assert await p.load_refresh_token(client, zweit.refresh_token) is None


async def test_neu_verbinden_ersetzt_die_alte_verbindung(welt, fabrik):
    p = welt["provider"]
    _, alt = await _verbinden(welt)
    _, neu = await _verbinden(welt)
    assert await p.load_access_token(alt.access_token) is None
    assert await p.load_access_token(neu.access_token) is not None
    async with fabrik() as db:
        offen = (await db.execute(sa.select(sa.func.count()).select_from(PersonalAccessToken).where(
            PersonalAccessToken.pseudonym == welt["pseudo"], PersonalAccessToken.revoked_at.is_(None)))).scalar()
    assert offen == 1


async def test_widerruf_beendet_die_verbindung(welt, fabrik):
    p = welt["provider"]
    client, antwort = await _verbinden(welt)
    await p.revoke_token(await p.load_refresh_token(client, antwort.refresh_token))
    assert await p.load_access_token(antwort.access_token) is None
    # Widerruf im Profil wirkt genauso
    _, antwort = await _verbinden(welt)
    async with fabrik() as db:
        v = (await db.execute(sa.select(PersonalAccessToken).where(
            PersonalAccessToken.pseudonym == welt["pseudo"], PersonalAccessToken.revoked_at.is_(None)))).scalar_one()
        assert await tokens.widerrufe(db, v.id, welt["pseudo"])
    assert await p.load_access_token(antwort.access_token) is None


async def test_aufraeumen(welt, fabrik):
    """F12: nie benutzte Clients nach 30 Tagen; abgelaufene Codes und Token; eingelöste
    Refresh-Token nach 7 Tagen. Ein neuer, noch nicht benutzter Client bleibt."""
    client, antwort = await _verbinden(welt)
    rt = await welt["provider"].load_refresh_token(client, antwort.refresh_token)
    await welt["provider"].exchange_refresh_token(client, rt, [])  # alter Refresh jetzt rotiert
    alt_hash = hashlib.sha256(antwort.refresh_token.encode()).hexdigest()
    async with fabrik() as db:
        alt, benutzt = f"c-{uuid.uuid4().hex}", f"c-{uuid.uuid4().hex}"
        vorher = datetime.now(timezone.utc) - timedelta(days=31)
        db.add_all([OAuthClient(client_id=alt, metadaten={}, created_at=vorher),
                    OAuthClient(client_id=benutzt, metadaten={}, created_at=vorher, last_used_at=vorher)])
        await db.commit()
        probe = await oauth_aufraeumen(db, dry_run=True)
        assert probe["clients"] >= 1
        assert await db.get(OAuthClient, alt) is not None  # Probelauf löscht nichts
        # in 8 Tagen: der rotierte Refresh-Token ist weg, der aktuelle bleibt
        aus = await oauth_aufraeumen(db, jetzt=datetime.now(timezone.utc) + timedelta(days=8))
        assert aus["clients"] >= 1 and aus["token"] >= 1
        assert await db.get(OAuthClient, alt) is None
        assert await db.get(OAuthClient, benutzt) is not None
        assert await db.get(OAuthClient, welt["cid"]) is not None  # benutzt — bleibt
        assert await db.scalar(sa.select(OAuthToken).where(OAuthToken.token_hash == alt_hash)) is None
        offen = await db.scalar(sa.select(sa.func.count()).select_from(OAuthToken).where(
            OAuthToken.art == "refresh", OAuthToken.rotiert_at.is_(None),
            OAuthToken.verbindung_id.in_(sa.select(PersonalAccessToken.id).where(
                PersonalAccessToken.pseudonym == welt["pseudo"]))))
        assert offen == 1
