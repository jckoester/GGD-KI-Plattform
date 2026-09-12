"""Die Drossel als Funktion — für Aufrufer, die keine FastAPI-Dependency sein können.

`rate_limit()` in `dependency.py` ist ein Drop-in-Ersatz für `get_current_user` und
deshalb auf Router zugeschnitten. Der Token-Pfad braucht dieselbe Prüfung *innerhalb*
von `get_current_user` — dort ist eine Dependency keine Option, und ein Import von
`dependency.py` wäre ein Zirkel (es importiert `get_current_user`).

Beide Wege benutzen dieselbe Funktion, damit es nicht zwei Auffassungen davon gibt, wie
ein 429 aussieht.
"""

from fastapi import HTTPException

from app.ratelimit import config, store


def pruefe(bucket: str, schluessel: str, rollen: list[str]) -> None:
    """Zählt eine Anfrage im Eimer `bucket` unter `schluessel`. Wirft 429, wenn voll.

    `schluessel` ist bewusst offen: Für Router-Drosselung ist es das Pseudonym, für
    Zugangstoken das Token. Das ist kein Detail — teilten sich Token und Browser-Sitzung
    einen Zähler, sperrte eine durchdrehende Sync-Schleife die Lehrkraft aus ihrer
    eigenen Oberfläche aus.
    """
    limit, window = config.resolve(bucket, rollen)
    ok, retry_after = store.allow(bucket, schluessel, limit, window)
    if not ok:
        raise HTTPException(
            status_code=429,
            detail="Zu viele Anfragen. Bitte kurz warten und erneut versuchen.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )
