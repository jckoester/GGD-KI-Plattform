#!/usr/bin/env python3
"""
Testet ob LiteLLM den x-litellm-response-cost Header korrekt befüllt —
einmal mit Streaming, einmal ohne. Liest einen Virtual Key aus der DB.

Verwendung:
    python scripts/test_cost_header.py
    python scripts/test_cost_header.py --key sk-...   # Key direkt übergeben
    python scripts/test_cost_header.py --model openai/gpt-4o-mini
"""
import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select

from app.config import settings
from app.db.models import PseudonymAudit
from app.db.session import AsyncSessionLocal

PROMPT = [{"role": "user", "content": "Antworte mit einem einzigen Wort: Hallo"}]
COST_HEADER = "x-litellm-response-cost"


async def get_first_virtual_key() -> str | None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(PseudonymAudit.litellm_key)
            .where(PseudonymAudit.litellm_key.isnot(None))
            .limit(1)
        )
        return result.scalar_one_or_none()


async def test_non_streaming(client: httpx.AsyncClient, key: str, model: str) -> None:
    print("\n── Non-Streaming ──────────────────────────────────────")
    response = await client.post(
        f"{settings.litellm_proxy_url}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": PROMPT, "stream": False},
        timeout=30,
    )
    print(f"Status: {response.status_code}")
    print(f"{COST_HEADER}: {response.headers.get(COST_HEADER, '(nicht vorhanden)')}")
    if response.status_code == 200:
        data = response.json()
        usage = data.get("usage", {})
        print(f"usage: {usage}")


async def test_streaming(client: httpx.AsyncClient, key: str, model: str) -> None:
    print("\n── Streaming ──────────────────────────────────────────")
    async with client.stream(
        "POST",
        f"{settings.litellm_proxy_url}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": PROMPT, "stream": True},
        timeout=30,
    ) as response:
        print(f"Status: {response.status_code}")
        # Response-Header kommen vor dem Body an
        print(f"{COST_HEADER} (initial): {response.headers.get(COST_HEADER, '(nicht vorhanden)')}")

        usage_chunk = None
        async for line in response.aiter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            import json
            try:
                chunk = json.loads(payload)
                if chunk.get("usage"):
                    usage_chunk = chunk["usage"]
            except json.JSONDecodeError:
                pass

        # Trailer-Header (falls LiteLLM sie als Trailer sendet)
        print(f"{COST_HEADER} (nach Stream): {response.headers.get(COST_HEADER, '(nicht vorhanden)')}")
        if usage_chunk:
            print(f"usage chunk: {usage_chunk}")
        else:
            print("usage chunk: keiner empfangen")


async def main(key: str | None, model: str) -> None:
    if key is None:
        key = await get_first_virtual_key()
        if key is None:
            print("Kein Virtual Key in der DB gefunden. Bitte --key übergeben.")
            sys.exit(1)
        print(f"Virtual Key aus DB: {key[:12]}...")
    else:
        print(f"Virtual Key (Argument): {key[:12]}...")

    async with httpx.AsyncClient(verify=settings.litellm_verify_ssl) as client:
        await test_non_streaming(client, key, model)
        await test_streaming(client, key, model)

    print()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--key", default=None, help="Virtual Key (Standard: aus DB)")
    parser.add_argument("--model", default=settings.chat_default_model)
    args = parser.parse_args()
    asyncio.run(main(args.key, args.model))
