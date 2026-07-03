import base64
import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class ImageGenerationResult:
    """Ergebnis eines Bild-Calls: dekodierte Bytes + Kosten (aus dem LiteLLM-Header)."""
    image_bytes: bytes
    cost_usd: Optional[float] = None


class LiteLLMClient:
    """Schlanker Wrapper um die LiteLLM Management API."""

    def __init__(self) -> None:
        self.base_url = settings.litellm_proxy_url.rstrip("/")
        self.master_key = settings.litellm_master_key
        self.verify_ssl = settings.litellm_verify_ssl
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy initialization of the HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                verify=self.verify_ssl,
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> "LiteLLMClient":
        await self._get_client()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    async def get_user(self, pseudonym: str) -> Optional[dict]:
        """
        GET /user/info?user_id={pseudonym}.
        Gibt None bei 404 zurück.
        """
        try:
            client = await self._get_client()
            url = f"{self.base_url}/user/info"
            headers = {
                "Authorization": f"Bearer {self.master_key}",
            }
            params = {"user_id": pseudonym}

            response = await client.get(url, headers=headers, params=params)

            if response.status_code == 404:
                return None
            if response.status_code == 200:
                data = response.json()
                # /user/info wraps user data under a nested "user_info" key
                return data.get("user_info", data)

            logger.error(
                "LiteLLM get_user fehlerhaft: status=%d, body=%s",
                response.status_code,
                response.text,
            )
            return None
        except Exception as e:
            logger.error("LiteLLM get_user Exception: %s", e)
            return None

    async def get_user_info(self, pseudonym: str) -> Optional[dict]:
        """Alias für get_user mit konsistentem Namensschema."""
        return await self.get_user(pseudonym)


    async def create_user(
        self,
        pseudonym: str,
        max_budget: Optional[float],
        budget_duration: str,
    ) -> None:
        """
        POST /user/new
        """
        client = await self._get_client()
        url = f"{self.base_url}/user/new"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }

        # max_budget kann null sein (kein Limit)
        payload = {
            "user_id": pseudonym,
            "max_budget": max_budget,
            "budget_duration": budget_duration,
        }

        response = await client.post(url, headers=headers, json=payload)

        if response.status_code not in (200, 201):
            logger.error(
                "LiteLLM create_user fehlerhaft: status=%d, body=%s, payload=%s",
                response.status_code,
                response.text,
                payload,
            )
            raise RuntimeError(f"Failed to create LiteLLM user: {response.text}")

        logger.info("LiteLLM-User %s erfolgreich angelegt", pseudonym)

    async def update_user_budget(
        self,
        pseudonym: str,
        max_budget: Optional[float],
        budget_duration: str,
    ) -> None:
        """
        POST /user/update
        """
        client = await self._get_client()
        url = f"{self.base_url}/user/update"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }

        payload = {
            "user_id": pseudonym,
            "max_budget": max_budget,
            "budget_duration": budget_duration,
        }

        response = await client.post(url, headers=headers, json=payload)

        if response.status_code not in (200, 201):
            logger.error(
                "LiteLLM update_user_budget fehlerhaft: status=%d, body=%s, payload=%s",
                response.status_code,
                response.text,
                payload,
            )
            raise RuntimeError(f"Failed to update LiteLLM user budget: {response.text}")

        logger.info("LiteLLM-User %s Budget erfolgreich aktualisiert", pseudonym)

    async def list_models(self) -> list[str]:
        """
        GET /models.
        Gibt eine deduplizierte Liste von Modell-IDs zurück.
        """
        client = await self._get_client()
        url = f"{self.base_url}/models"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
        }

        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            logger.error(
                "LiteLLM list_models fehlerhaft: status=%d, body=%s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(f"Failed to fetch LiteLLM models: {response.text}")

        payload = response.json()
        entries: list = []

        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                entries = payload["data"]
            elif isinstance(payload.get("models"), list):
                entries = payload["models"]
        elif isinstance(payload, list):
            entries = payload

        model_ids: list[str] = []
        seen: set[str] = set()
        for entry in entries:
            model_id = None
            if isinstance(entry, str):
                model_id = entry
            elif isinstance(entry, dict):
                model_id = (
                    entry.get("id")
                    or entry.get("model_name")
                    or entry.get("model")
                    or entry.get("name")
                )

            if not model_id or not isinstance(model_id, str):
                continue
            if model_id in seen:
                continue
            seen.add(model_id)
            model_ids.append(model_id)

        return model_ids

    async def delete_user(self, pseudonym: str) -> None:
        """
        POST /user/delete.
        404 wird als Erfolg behandelt (idempotentes Verhalten).
        """
        client = await self._get_client()
        url = f"{self.base_url}/user/delete"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }
        payload = {"user_ids": [pseudonym]}

        response = await client.post(url, headers=headers, json=payload)
        if response.status_code in (200, 202, 204, 404):
            return

        logger.error(
            "LiteLLM delete_user fehlerhaft: status=%d, body=%s, pseudonym=%s payload=%s",
            response.status_code,
            response.text,
            pseudonym,
            payload,
        )
        raise RuntimeError(f"Failed to delete LiteLLM user: {response.text}")

    async def create_team(self, team_id: str) -> None:
        """
        POST /team/new — legt Team an, falls noch nicht vorhanden.
        409/Konflikt wird als Erfolg behandelt (idempotent).
        """
        client = await self._get_client()
        url = f"{self.base_url}/team/new"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "team_id": team_id,
            "team_alias": team_id,
            "models": ["no-default-models"],
        }

        response = await client.post(url, headers=headers, json=payload)

        if response.status_code in (200, 201, 409):
            return

        logger.error(
            "LiteLLM create_team fehlerhaft: status=%d, body=%s, payload=%s",
            response.status_code,
            response.text,
            payload,
        )
        raise RuntimeError(f"Failed to create LiteLLM team: {response.text}")

    async def list_teams(self) -> list[dict]:
        """
        GET /team/list.
        Gibt eine Liste von Team-Objekten zurück.
        """
        client = await self._get_client()
        url = f"{self.base_url}/team/list"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
        }

        response = await client.get(url, headers=headers)
        if response.status_code != 200:
            logger.error(
                "LiteLLM list_teams fehlerhaft: status=%d, body=%s",
                response.status_code,
                response.text,
            )
            raise RuntimeError(f"Failed to list LiteLLM teams: {response.text}")

        payload = response.json()
        if isinstance(payload, dict):
            if isinstance(payload.get("data"), list):
                return payload["data"]
            if isinstance(payload.get("teams"), list):
                return payload["teams"]
        if isinstance(payload, list):
            return payload
        return []

    async def get_team_info(self, team_id: str) -> dict | None:
        """
        GET /team/info?team_id={team_id}.
        Gibt das Team-Objekt zurück; None bei 404.
        Das Feld 'models' im Response enthält die Allowlist (list[str]).
        Fehlt es oder ist es None, wird [] zurückgegeben.
        """
        client = await self._get_client()
        response = await client.get(
            f"{self.base_url}/team/info",
            headers={"Authorization": f"Bearer {self.master_key}"},
            params={"team_id": team_id},
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            logger.error(
                "LiteLLM get_team_info fehlerhaft: status=%d, team=%s, body=%s",
                response.status_code, team_id, response.text,
            )
            raise RuntimeError(f"Failed to get team info for {team_id}: {response.text}")
        data = response.json()
        return data.get("team_info", data)

    async def update_team_models(self, team_id: str, models: list[str]) -> None:
        """
        POST /team/update - setzt die Allowlist des Teams.
        """
        client = await self._get_client()
        payload = {"team_id": team_id, "models": models}
        response = await client.post(
            f"{self.base_url}/team/update",
            headers={
                "Authorization": f"Bearer {self.master_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        if response.status_code not in (200, 201):
            logger.error(
                "LiteLLM update_team_models fehlerhaft: status=%d, team=%s, body=%s",
                response.status_code, team_id, response.text,
            )
            raise RuntimeError(f"Failed to update team models for {team_id}: {response.text}")
        logger.info("LiteLLM-Team %s Allowlist aktualisiert: %s", team_id, models)

    async def add_team_member(self, team_id: str, pseudonym: str) -> None:
        """
        POST /team/member_add.
        """
        client = await self._get_client()
        url = f"{self.base_url}/team/member_add"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "team_id": team_id,
            "member": {"role": "user", "user_id": pseudonym},
        }

        response = await client.post(url, headers=headers, json=payload)
        if response.status_code not in (200, 201):
            logger.error(
                "LiteLLM add_team_member fehlerhaft: status=%d, body=%s, payload=%s",
                response.status_code,
                response.text,
                payload,
            )
            raise RuntimeError(f"Failed to add team member: {response.text}")

    async def remove_team_member(self, team_id: str, pseudonym: str) -> None:
        """
        POST /team/member_delete.
        404 wird als idempotenter Erfolg behandelt.
        """
        client = await self._get_client()
        url = f"{self.base_url}/team/member_delete"
        headers = {
            "Authorization": f"Bearer {self.master_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "team_id": team_id,
            "user_id": pseudonym,
        }

        response = await client.post(url, headers=headers, json=payload)
        if response.status_code in (200, 201, 204, 404):
            return

        logger.error(
            "LiteLLM remove_team_member fehlerhaft: status=%d, body=%s, payload=%s",
            response.status_code,
            response.text,
            payload,
        )
        raise RuntimeError(f"Failed to remove team member: {response.text}")

    async def generate_key(self, pseudonym: str) -> str:
        """
        POST /key/generate — legt einen Virtual Key für den User an.
        Gibt den Key-String zurück (wird im Backend gespeichert).
        """
        client = await self._get_client()
        payload = {"user_id": pseudonym}
        response = await client.post(
            f"{self.base_url}/key/generate",
            headers={"Authorization": f"Bearer {self.master_key}", "Content-Type": "application/json"},
            json=payload,
        )
        if response.status_code not in (200, 201):
            raise RuntimeError(f"Failed to generate LiteLLM key: {response.text}")
        return response.json()["key"]

    async def delete_key(self, key: str) -> None:
        """
        POST /key/delete — löscht den Virtual Key. Idempotent (404 = Erfolg).
        """
        client = await self._get_client()
        response = await client.post(
            f"{self.base_url}/key/delete",
            headers={"Authorization": f"Bearer {self.master_key}", "Content-Type": "application/json"},
            json={"keys": [key]},
        )
        if response.status_code in (200, 204, 404):
            return
        raise RuntimeError(f"Failed to delete LiteLLM key: {response.text}")

    async def list_guardrails(self) -> list[dict]:
        """
        GET /guardrails/list.
        Gibt eine normalisierte Liste von Guardrail-Objekten zurück.
        Bei Fehler: leere Liste (kein Hard-Fail — LiteLLM ist optional konfiguriert).

        Normalisiertes Format je Eintrag:
          { "name": str, "mode": str | None }
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/guardrails/list",
                headers={"Authorization": f"Bearer {self.master_key}"},
            )
            if response.status_code != 200:
                logger.warning(
                    "list_guardrails fehlerhaft: status=%d, body=%s",
                    response.status_code, response.text[:200],
                )
                return []
            payload = response.json()
            raw: list = []
            if isinstance(payload, dict):
                raw = payload.get("guardrails", [])
            elif isinstance(payload, list):
                raw = payload

            result = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                params = item.get("litellm_params", {}) or {}
                name = (
                    item.get("guardrail_name")
                    or params.get("guardrail_name")
                    or params.get("guardrail")
                    or ""
                )
                mode = params.get("mode")
                if name:
                    result.append({"name": name, "mode": mode})
            return result
        except Exception:
            logger.exception("list_guardrails Exception")
            return []

    async def get_spend_log(self, request_id: str) -> float | None:
        """
        GET /spend/logs/v2?request_id={request_id}&start_date=...&end_date=...
        Gibt die Kosten des Requests zurück, None wenn nicht gefunden.

        start_date/end_date (±1 Tag) sind Pflichtparameter des Endpoints.
        request_id wird unverändert übergeben — LiteLLM speichert IDs im selben
        Format wie der Stream-Chunk sie liefert (OpenAI: chatcmpl-..., andere: UUID).
        """
        from datetime import date, timedelta
        today = date.today()
        try:
            client = await self._get_client()
            url = f"{self.base_url}/spend/logs/v2"
            headers = {"Authorization": f"Bearer {self.master_key}"}
            params = {
                "request_id": request_id,
                "start_date": (today - timedelta(days=1)).isoformat(),
                "end_date": (today + timedelta(days=1)).isoformat(),
            }
            response = await client.get(url, headers=headers, params=params)
            if response.status_code != 200:
                logger.warning(
                    "get_spend_log fehlerhaft: status=%d request_id=%s body=%s",
                    response.status_code, request_id, response.text[:200],
                )
                return None
            data = response.json().get("data", [])
            if not data:
                return None
            entry = data[0]
            spend = entry.get("spend")
            if spend:
                return float(spend)
            # Fallback: spend=0 bei sehr günstigen Modellen
            total_cost = (
                entry.get("metadata", {})
                    .get("cost_breakdown", {})
                    .get("total_cost")
            )
            return float(total_cost) if total_cost else None
        except Exception:
            logger.exception("get_spend_log Exception für request_id=%s", request_id)
            return None

    async def get_model_info(self) -> dict[str, bool | None]:
        """
        GET /model/info → Map model_name → supports_function_calling.
        Gibt {} zurück bei Fehler (kein Hard-Fail).
        Unbekannte/fehlende Werte → None.
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/model/info",
                headers={"Authorization": f"Bearer {self.master_key}"},
            )
            if response.status_code != 200:
                logger.warning(
                    "get_model_info fehlerhaft: status=%d, body=%s",
                    response.status_code, response.text[:200],
                )
                return {}
            data = response.json().get("data", [])
            return {
                entry["model_name"]: entry.get("model_info", {}).get("supports_function_calling")
                for entry in data
                if isinstance(entry, dict) and "model_name" in entry
            }
        except Exception:
            logger.exception("get_model_info Exception")
            return {}

    async def get_image_model_ids(self) -> list[str]:
        """
        GET /model/info → Modell-IDs mit ``model_info.mode == "image_generation"``.

        Trennt Bild-Modelle von Chat-Modellen anhand des in der LiteLLM-Config
        gesetzten Modus (``model_info.mode``). Wird von beiden Freischaltungs-Matrizen
        genutzt: die Chat-Matrix blendet diese IDs aus, die Bild-Matrix zeigt nur sie.
        Gibt [] zurück bei Fehler (kein Hard-Fail — die aufrufende Matrix degradiert
        dann sauber: keine Bild-Spalten bzw. keine Ausblendung, aber kein Datenverlust).
        """
        try:
            client = await self._get_client()
            response = await client.get(
                f"{self.base_url}/model/info",
                headers={"Authorization": f"Bearer {self.master_key}"},
            )
            if response.status_code != 200:
                logger.warning(
                    "get_image_model_ids fehlerhaft: status=%d, body=%s",
                    response.status_code, response.text[:200],
                )
                return []
            data = response.json().get("data", [])
            ids: list[str] = []
            seen: set[str] = set()
            for entry in data:
                if not isinstance(entry, dict) or "model_name" not in entry:
                    continue
                mode = (entry.get("model_info") or {}).get("mode")
                if mode == "image_generation":
                    name = entry["model_name"]
                    if name not in seen:
                        seen.add(name)
                        ids.append(name)
            return ids
        except Exception:
            logger.exception("get_image_model_ids Exception")
            return []

    async def generate_image(
        self,
        prompt: str,
        *,
        model: str,
        api_key: str,
        user: str,
        size: str | None = None,
        response_format: str | None = "b64_json",
        n: int = 1,
    ) -> "ImageGenerationResult":
        """
        POST /images/generations (OpenAI-kompatibel) → Bytes + Kosten.

        Die Kosten kommen aus dem ``x-litellm-response-cost``-Header des (nicht
        gestreamten) Bild-Calls — kein zweiter Spend-Log-Roundtrip nötig. Fehlt der
        Header (z. B. kein Pricing hinterlegt), ist ``cost_usd`` None; das Budget am
        Virtual Key greift trotzdem, nur die angezeigten Kosten unterzählen dann.

        Ruft über den **Virtual Key des Users** (``api_key``) — nicht den Master-Key —,
        damit Spend/Budget dem User zugerechnet werden (wie der Chat-Call). Kein
        Streaming: ein Request / eine Response; die Generierung dauert Sekunden →
        eigenes, großzügigeres Timeout (``settings.image_generation_timeout``).

        Datenschutz: Es werden **nur Base64-Bilder** verarbeitet. Liefert der Provider
        stattdessen eine (extern gehostete) URL, wird abgebrochen — die Bytes sollen
        das Schulnetz nicht über einen zweiten Request zum Provider verlassen.
        ``response_format="b64_json"`` erzwingt Base64 bei URL-fähigen Modellen; für
        Modelle, die ohnehin nur Base64 liefern und den Parameter ablehnen
        (``gpt-image-1``), ``response_format=None`` übergeben.

        Wirft ``RuntimeError`` bei Nicht-200, leerer/fehlender Bilddaten oder wenn der
        Provider eine URL statt Base64 liefert.
        """
        client = await self._get_client()
        url = f"{self.base_url}/images/generations"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        payload: dict = {
            "model": model,
            "prompt": prompt,
            "n": n,
            "size": size or settings.image_default_size,
            "user": user,
        }
        if response_format:
            payload["response_format"] = response_format

        response = await client.post(
            url,
            headers=headers,
            json=payload,
            timeout=settings.image_generation_timeout,
        )

        if response.status_code != 200:
            logger.error(
                "LiteLLM generate_image fehlerhaft: status=%d, model=%s, body=%s",
                response.status_code, model, response.text[:500],
            )
            raise RuntimeError(f"Failed to generate image: {response.text}")

        raw_cost = response.headers.get("x-litellm-response-cost")
        try:
            cost_usd = float(raw_cost) if raw_cost else None
        except (TypeError, ValueError):
            cost_usd = None

        data = response.json().get("data", [])
        if not data:
            logger.error("LiteLLM generate_image: leere data-Liste (model=%s)", model)
            raise RuntimeError("Image generation returned no data")

        entry = data[0]
        b64 = entry.get("b64_json")
        if b64:
            return ImageGenerationResult(image_bytes=base64.b64decode(b64), cost_usd=cost_usd)

        # Datenschutz-Grenze: keine extern gehosteten Bild-URLs verarbeiten.
        if entry.get("url"):
            logger.error(
                "LiteLLM generate_image lieferte URL statt Base64 (model=%s) — "
                "response_format=b64_json setzen bzw. b64-fähiges Modell nutzen.",
                model,
            )
            raise RuntimeError(
                "Image provider returned a URL instead of base64; "
                "external image URLs are not permitted."
            )

        logger.error("LiteLLM generate_image: weder b64_json noch url (model=%s)", model)
        raise RuntimeError("Image generation response missing image data")
