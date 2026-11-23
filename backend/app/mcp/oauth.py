"""OAuth-Autorisierungsserver für KI-Abos (0.55, Päckchen AX Schritt 2).

Die Endpunkte (`/authorize`, `/token`, `/register`, `/revoke`, Metadaten) liefert das SDK `mcp`;
hier steht der **Speicher** dahinter (`OAuthAuthorizationServerProvider`), über die Tabellen aus
Migration 0112.

**Ablauf.**
1. `register_client` — Dynamic Client Registration, offen für alle (F12), aber Redirect-URIs nur
   `https://` oder Loopback.
2. `authorize` — schreibt die Anfrage in ein **signiertes, kurzlebiges JWT** (keine Tabelle) und
   schickt den Browser auf die Zustimmungsseite im Frontend (`<FRONTEND_ORIGIN>/oauth/consent?anfrage=…`).
3. `code_ausstellen` — nach Anmeldung und Zustimmung der Lehrkraft (Schritt 4): ein einmaliger
   Code, 5 Minuten gültig, zurück an den Client.
4. `exchange_authorization_code` — PKCE prüft das SDK; hier entsteht die **Verbindung** (eine
   Zeile in `personal_access_tokens` mit `oauth_client_id`, F7) mit Zugriffs- und Refresh-Token.
5. `exchange_refresh_token` — Rotation: Der alte Refresh-Token gilt als eingelöst
   (`rotiert_at`). Kommt er noch einmal, ist er gestohlen — die Verbindung endet.

**Laufzeiten (F8).** Zugriff 1 Stunde; Refresh und Verbindung 90 Tage ab der Zustimmung, dann
neu verbinden. Die Verbindung prüft bei jedem Zugriff dasselbe wie ein Zugangstoken
(`tokens.pruefe_zeile`): Widerruf, Ablauf, Rollen frisch, Massenwiderruf.

**Beide Token-Arten.** Mit Provider baut das SDK den Prüfer selbst aus `load_access_token`. Der
nimmt deshalb auch persönliche Zugangstoken (`ggd_pat_…`, AW) an.
"""
from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

import sqlalchemy as sa
from jose import JWTError, jwt
from mcp.server.auth.provider import (
    AccessToken,
    AuthorizationCode,
    AuthorizationParams,
    AuthorizeError,
    RefreshToken,
    RegistrationError,
    TokenError,
    construct_redirect_uri,
)
from mcp.shared.auth import OAuthClientInformationFull, OAuthToken
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import tokens
from app.db.models import OAuthClient, OAuthCode, OAuthToken as OAuthTokenZeile, PersonalAccessToken
from app.mcp.auth import SCOPE, ZugangstokenPruefer

ZUGRIFF = timedelta(hours=1)
VERBINDUNG = timedelta(days=90)
CODE = timedelta(minutes=5)
ANFRAGE = timedelta(minutes=10)

PRAEFIX_ZUGRIFF = "ggd_oat_"
PRAEFIX_REFRESH = "ggd_ort_"
_ANFRAGE_TYP = "oauth_anfrage"
_LOOPBACK = {"localhost", "127.0.0.1", "::1", "[::1]"}


def _hash(klartext: str) -> str:
    return hashlib.sha256(klartext.encode()).hexdigest()


def redirect_erlaubt(uri: str) -> bool:
    """`https://` überall, `http://` nur auf Loopback (Claude Code mit beliebigem Port)."""
    teile = urlsplit(uri)
    if teile.scheme == "https" and teile.hostname:
        return True
    return teile.scheme == "http" and (teile.hostname or "") in _LOOPBACK


class OAuthFehler(Exception):
    """Abgelehnte Zustimmung oder ungültige Anfrage — die Meldung ist für die Lehrkraft."""


