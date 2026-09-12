"""Welche Router ein Zugangstoken erreicht — und welche nicht.

**Warum es das braucht.** 156 Guard-Stellen in 32 Dateien laufen über
`get_current_user`; ein zweiter Auth-Zweig dort öffnet sie sonst alle auf einmal — Chat,
Budget, Verwaltung, Krisen-Einsicht inbegriffen. Die Tabelle unten ist die einzige Stelle,
an der ein Token Zugang bekommt.

**Deny-by-default, und zwar wörtlich.** Was hier nicht steht, ist für Token gesperrt.
Ein neuer Router ist damit ab der ersten Zeile zu, nicht erst, wenn jemand daran denkt —
die umgekehrte Bauart (eine Sperrliste) wäre bei jedem neuen Feature stillschweigend zu
eng geworden. Für Browser-Sitzungen ändert die Datei nichts.

**Kein Ersatz für die Rechteprüfung.** Ein Scope sagt nur, *welche Art* Anfrage ein Token
stellen darf. Ob die Person die Gruppe unterrichtet, entscheidet danach unverändert
`require_group_teacher` und die übrige Sichtbarkeitslogik.
"""

from fastapi import HTTPException

# Pfad-Präfix → (Scope zum Lesen, Scope zum Schreiben).
#
# Präfixe statt einzelner Routen — aber **so eng wie der Zweck**, nicht so weit wie der
# Router. `/context` als Ganzes wäre zu viel gewesen: Darunter hängen auch
# `/context/assistants/{id}/anchors` (Assistenten-Konfiguration) und
# `/context/conversations/{id}/nodes` (Anhänge einer Unterhaltung). Beides hat mit dem
# Kontextspeicher-Spiegel nichts zu tun und widerspräche der Zusage, dass ein Token
# weder in den Chat noch in die Verwaltung reicht.
#
# Was ein Client zusätzlich braucht, kommt als eigene Zeile dazu — bewusst, nicht durch
# das Wachsen eines Routers.
_ZUSTAENDIG: dict[str, tuple[str, str]] = {
    "/planning": ("planning:read", "planning:write"),
    "/context/nodes": ("context:read", "context:write"),
    "/context/edges": ("context:read", "context:write"),
    "/context/search": ("context:read", "context:write"),
}

# HTTP-Methoden, die lesen. Alles andere gilt als Schreiben.
_LESEND = frozenset({"GET", "HEAD", "OPTIONS"})

# Endpunkte, die trotz POST lesen. Die Suche braucht einen Rumpf (Filter, Vektor-Anfrage)
# und ist deshalb POST — sie ändert nichts. Ohne diese Ausnahme bräuchte ein rein
# spiegelndes Token Schreibrecht, um suchen zu dürfen, und das wäre die Regel auf den
# Kopf gestellt.
_LESEND_TROTZ_POST = frozenset({"/context/search"})

_KEIN_ZUGANG = HTTPException(
    status_code=403,
    detail="Dieser Bereich ist für Zugangstoken gesperrt.",
)


def benoetigter_scope(methode: str, pfad: str) -> str | None:
    """Der Scope, den ein Token für (Methode, Pfad) braucht. `None` = gar kein Zugang."""
    for praefix, (lesen, schreiben) in _ZUSTAENDIG.items():
        if pfad == praefix or pfad.startswith(praefix + "/"):
            if methode.upper() in _LESEND or pfad in _LESEND_TROTZ_POST:
                return lesen
            return schreiben
    return None


def pruefe_zugang(scopes: list[str], methode: str, pfad: str) -> None:
    """Wirft 403, wenn ein Token diesen Pfad nicht erreichen darf.

    Für Schreibzugriffe genügt der Schreib-Scope; Lesen ist darin **nicht** enthalten.
    Wer beides tun will, bekommt beide — das ist eine Zeile mehr bei der Erzeugung und
    erspart die Frage, was „write impliziert read" in einem halben Jahr bedeutete.
    """
    noetig = benoetigter_scope(methode, pfad)
    if noetig is None or noetig not in scopes:
        raise _KEIN_ZUGANG
