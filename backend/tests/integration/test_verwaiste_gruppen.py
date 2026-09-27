"""Verwaiste Unterrichtsgruppen finden (Paket 7, AP3).

Eine Unterrichtsgruppe ohne Lehrkraft ist für niemanden erreichbar: Die Jahresübersicht
verlangt eine Lehrkraft-Mitgliedschaft (`require_group_teacher` → 403), und in der
Gruppenliste erscheinen nur die eigenen. Jahresplan, Stundenentwürfe und Konversationen
bleiben trotzdem stehen.

**Gemessen, nicht vermutet** (25.09.2026): Das entsteht auch in Produktion. Der Immediate
Mirror entfernt die Mitgliedschaft, sobald die SSO-Gruppe nicht mehr im Token steht; der
90-Tage-Löschlauf nimmt sie mitsamt dem Konto — bei einer Lehrkraft, die die Schule
verlässt, der Normalfall.

⚠️ **Gegen die Datenbank, nicht gegen einen Mock.** Die Unit-Tests der Admin-Endpunkte
arbeiten mit `MagicMock`; ein `NOT EXISTS` über eine zweite Tabelle prüfen sie damit
nicht. Genau daran hängt dieser Filter.
"""
import psycopg2
import pytest

from tests.integration.conftest import TEACHER1_PSEUDO, TEACHER2_PSEUDO

pytestmark = pytest.mark.asyncio

SLUGS = ("vw-mit-lehrkraft", "vw-ohne-lehrkraft", "vw-nur-schueler", "vw-klasse")


@pytest.fixture
def welt(db_url, run_migrations):
    """Vier Gruppen: mit Lehrkraft, ohne, nur mit Schüler:in, und eine Klasse."""
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    ids = {}
    with conn.cursor() as cur:
        for slug, typ in (
            ("vw-mit-lehrkraft", "teaching_group"),
            ("vw-ohne-lehrkraft", "teaching_group"),
            ("vw-nur-schueler", "teaching_group"),
            ("vw-klasse", "school_class"),
        ):
            cur.execute(
                "INSERT INTO groups (name, slug, type) VALUES (%s, %s, %s) RETURNING id",
                (slug, slug, typ),
            )
            ids[slug] = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
            " VALUES (%s, %s, 'teacher', 'manuell')",
            (ids["vw-mit-lehrkraft"], TEACHER1_PSEUDO),
        )
        # ⚠️ Eine Schüler-Mitgliedschaft macht die Gruppe **nicht** betreut. Ohne diesen
        # Fall genügte ein `NOT EXISTS` ohne Rollenbedingung, und der Filter übersähe
        # genau die Gruppen, in denen noch eine Klasse sitzt, aber niemand unterrichtet.
        cur.execute(
            "INSERT INTO group_memberships (group_id, pseudonym, role_in_group, herkunft)"
            " VALUES (%s, %s, 'student', 'manuell')",
            (ids["vw-nur-schueler"], TEACHER2_PSEUDO),
        )
    conn.commit()
    yield ids
    with conn.cursor() as cur:
        cur.execute("DELETE FROM groups WHERE slug = ANY(%s)", (list(SLUGS),))
    conn.commit()
    conn.close()


async def _namen(client, headers, **params) -> set[str]:
    resp = await client.get("/admin/groups", params=params, headers=headers)
    assert resp.status_code == 200, resp.text
    return {g["slug"] for g in resp.json()["items"] if g["slug"] in SLUGS}


async def test_filter_findet_die_unbetreute_gruppe(test_client, auth_headers, welt):
    gefunden = await _namen(test_client, auth_headers, ohne_lehrkraft="true")
    assert "vw-ohne-lehrkraft" in gefunden


async def test_gruppe_mit_lehrkraft_taucht_nicht_auf(test_client, auth_headers, welt):
    """Die Gegenprobe. Ohne sie prüfte der Test nur, dass die Liste nicht leer ist."""
    gefunden = await _namen(test_client, auth_headers, ohne_lehrkraft="true")
    assert "vw-mit-lehrkraft" not in gefunden


async def test_nur_schueler_zaehlt_nicht_als_betreut(test_client, auth_headers, welt):
    """Eine Gruppe voller Schüler:innen ohne Lehrkraft ist der eigentliche Schadensfall."""
    gefunden = await _namen(test_client, auth_headers, ohne_lehrkraft="true")
    assert "vw-nur-schueler" in gefunden


async def test_klassen_sind_kein_befund(test_client, auth_headers, welt):
    """Eine Klasse ohne Lehrkraft ist der Normalfall — sie gehörte nur ins Rauschen."""
    gefunden = await _namen(test_client, auth_headers, ohne_lehrkraft="true")
    assert "vw-klasse" not in gefunden


async def test_ohne_den_filter_sind_alle_da(test_client, auth_headers, welt):
    """Der Vorgabewert ändert nichts — der Filter ist eine Zugabe, keine Umstellung."""
    gefunden = await _namen(test_client, auth_headers)
    assert gefunden == set(SLUGS)


async def test_lehrkraft_ohne_adminrolle_kommt_nicht_dran(
    test_client, auth_headers_teacher2, welt
):
    resp = await test_client.get(
        "/admin/groups", params={"ohne_lehrkraft": "true"}, headers=auth_headers_teacher2
    )
    assert resp.status_code == 403
