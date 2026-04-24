import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/

from scripts.refresh_ecb_rate import fetch_ecb_rate

_VALID_XML = """\
<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-04-24">
      <Cube currency="USD" rate="1.1040"/>
      <Cube currency="GBP" rate="0.8650"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""

_XML_WITHOUT_USD = """\
<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-04-24">
      <Cube currency="GBP" rate="0.8650"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""

_XML_INVALID_RATE = """\
<?xml version="1.0" encoding="UTF-8"?>
<gesmes:Envelope xmlns:gesmes="http://www.gesmes.org/xml/2002-08-01"
                 xmlns="http://www.ecb.int/vocabulary/2002-08-01/eurofxref">
  <Cube>
    <Cube time="2026-04-24">
      <Cube currency="USD" rate="abc"/>
    </Cube>
  </Cube>
</gesmes:Envelope>
"""


@pytest.mark.asyncio
async def test_fetch_ecb_rate_parses_usd_correctly():
    """Valides XML mit USD rate="1.1040" -> 1.104 (float)"""
    mock_response = MagicMock()
    mock_response.text = _VALID_XML
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("scripts.refresh_ecb_rate.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=None)
        rate = await fetch_ecb_rate()

    assert rate == 1.104


@pytest.mark.asyncio
async def test_fetch_ecb_rate_usd_not_found_raises():
    """XML ohne USD-Cube -> ValueError"""
    mock_response = MagicMock()
    mock_response.text = _XML_WITHOUT_USD
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("scripts.refresh_ecb_rate.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="USD-Kurs nicht im EZB-Feed gefunden"):
            await fetch_ecb_rate()


@pytest.mark.asyncio
async def test_fetch_ecb_rate_invalid_rate_string_raises():
    """rate="abc" -> ValueError"""
    mock_response = MagicMock()
    mock_response.text = _XML_INVALID_RATE
    mock_response.raise_for_status.return_value = None
    mock_response.status_code = 200

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("scripts.refresh_ecb_rate.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="USD-Kurs ist keine g.ltige Zahl"):
            await fetch_ecb_rate()


@pytest.mark.asyncio
async def test_fetch_ecb_rate_http_error_propagates():
    """raise_for_status() wirft httpx.HTTPStatusError -> Propagiert"""
    import httpx

    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    # Mock raise_for_status to actually raise
    mock_response.raise_for_status.side_effect = httpx.HTTPStatusError("Internal Server Error", request=MagicMock(), response=mock_response)

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_response)

    with patch("scripts.refresh_ecb_rate.httpx.AsyncClient") as mock_ac:
        mock_ac.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_ac.return_value.__aexit__ = AsyncMock(return_value=None)
        with pytest.raises(httpx.HTTPStatusError):
            await fetch_ecb_rate()
