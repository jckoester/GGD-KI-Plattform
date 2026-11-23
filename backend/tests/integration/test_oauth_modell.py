"""Datenmodell für OAuth (0.55, Päckchen AX Schritt 1, Migration 0112). Erfordert TEST_DATABASE_URL."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.db.models import OAuthClient, OAuthCode, OAuthToken, PersonalAccessToken

pytestmark = pytest.mark.asyncio

BALD = datetime.now(timezone.utc) + timedelta(days=1)


async def _welt(db):
    client = OAuthClient(client_id=f"c-{uuid.uuid4().hex}", client_secret="geheim",
                         metadaten={"client_name": "Claude", "redirect_uris": ["https://claude.ai/api/mcp/auth_callback"]})
    db.add(client)
    await db.flush()
    verbindung = PersonalAccessToken(pseudonym="p-oauth", name="Claude", token_hash=None, scopes=["curriculum:read"],
                                     expires_at=BALD, oauth_client_id=client.client_id)
    code = OAuthCode(code_hash=uuid.uuid4().hex, client_id=client.client_id, pseudonym="p-oauth",
                     scopes=["curriculum:read"], code_challenge="x", redirect_uri="https://claude.ai/cb",
                     redirect_uri_explizit=True, expires_at=BALD)
    db.add_all([verbindung, code])
    await db.flush()
    tokens = [OAuthToken(token_hash=uuid.uuid4().hex, art=art, verbindung_id=verbindung.id, expires_at=BALD)
              for art in ("zugriff", "refresh")]
    db.add_all(tokens)
    await db.flush()
    return client, verbindung, code


async def _anzahl(db, modell, bedingung):
    return await db.scalar(sa.select(sa.func.count()).select_from(modell).where(bedingung))


async def test_verbindung_ohne_eigenen_hash(db_session):
    _, verbindung, _ = await _welt(db_session)
    assert verbindung.token_hash is None
    assert await _anzahl(db_session, OAuthToken, OAuthToken.verbindung_id == verbindung.id) == 2


async def test_widerruf_der_verbindung_loescht_ihre_token(db_session):
    _, verbindung, _ = await _welt(db_session)
    await db_session.execute(sa.delete(PersonalAccessToken).where(PersonalAccessToken.id == verbindung.id))
    assert await _anzahl(db_session, OAuthToken, OAuthToken.verbindung_id == verbindung.id) == 0


async def test_client_loeschen_raeumt_alles_ab(db_session):
    client, verbindung, code = await _welt(db_session)
    await db_session.execute(sa.delete(OAuthClient).where(OAuthClient.client_id == client.client_id))
    assert await _anzahl(db_session, PersonalAccessToken, PersonalAccessToken.id == verbindung.id) == 0
    assert await _anzahl(db_session, OAuthCode, OAuthCode.code_hash == code.code_hash) == 0
    assert await _anzahl(db_session, OAuthToken, OAuthToken.verbindung_id == verbindung.id) == 0


async def test_zeile_ohne_hash_und_ohne_client_abgewiesen(db_session):
    db_session.add(PersonalAccessToken(pseudonym="p-oauth", name="leer", token_hash=None, scopes=[], expires_at=BALD))
    with pytest.raises(IntegrityError, match="ck_personal_access_tokens_hash_oder_client"):
        await db_session.flush()


async def test_unbekannte_token_art_abgewiesen(db_session):
    _, verbindung, _ = await _welt(db_session)
    db_session.add(OAuthToken(token_hash=uuid.uuid4().hex, art="ewig", verbindung_id=verbindung.id, expires_at=BALD))
    with pytest.raises(IntegrityError, match="ck_oauth_tokens_art"):
        await db_session.flush()
