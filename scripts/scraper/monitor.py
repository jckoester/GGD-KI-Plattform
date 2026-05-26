"""Monitor: prueft ob sich Fassungsdaten geaendert haben.

Aufruf:
  python -m scripts.scraper.monitor --subjects config/subjects.yaml
Gibt Liste geaenderter fach_codes aus (exit code 0 = alles aktuell, 1 = Aenderungen).
"""

import asyncio
import json
import re
import sys
from pathlib import Path

import httpx
import yaml

BASE_URL = 'https://www.bildungsplaene-bw.de/,Lde/'
STATE_FILE = Path('data/scraper_state.json')


async def fetch_version_date(client: httpx.AsyncClient, bp_id: str) -> str | None:
    """Fetcht die Fassungsdaten-Seite und extrahiert das Datum."""
    url = BASE_URL + bp_id
    try:
        resp = await client.get(url, follow_redirects=True, timeout=15)
        resp.raise_for_status()
        # Datum in Meta-Tags oder Fusszeile suchen
        m = re.search(r'Fassung\s+(?:vom\s+)?(\d{2}\.\d{2}\.\d{4})', resp.text)
        if m:
            return m.group(1)
    except Exception:
        pass
    return None


async def check_for_updates(subjects_path: str = 'config/subjects.yaml') -> list[str]:
    """Gibt Liste der fach_codes zurueck, bei denen sich das Fassungsdatum geaendert hat."""
    state: dict[str, str] = {}
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text())

    with open(subjects_path, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)

    schulart = cfg['schulart']
    bp_default = cfg.get('bildungsplan_default', {})
    bp_basis = bp_default.get('bp_basis', 'BP2016BW')

    changed = []
    async with httpx.AsyncClient(timeout=15) as client:
        for fach in cfg['subjects']:
            fach_code = fach.get('fach_code')
            if not fach_code:
                continue
            bp_id = f"{bp_basis}_ALLG_{schulart}_{fach_code}"
            current_date = await fetch_version_date(client, bp_id)
            if current_date and state.get(bp_id) != current_date:
                changed.append(fach_code)
                state[bp_id] = current_date
            await asyncio.sleep(0.5)

    STATE_FILE.parent.mkdir(exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2))
    return changed


if __name__ == '__main__':
    changed = asyncio.run(check_for_updates())
    if changed:
        print('Geaenderte Faeccher:', changed)
        sys.exit(1)
    else:
        print('Keine Aenderungen')
        sys.exit(0)