class Provider:
    """`OAuthAuthorizationServerProvider` über die Tabellen aus 0112."""

    def __init__(self, *, oeffentliche_url: str, geheimnis: str, zustimmungsseite: str,
                 sitzung: Callable[[], AsyncSession] | None = None):
        if sitzung is None:
            from app.db.session import AsyncSessionLocal

            sitzung = AsyncSessionLocal
        self._sitzung = sitzung
        self._geheimnis = geheimnis
        self._resource = oeffentliche_url
        # Die Zustimmungsseite im Frontend (`FRONTEND_ORIGIN` + `/oauth/consent`). Auf Prod dieselbe
        # Domain wie die Schnittstelle, auf Dev ein anderer Port als das Backend.
        self._zustimmungsseite = zustimmungsseite
        self._pat = ZugangstokenPruefer(sitzung)

    # ── Clients ───────────────────────────────────────────────────────────────

    async def get_client(self, client_id: str) -> OAuthClientInformationFull | None:
        async with self._sitzung() as db:
            zeile = await db.get(OAuthClient, client_id)
        if zeile is None:
            return None
        return OAuthClientInformationFull.model_validate(
            {**zeile.metadaten, "client_id": zeile.client_id, "client_secret": zeile.client_secret})

    async def register_client(self, client_info: OAuthClientInformationFull) -> None:
        uris = [str(u) for u in (client_info.redirect_uris or [])]
        if not uris or not all(redirect_erlaubt(u) for u in uris):
            raise RegistrationError("invalid_redirect_uri",
                                    "Redirect-URIs nur mit https:// oder auf Loopback (http://localhost).")
        metadaten = client_info.model_dump(mode="json", exclude={"client_id", "client_secret"}, exclude_none=True)
        async with self._sitzung() as db:
            db.add(OAuthClient(client_id=client_info.client_id, client_secret=client_info.client_secret,
                               metadaten=metadaten))
            await db.commit()

    # ── Anfrage und Zustimmung ────────────────────────────────────────────────

    async def authorize(self, client: OAuthClientInformationFull, params: AuthorizationParams) -> str:
        """Die Anfrage reist signiert zur Zustimmungsseite — gebunden an den Client, 10 Minuten."""
        if params.scopes and set(params.scopes) - {SCOPE}:
            raise AuthorizeError("invalid_scope", f"Nur {SCOPE} ist möglich.")
        jetzt = datetime.now(timezone.utc)
        anfrage = jwt.encode({
            "typ": _ANFRAGE_TYP, "client_id": client.client_id, "redirect_uri": str(params.redirect_uri),
            "explizit": params.redirect_uri_provided_explicitly, "challenge": params.code_challenge,
            "state": params.state, "resource": params.resource,
            "iat": int(jetzt.timestamp()), "exp": int((jetzt + ANFRAGE).timestamp()),
        }, self._geheimnis, algorithm="HS256")
        return construct_redirect_uri(self._zustimmungsseite, anfrage=anfrage)

    def anfrage_lesen(self, anfrage: str) -> dict:
        """Die signierte Anfrage — oder `OAuthFehler`, wenn sie abgelaufen oder gefälscht ist."""
        try:
            daten = jwt.decode(anfrage, self._geheimnis, algorithms=["HS256"])
        except JWTError:
            raise OAuthFehler("Die Anfrage ist abgelaufen oder ungültig. Bitte im Programm neu verbinden.") from None
        if daten.get("typ") != _ANFRAGE_TYP:
            raise OAuthFehler("Die Anfrage ist ungültig.")
        return daten

    async def anfrage_anzeigen(self, anfrage: str) -> dict:
        """Was die Zustimmungsseite zeigt: Programm, Rücksprung-Host, Berechtigung, Dauer."""
        daten = self.anfrage_lesen(anfrage)
        client = await self.get_client(daten["client_id"])
        if client is None:
            raise OAuthFehler("Dieses Programm ist nicht mehr registriert. Bitte im Programm neu verbinden.")
        return {"programm": client.client_name or "Unbenanntes Programm",
                "ruecksprung": urlsplit(daten["redirect_uri"]).netloc, "scope": SCOPE,
                "berechtigung": tokens.SCOPE_BESCHRIFTUNG[SCOPE], "tage": VERBINDUNG.days}

    async def code_ausstellen(self, anfrage: str, user) -> str:
        """Nach der Zustimmung: Code speichern, Rücksprung-URL mit Code und State zurückgeben.

        Nur Lehrkräfte und Admins, nicht in der Vorschau (F9) — die Rollen prüft der Aufrufer
        über die Sitzung; hier zur Sicherheit noch einmal.
        """
        daten = self.anfrage_lesen(anfrage)
        if user.preview is not None or not tokens.ERLAUBTE_ROLLEN & set(user.roles or []):
            raise OAuthFehler("KI-Programme verbinden können nur Lehrkräfte und Admins.")
        code = secrets.token_urlsafe(32)
        async with self._sitzung() as db:
            if await db.get(OAuthClient, daten["client_id"]) is None:
                raise OAuthFehler("Dieses Programm ist nicht mehr registriert.")
            db.add(OAuthCode(
                code_hash=_hash(code), client_id=daten["client_id"], pseudonym=user.sub, scopes=[SCOPE],
                code_challenge=daten["challenge"], redirect_uri=daten["redirect_uri"],
                redirect_uri_explizit=bool(daten["explizit"]), resource=daten.get("resource"),
                expires_at=datetime.now(timezone.utc) + CODE))
            await db.commit()
        return construct_redirect_uri(daten["redirect_uri"], code=code, state=daten.get("state"))

    def ablehnen(self, anfrage: str) -> str:
        """Die Lehrkraft lehnt ab: zurück an den Client mit `access_denied`."""
        daten = self.anfrage_lesen(anfrage)
        return construct_redirect_uri(daten["redirect_uri"], error="access_denied", state=daten.get("state"))

    # ── Code einlösen ─────────────────────────────────────────────────────────

    async def load_authorization_code(self, client: OAuthClientInformationFull,
                                      authorization_code: str) -> AuthorizationCode | None:
        async with self._sitzung() as db:
            zeile = await db.get(OAuthCode, _hash(authorization_code))
        if zeile is None or zeile.client_id != client.client_id:
            return None
        return AuthorizationCode(
            code=authorization_code, scopes=list(zeile.scopes), expires_at=zeile.expires_at.timestamp(),
            client_id=zeile.client_id, code_challenge=zeile.code_challenge, redirect_uri=zeile.redirect_uri,
            redirect_uri_provided_explicitly=zeile.redirect_uri_explizit, resource=zeile.resource,
            subject=zeile.pseudonym)

    async def exchange_authorization_code(self, client: OAuthClientInformationFull,
                                          authorization_code: AuthorizationCode) -> OAuthToken:
        async with self._sitzung() as db:
            # Einmalig: Wer zuerst löscht, bekommt die Token — ein zweites Einlösen findet nichts.
            geloescht = await db.execute(sa.delete(OAuthCode).where(
                OAuthCode.code_hash == _hash(authorization_code.code)).returning(OAuthCode.pseudonym))
            pseudonym = geloescht.scalar_one_or_none()
            if pseudonym is None:
                raise TokenError("invalid_grant", "Code bereits eingelöst")
            jetzt = datetime.now(timezone.utc)
            # Eine Verbindung je Person und Programm: Ein neues Verbinden ersetzt die alte.
            await db.execute(sa.update(PersonalAccessToken).where(
                PersonalAccessToken.pseudonym == pseudonym, PersonalAccessToken.oauth_client_id == client.client_id,
                PersonalAccessToken.revoked_at.is_(None)).values(revoked_at=jetzt))
            verbindung = PersonalAccessToken(
                pseudonym=pseudonym, name=client.client_name or "KI-Programm", token_hash=None,
                scopes=list(authorization_code.scopes), expires_at=jetzt + VERBINDUNG,
                oauth_client_id=client.client_id)
            db.add(verbindung)
            await db.execute(sa.update(OAuthClient).where(OAuthClient.client_id == client.client_id)
                             .values(last_used_at=jetzt))
            await db.flush()
            antwort = self._token_paar(db, verbindung, list(authorization_code.scopes))
            await db.commit()
        return antwort

    def _token_paar(self, db: AsyncSession, verbindung: PersonalAccessToken, scopes: list[str]) -> OAuthToken:
        jetzt = datetime.now(timezone.utc)
        zugriff, refresh = PRAEFIX_ZUGRIFF + secrets.token_urlsafe(32), PRAEFIX_REFRESH + secrets.token_urlsafe(32)
        db.add_all([
            OAuthTokenZeile(token_hash=_hash(zugriff), art="zugriff", verbindung_id=verbindung.id,
                            expires_at=min(jetzt + ZUGRIFF, verbindung.expires_at)),
            OAuthTokenZeile(token_hash=_hash(refresh), art="refresh", verbindung_id=verbindung.id,
                            expires_at=verbindung.expires_at),
        ])
        return OAuthToken(access_token=zugriff, token_type="Bearer", refresh_token=refresh,
                          expires_in=int(min(ZUGRIFF, verbindung.expires_at - jetzt).total_seconds()),
                          scope=" ".join(scopes))

    # ── Refresh ───────────────────────────────────────────────────────────────

    async def _token_mit_verbindung(self, db: AsyncSession, klartext: str, art: str):
        zeile = (await db.execute(sa.select(OAuthTokenZeile, PersonalAccessToken)
                                  .join(PersonalAccessToken, PersonalAccessToken.id == OAuthTokenZeile.verbindung_id)
                                  .where(OAuthTokenZeile.token_hash == _hash(klartext),
                                         OAuthTokenZeile.art == art))).first()
        return (zeile[0], zeile[1]) if zeile else (None, None)

    async def load_refresh_token(self, client: OAuthClientInformationFull, refresh_token: str) -> RefreshToken | None:
        if not refresh_token.startswith(PRAEFIX_REFRESH):
            return None
        async with self._sitzung() as db:
            token, verbindung = await self._token_mit_verbindung(db, refresh_token, "refresh")
            if token is None or verbindung.oauth_client_id != client.client_id:
                return None
            if token.rotiert_at is not None:
                # Ein schon eingelöster Refresh-Token kommt noch einmal: gestohlen. Verbindung beenden.
                await db.execute(sa.update(PersonalAccessToken).where(PersonalAccessToken.id == verbindung.id)
                                 .values(revoked_at=datetime.now(timezone.utc)))
                await db.commit()
                return None
            if await tokens.pruefe_zeile(db, verbindung) is None:
                return None
            return RefreshToken(token=refresh_token, client_id=client.client_id, scopes=list(verbindung.scopes),
                                expires_at=int(token.expires_at.timestamp()), resource=self._resource,
                                subject=verbindung.pseudonym)

    async def exchange_refresh_token(self, client: OAuthClientInformationFull, refresh_token: RefreshToken,
                                     scopes: list[str]) -> OAuthToken:
        async with self._sitzung() as db:
            token, verbindung = await self._token_mit_verbindung(db, refresh_token.token, "refresh")
            if token is None or token.rotiert_at is not None:
                raise TokenError("invalid_grant", "Refresh-Token ungültig")
            rotiert = await db.execute(sa.update(OAuthTokenZeile).where(
                OAuthTokenZeile.id == token.id, OAuthTokenZeile.rotiert_at.is_(None))
                .values(rotiert_at=datetime.now(timezone.utc)))
            if rotiert.rowcount != 1:  # gleichzeitig zweimal eingelöst
                raise TokenError("invalid_grant", "Refresh-Token ungültig")
            antwort = self._token_paar(db, verbindung, scopes or list(verbindung.scopes))
            await db.commit()
        return antwort

    # ── Zugriff ───────────────────────────────────────────────────────────────

    async def load_access_token(self, token: str) -> AccessToken | None:
        if token.startswith(tokens.PRAEFIX):
            zugang = await self._pat.verify_token(token)
            return zugang.model_copy(update={"resource": self._resource}) if zugang else None
        if not token.startswith(PRAEFIX_ZUGRIFF):
            return None
        async with self._sitzung() as db:
            zeile, verbindung = await self._token_mit_verbindung(db, token, "zugriff")
            if zeile is None or zeile.expires_at <= datetime.now(timezone.utc):
                return None
            principal = await tokens.pruefe_zeile(db, verbindung)
        if principal is None or SCOPE not in (verbindung.scopes or []):
            return None
        return AccessToken(
            token=token, client_id=verbindung.oauth_client_id, scopes=list(verbindung.scopes),
            expires_at=int(zeile.expires_at.timestamp()), resource=self._resource, subject=principal.sub,
            claims={"roles": principal.roles, "grade": principal.grade, "iat": principal.iat})

    # ── Widerruf ──────────────────────────────────────────────────────────────

    async def revoke_token(self, token: AccessToken | RefreshToken) -> None:
        """RFC 7009 über das SDK: Widerruf eines Tokens beendet die ganze Verbindung — wie der
        Widerruf im Profil. Zugangstoken (AW) widerruft nur das Profil."""
        if not token.token.startswith((PRAEFIX_ZUGRIFF, PRAEFIX_REFRESH)):
            return
        async with self._sitzung() as db:
            zeile = await db.scalar(sa.select(OAuthTokenZeile).where(OAuthTokenZeile.token_hash == _hash(token.token)))
            if zeile is not None:
                await db.execute(sa.update(PersonalAccessToken).where(PersonalAccessToken.id == zeile.verbindung_id)
                                 .values(revoked_at=datetime.now(timezone.utc)))
                await db.commit()


