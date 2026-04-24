import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


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
