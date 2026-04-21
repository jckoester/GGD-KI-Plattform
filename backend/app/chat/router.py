from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

import httpx

from app.auth.dependencies import get_current_user
from app.auth.jwt import JwtPayload
from app.config import settings
from app.chat.schemas import ChatRequest


router = APIRouter(tags=["chat"])

_LITELLM_TIMEOUT = httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0)


@router.post("/chat")
async def chat(
    request: ChatRequest,
    current_user: JwtPayload = Depends(get_current_user),
):
    litellm_payload = {
        "model": settings.chat_default_model,
        "messages": [{"role": msg.role, "content": msg.content} for msg in request.messages],
        "stream": True,
        "user": current_user.sub,  # Pseudonym für LiteLLM Budget-Tracking
    }

    # Client außerhalb des Generators erstellen, damit wir den Status prüfen können
    # bevor die StreamingResponse beginnt — und ihn im Generator sauber schließen.
    client = httpx.AsyncClient(timeout=_LITELLM_TIMEOUT)
    try:
        req = client.build_request(
            "POST",
            f"{settings.litellm_proxy_url}/chat/completions",
            headers={"Authorization": f"Bearer {settings.litellm_master_key}"},
            json=litellm_payload,
        )
        response = await client.send(req, stream=True)
    except httpx.ConnectError:
        await client.aclose()
        raise HTTPException(status_code=502, detail="LiteLLM Proxy nicht erreichbar")

    # Status vor Stream-Start prüfen — danach ist HTTPException nicht mehr möglich
    if response.status_code != 200:
        error_body = await response.aread()
        await response.aclose()
        await client.aclose()
        raise HTTPException(
            status_code=response.status_code,
            detail=f"LiteLLM Fehler: {error_body.decode()}" if error_body else "LiteLLM Fehler",
        )

    async def generate():
        try:
            async for line in response.aiter_lines():
                if line:
                    # LiteLLM schickt Zeilen bereits im SSE-Format ("data: {...}")
                    yield f"{line}\n\n"
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(generate(), media_type="text/event-stream")
