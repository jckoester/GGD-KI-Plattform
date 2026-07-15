"""Unit-Tests: vertrauenswürdige Client-IP-Ableitung (Sicherheits-Audit #13)."""
from starlette.requests import Request

from app.core.client_ip import client_ip


def _request(peer: str | None, xff: str | None = None) -> Request:
    headers = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345) if peer else None,
    }
    return Request(scope)


TRUSTED = ["127.0.0.1", "::1"]


def test_untrusted_peer_ignores_xff():
    # Direkt erreichbares Backend: XFF ist spoofbar → wird ignoriert, Peer zählt.
    req = _request("203.0.113.9", xff="1.2.3.4")
    assert client_ip(req, TRUSTED) == "203.0.113.9"


def test_trusted_peer_takes_rightmost_untrusted():
    # nginx (127.0.0.1) hängt die echte Client-IP rechts an; Spoof-Wert steht links.
    req = _request("127.0.0.1", xff="1.2.3.4, 198.51.100.7")
    assert client_ip(req, TRUSTED) == "198.51.100.7"


def test_trusted_peer_single_xff_entry():
    req = _request("127.0.0.1", xff="198.51.100.7")
    assert client_ip(req, TRUSTED) == "198.51.100.7"


def test_trusted_peer_without_xff_falls_back_to_peer():
    req = _request("127.0.0.1", xff=None)
    assert client_ip(req, TRUSTED) == "127.0.0.1"


def test_spoofed_trusted_proxy_in_xff_is_skipped():
    # Angreifer setzt XFF mit lauter Proxy-IPs → die rechteste NICHT-Proxy-IP gewinnt.
    req = _request("127.0.0.1", xff="203.0.113.5, 127.0.0.1")
    assert client_ip(req, TRUSTED) == "203.0.113.5"


def test_all_entries_trusted_returns_peer():
    req = _request("127.0.0.1", xff="127.0.0.1, ::1")
    assert client_ip(req, TRUSTED) == "127.0.0.1"


def test_cidr_trusted_network():
    # Docker-Bridge-Subnetz als CIDR.
    req = _request("172.18.0.2", xff="9.9.9.9, 198.51.100.7")
    assert client_ip(req, ["172.16.0.0/12"]) == "198.51.100.7"


def test_no_client_no_xff_returns_none():
    req = _request(None, xff=None)
    assert client_ip(req, TRUSTED) is None


def test_malformed_xff_entry_skipped():
    req = _request("127.0.0.1", xff="not-an-ip, 198.51.100.7")
    assert client_ip(req, TRUSTED) == "198.51.100.7"
