"""PII-Scan-Endpoint (Phase 14, Schritt 2).

Prüft eine Eingabe lokal auf Name/Wohnort, bevor sie gesendet wird. Eingeloggt,
**kein** Persistieren, **kein** externer Call. Das Frontend nutzt die Spans für den
Bestätigungsdialog (Schritt 5).
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.auth.jwt import JwtPayload
from app.pii.scanner import scan
from app.ratelimit.dependency import rate_limit

router = APIRouter(prefix="/pii", tags=["pii"])


class PiiScanRequest(BaseModel):
    text: str = Field(default="", max_length=20000)


class PiiSpanOut(BaseModel):
    category: str  # 'name' | 'wohnort'
    start: int
    end: int
    text: str


class PiiScanResponse(BaseModel):
    spans: list[PiiSpanOut]


@router.post("/scan", response_model=PiiScanResponse)
async def pii_scan(
    body: PiiScanRequest,
    _: JwtPayload = Depends(rate_limit("pii_scan")),
) -> PiiScanResponse:
    spans = scan(body.text)
    return PiiScanResponse(
        spans=[
            PiiSpanOut(category=s.category, start=s.start, end=s.end, text=s.text)
            for s in spans
        ]
    )