async def oauth_aufraeumen(db: AsyncSession, *, jetzt: datetime | None = None, dry_run: bool = False) -> dict:
    """Täglicher Lauf (`scripts/cleanup_oauth.py`):

    - Clients, die 30 Tage nach der Registrierung nie benutzt wurden (F12) — jede:r kann
      registrieren, ohne Aufräumen wüchse die Tabelle mit jedem Versuch;
    - abgelaufene Codes und Token;
    - eingelöste Refresh-Token nach 7 Tagen. Bis dahin erkennen sie Diebstahl; danach
      stünden sonst bei stündlichem Refresh über 2000 Zeilen je Verbindung.
    """
    jetzt = jetzt or datetime.now(timezone.utc)
    clients = sa.and_(OAuthClient.last_used_at.is_(None), OAuthClient.created_at < jetzt - timedelta(days=30))
    codes = OAuthCode.expires_at < jetzt
    token = sa.or_(OAuthTokenZeile.expires_at < jetzt, OAuthTokenZeile.rotiert_at < jetzt - timedelta(days=7))
    if dry_run:
        zaehlen = lambda m, b: db.scalar(sa.select(sa.func.count()).select_from(m).where(b))  # noqa: E731
        return {"clients": await zaehlen(OAuthClient, clients), "codes": await zaehlen(OAuthCode, codes),
                "token": await zaehlen(OAuthTokenZeile, token)}
    # Ausgeschrieben statt in einer Schleife: Der Wächter `test_mcp_nur_lesend` sieht so, welche
    # Tabellen hier geschrieben werden.
    aus = {"clients": (await db.execute(sa.delete(OAuthClient).where(clients))).rowcount,
           "codes": (await db.execute(sa.delete(OAuthCode).where(codes))).rowcount,
           "token": (await db.execute(sa.delete(OAuthTokenZeile).where(token))).rowcount}
    await db.commit()
    return aus
