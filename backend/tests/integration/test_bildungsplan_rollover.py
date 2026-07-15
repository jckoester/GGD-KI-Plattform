"""Integrationstest: Schuljahr-Rollover der Bildungsplan-Editionen (Todo A3).

Seedt synthetische Fachplan-Knoten für zwei Editionen (Basis "2016" + V3 "2016.V3")
und schaltet ``GET /context/fachplan/by-subject`` über simulierte Schuljahre
(2025 → 2031) durch. Prüft end-to-end (Frontier + Endpoint + DB), dass je Stufe die
korrekte Edition ausgewählt wird und die V3-Frontier jahrgangsweise nach oben wandert.

Ergänzt die Unit-Tests in ``test_editions.py`` (dort ohne DB/Endpoint).
"""
import json
import uuid as _uuid
from unittest.mock import patch

import psycopg2
import pytest

# Kontrollierter Editions-Fahrplan — spiegelt die V3-Edition aus config/subjects.yaml
# (V3 ab Schuljahr 2026/27, Einstieg Stufen 5–7, wächst jahrgangsweise nach oben).
# Bewusst ohne V2, damit die Erwartungstabelle unabhängig von der realen Datei bleibt.
_ROLLOVER_CFG = {
    "bildungsplan_default": {
        "bp_basis": "BP2016BW",
        "suffix": "",
        "editionen": [
            {"suffix": ""},  # Basis "2016" — immer gültiger Fallback
            {
                "suffix": ".V3",
                "ab_schuljahr": "2026/27",
                "einstieg_stufen": [5, 7],
                "wachstum": "nach_oben",
            },
        ],
    }
}

_TEACHER_PSEUDO = "rollover-teacher-pseudo"

_SUBJECT_FULL = {"id": 300, "slug": "bp-rollover-full", "name": "Rollover Full"}
_SUBJECT_BASIS_ONLY = {"id": 301, "slug": "bp-rollover-basisonly", "name": "Rollover BasisOnly"}


def _nid() -> str:
    return str(_uuid.uuid4())


def _seed(db_url: str) -> dict:
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    ids = {"nodes": []}
    try:
        with conn.cursor() as cur:
            # Clean slate (feste IDs/Slugs; FKs sind ON DELETE SET NULL).
            cur.execute(
                "DELETE FROM context_nodes WHERE subject_id = ANY(%s)",
                ([_SUBJECT_FULL["id"], _SUBJECT_BASIS_ONLY["id"]],),
            )
            cur.execute(
                "DELETE FROM subjects WHERE id = ANY(%s) OR slug = ANY(%s)",
                (
                    [_SUBJECT_FULL["id"], _SUBJECT_BASIS_ONLY["id"]],
                    [_SUBJECT_FULL["slug"], _SUBJECT_BASIS_ONLY["slug"]],
                ),
            )
            for subj in (_SUBJECT_FULL, _SUBJECT_BASIS_ONLY):
                cur.execute(
                    "INSERT INTO subjects (id, name, slug) VALUES (%s, %s, %s)",
                    (subj["id"], subj["name"], subj["slug"]),
                )

            def _fachplan(subject_id: int, bp_version: str, label: str) -> None:
                node_id = _nid()
                ids["nodes"].append(node_id)
                cur.execute(
                    """
                    INSERT INTO context_nodes
                      (id, category, content_type, title, content, metadata,
                       read_scope, write_scope, status, owner_pseudonym,
                       subject_id, bp_version)
                    VALUES (%s, 'knowledge', 'fachplan', %s, NULL, %s,
                            'school', 'school', 'active', %s, %s, %s)
                    """,
                    (
                        node_id,
                        f"Fachplan {label}",
                        json.dumps({"bp_version": bp_version}),
                        _TEACHER_PSEUDO,
                        subject_id,
                        bp_version,
                    ),
                )

            # Fach mit beiden Editionen (Basis + V3)
            _fachplan(_SUBJECT_FULL["id"], "2016", "Basis")
            _fachplan(_SUBJECT_FULL["id"], "2016.V3", "V3")
            # Fach mit NUR Basis (für den Inhalts-Fallback)
            _fachplan(_SUBJECT_BASIS_ONLY["id"], "2016", "Basis")

        conn.commit()
    finally:
        conn.close()
    return ids


def _teardown(db_url: str) -> None:
    sync_url = db_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(sync_url)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM context_nodes WHERE subject_id = ANY(%s)",
                ([_SUBJECT_FULL["id"], _SUBJECT_BASIS_ONLY["id"]],),
            )
            cur.execute(
                "DELETE FROM subjects WHERE id = ANY(%s)",
                ([_SUBJECT_FULL["id"], _SUBJECT_BASIS_ONLY["id"]],),
            )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture(scope="session")
def rollover_data(db_url, run_migrations):
    ids = _seed(db_url)
    yield ids
    _teardown(db_url)


@pytest.fixture(scope="session")
def rollover_headers(jwt_service):
    token, _ = jwt_service.issue(pseudonym=_TEACHER_PSEUDO, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}


async def _resolved_bp_version(test_client, headers, subject_id, stufe, schuljahr):
    """Ruft den Endpoint mit gepatchtem Schuljahr/Fahrplan auf, gibt bp_version zurück."""
    with patch("app.context.editions.load_subjects_config", return_value=_ROLLOVER_CFG), \
         patch("app.context.editions.aktuelles_schuljahr_start", return_value=schuljahr):
        resp = await test_client.get(
            f"/context/fachplan/by-subject/{subject_id}?min_grade={stufe}",
            headers=headers,
        )
    assert resp.status_code == 200, resp.text
    return resp.json()["bp_version"]


# (schuljahr, stufe, erwartete bp_version) — V3-Frontier: og(V3) = 7 + (schuljahr - 2026)
_TABLE = [
    (2025, 5, "2016"),      # V3 noch nicht in Kraft
    (2025, 7, "2016"),
    (2026, 5, "2016.V3"),   # V3 startet: 5–7
    (2026, 7, "2016.V3"),
    (2026, 8, "2016"),      # og=7 → Stufe 8 noch Basis
    (2027, 8, "2016.V3"),   # og=8
    (2028, 9, "2016.V3"),   # og=9
    (2029, 10, "2016.V3"),  # og=10
    (2029, 11, "2016"),     # og=10 → Stufe 11 noch Basis
    (2031, 12, "2016.V3"),  # og=12
    (2031, 13, "2016"),     # og=12 → Stufe 13 noch Basis
]


@pytest.mark.asyncio
@pytest.mark.parametrize("schuljahr, stufe, erwartet", _TABLE)
async def test_rollover_frontier_je_schuljahr_und_stufe(
    test_client, rollover_headers, rollover_data, schuljahr, stufe, erwartet
):
    """Die geltende Edition wandert mit dem Schuljahr jahrgangsweise nach oben."""
    got = await _resolved_bp_version(
        test_client, rollover_headers, _SUBJECT_FULL["id"], stufe, schuljahr
    )
    assert got == erwartet, f"Schuljahr {schuljahr}, Stufe {stufe}: {got} != {erwartet}"


@pytest.mark.asyncio
async def test_rollover_inhalts_fallback_wenn_edition_nicht_importiert(
    test_client, rollover_headers, rollover_data
):
    """V3 ist laut Fahrplan in Kraft (2026, Stufe 5), aber für dieses Fach NICHT
    importiert → automatischer Fallback auf die Basis-Edition."""
    got = await _resolved_bp_version(
        test_client, rollover_headers, _SUBJECT_BASIS_ONLY["id"], stufe=5, schuljahr=2026
    )
    assert got == "2016"
