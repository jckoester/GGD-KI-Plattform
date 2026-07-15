"""Vertrauenswürdige Ableitung der Client-IP hinter einem Reverse-Proxy (Sicherheits-Audit #13).

`X-Forwarded-For` ist frei vom Client setzbar. Wird es blind ausgewertet, kann ein Angreifer
bei direkter Erreichbarkeit des Backends die forensische Audit-IP fälschen. Diese Helfer werten
den Header **nur** aus, wenn der direkte TCP-Peer eine konfigurierte Proxy-Adresse ist, und
nehmen dann den rechtesten (proxy-nächsten) Eintrag, der selbst kein vertrauenswürdiger Proxy
ist — das ist die echte Client-IP, wie der vertrauenswürdige Proxy sie gesehen hat.
"""
from __future__ import annotations

import ipaddress
from typing import Iterable

from starlette.requests import Request


def _parse_networks(entries: Iterable[str]) -> list[ipaddress._BaseNetwork]:
    nets: list[ipaddress._BaseNetwork] = []
    for entry in entries:
        entry = (entry or "").strip()
        if not entry:
            continue
        try:
            # Einzel-IP wie CIDR behandeln (/32 bzw. /128) — strict=False toleriert Host-Bits.
            nets.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            continue
    return nets


def _is_trusted(ip: str | None, nets: list[ipaddress._BaseNetwork]) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(addr in net for net in nets)


def client_ip(request: Request, trusted_proxies: Iterable[str]) -> str | None:
    """Gibt die vertrauenswürdig abgeleitete Client-IP zurück (oder None).

    - Ist der direkte Peer (`request.client.host`) **kein** vertrauenswürdiger Proxy, wird
      `X-Forwarded-For` ignoriert und der Peer selbst zurückgegeben (anti-spoofing).
    - Andernfalls wird die XFF-Kette von rechts nach links durchlaufen und der erste Eintrag
      zurückgegeben, der selbst kein vertrauenswürdiger Proxy ist.
    """
    peer = request.client.host if request.client else None
    nets = _parse_networks(trusted_proxies)

    if not _is_trusted(peer, nets):
        return peer

    fwd = request.headers.get("x-forwarded-for")
    if not fwd:
        return peer

    for candidate in reversed([p.strip() for p in fwd.split(",") if p.strip()]):
        if not _is_trusted(candidate, nets):
            return candidate

    # Alle Einträge sind vertrauenswürdige Proxys → der Peer ist das Beste, was wir haben.
    return peer
