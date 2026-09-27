"""Der Upload-Endpunkt für Fachbegriffe (Paket 10, AP3).

`POST /context/fachbegriffe/import` ist derselbe Kern wie `scripts/seed_fachbegriffe.py`
— mit drei Unterschieden, und jeder davon ist hier ein Prüfsatz:

1. **Rechte** (Entscheidung D2): Schreibrecht im Fach, also Mitgliedschaft in dessen
   Fachschaft. Eine fremde Lehrkraft und eine Schülerin kommen nicht durch.
2. **Ein Fach**: Der Lauf ist an das Fach gebunden, für das die Rechte geprüft wurden.
   Eine Datei, die im Frontmatter ein anderes nennt, wird gemeldet — nicht umgehängt.
3. **Grenzen**: Größe, Anzahl, Zip-Bomben, Pfade aus dem Bündel heraus, Endungen,
   Abbildungen mit Skript. Die Mechanik dahinter prüft `tests/unit/`; hier geht es um
   die Verdrahtung — dass der Riegel am Endpunkt wirklich hängt.

⚠️ **Der wichtigste Fall ist der Probelauf.** Die Vorschau aus AP4 ist nur so viel wert
wie die Zusage „es wurde nichts geschrieben". Deshalb wird nach dem Probelauf in der
Datenbank nachgesehen, nicht im Bericht.

Router-Pfade ohne /api-Präfix (CLAUDE.md: FastAPI sieht /api nie).
"""
import io
import uuid
import zipfile

import psycopg2
import pytest

PFAD = "/context/fachbegriffe/import"

FACHSCHAFT = "fs-lehrkraft-import"
FREMDE = "fremde-lehrkraft-import"
SCHUELERIN = "schuelerin-import"

SVG = '<svg xmlns="http://www.w3.org/2000/svg"><path d="M0 0"/></svg>'
SVG_BOESE = '<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


def _md(titel: str, *, fach: str | None = "Importfach", zusatz: str = "") -> bytes:
    kopf = f"fach: {fach}\n" if fach else ""
    return (
        f"---\nknotentyp: begriff\ntitel: {titel}\n{kopf}{zusatz}---\n\n"
        f"Ein Text über {titel}.\n"
    ).encode("utf-8")


def _zip(eintraege: dict[str, bytes]) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        for pfad, inhalt in eintraege.items():
            z.writestr(pfad, inhalt)
    return puffer.getvalue()


def _datei(name: str, inhalt: bytes):
    return ("dateien", (name, inhalt, "application/octet-stream"))


@pytest.fixture(scope="module")
def sync_conn(db_url, run_migrations):
    conn = psycopg2.connect(db_url.replace("postgresql+asyncpg://", "postgresql://"))
    yield conn
    conn.close()


@pytest.fixture(scope="module")
def fach(sync_conn):
    """Fach „Importfach" mit Fachschaft — und eine Lehrkraft darin.

    Modulweit, weil `fach_code` schulweit eindeutig ist (`idx_subjects_fach_code`):
    Ein Fach je Test hieße ein Kürzel je Test.
    """
    kennung = uuid.uuid4().hex[:8]
    with sync_conn.cursor() as cur:
        cur.execute(
            "INSERT INTO subjects (slug, name, fach_code) VALUES (%s,%s,%s) RETURNING id",
            (f"importfach-{kennung}", "Importfach", f"IM{kennung[:4]}"),
        )
        subject_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO subjects (slug, name, fach_code) VALUES (%s,%s,%s) RETURNING id",
            (f"anderesfach-{kennung}", "Anderesfach", f"AN{kennung[:4]}"),
        )
        anderes_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO groups (name, slug, type, subject_id, sso_group_id)"
            " VALUES (%s,%s,'subject_department',%s,%s) RETURNING id",
            (f"FS Importfach {kennung}", f"fs-import-{kennung}", subject_id,
             f"fs-import-{kennung}"),
        )
        gruppe_id = cur.fetchone()[0]
        # ⚠️ **Das andere Fach braucht auch eine Fachschaft.** Ohne sie überspränge der
        # Import eine Datei mit fremdem `fach:` schon deshalb, weil er nirgends
        # hinschreiben könnte — und die Gegenprobe zur Fachbindung bliebe grün, obwohl
        # die Bindung fehlt. Genau so ist es beim ersten Anlauf passiert.
        cur.execute(
            "INSERT INTO groups (name, slug, type, subject_id, sso_group_id)"
            " VALUES (%s,%s,'subject_department',%s,%s) RETURNING id",
            (f"FS Anderesfach {kennung}", f"fs-anderes-{kennung}", anderes_id,
             f"fs-anderes-{kennung}"),
        )
        anderes_gruppe_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO group_memberships"
            " (group_id, pseudonym, role_in_group, herkunft)"
            " VALUES (%s,%s,'teacher','sso')",
            (gruppe_id, FACHSCHAFT),
        )
    sync_conn.commit()
    yield {"id": subject_id, "slug": f"importfach-{kennung}", "anderes_id": anderes_id}
    with sync_conn.cursor() as cur:
        cur.execute("DELETE FROM context_nodes WHERE subject_id IN (%s,%s)",
                    (subject_id, anderes_id))
        cur.execute("DELETE FROM group_memberships WHERE group_id = %s", (gruppe_id,))
        cur.execute("DELETE FROM groups WHERE id IN (%s,%s)",
                    (gruppe_id, anderes_gruppe_id))
        cur.execute("DELETE FROM subjects WHERE id IN (%s,%s)", (subject_id, anderes_id))
    sync_conn.commit()


@pytest.fixture(autouse=True)
def leerer_bestand(sync_conn, fach):
    """Vor **und** nach jedem Test: keine Knoten im Fach.

    Der echte Lauf committet — ohne diesen Schnitt trüge der nächste Test den Bestand
    des vorigen und „1 neu" hieße plötzlich „1 unverändert".
    """
    def weg():
        with sync_conn.cursor() as cur:
            cur.execute("DELETE FROM context_nodes WHERE subject_id IN (%s,%s)",
                        (fach["id"], fach["anderes_id"]))
        sync_conn.commit()
    weg()
    yield
    weg()


def _knoten(sync_conn, subject_id):
    with sync_conn.cursor() as cur:
        cur.execute(
            "SELECT title, metadata FROM context_nodes WHERE subject_id = %s"
            " ORDER BY title", (subject_id,)
        )
        return cur.fetchall()


@pytest.fixture
def fachschaft_headers(jwt_service):
    token, _ = jwt_service.issue(pseudonym=FACHSCHAFT, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def fremde_headers(jwt_service):
    token, _ = jwt_service.issue(pseudonym=FREMDE, roles=["teacher"], grade=None)
    return {"Cookie": f"session={token}"}


@pytest.fixture
def schuelerin_headers(jwt_service):
    token, _ = jwt_service.issue(pseudonym=SCHUELERIN, roles=["student"], grade="9")
    return {"Cookie": f"session={token}"}


# ── Rechte (D2) ──────────────────────────────────────────────────────────────

class TestWerImportierenDarf:
    @pytest.mark.asyncio
    async def test_schuelerin_nicht(self, test_client, fach, schuelerin_headers):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=schuelerin_headers,
        )
        assert antwort.status_code == 403

    @pytest.mark.asyncio
    async def test_fremde_lehrkraft_nicht(self, test_client, fach, fremde_headers):
        """Lehrkraft ja — aber nicht in dieser Fachschaft."""
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fremde_headers,
        )
        assert antwort.status_code == 403
        assert "Fachschaft" in antwort.json()["detail"]

    @pytest.mark.asyncio
    async def test_die_eigene_fachschaft_ja(self, test_client, fach, fachschaft_headers):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text

    @pytest.mark.asyncio
    async def test_admin_auch_ohne_mitgliedschaft(self, test_client, fach, auth_headers):
        """Admins machen das heute über das Skript; der Weg bleibt ihnen."""
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=auth_headers,
        )
        assert antwort.status_code == 200, antwort.text

    @pytest.mark.asyncio
    async def test_unbekanntes_fach(self, test_client, fachschaft_headers):
        antwort = await test_client.post(
            PFAD, params={"fach": "gibtesnicht"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.status_code == 404


# ── Probelauf ────────────────────────────────────────────────────────────────

class TestProbelauf:
    @pytest.mark.asyncio
    async def test_bericht_ja_bestand_nein(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """⚠️ Die eine Zusage, auf der die Vorschau aus AP4 steht.

        Nachgesehen wird in der **Datenbank**, nicht im Bericht: Ein Bericht, der
        „1 neu" sagt, sagt nichts darüber, ob die Transaktion verworfen wurde.
        """
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "true"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        bericht = antwort.json()
        assert bericht["probelauf"] is True and bericht["neu"] == 1
        assert _knoten(sync_conn, fach["id"]) == []

    @pytest.mark.asyncio
    async def test_ist_die_vorgabe(self, test_client, fach, fachschaft_headers, sync_conn):
        """Ohne Angabe wird nicht geschrieben — ein Schreiblauf ist eine Entscheidung."""
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.json()["probelauf"] is True
        assert _knoten(sync_conn, fach["id"]) == []


# ── Echter Lauf ──────────────────────────────────────────────────────────────

class TestEchterLauf:
    @pytest.mark.asyncio
    async def test_knoten_entsteht_mit_kennung(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        bericht = antwort.json()
        assert bericht["neu"] == 1 and bericht["probelauf"] is False
        zeilen = _knoten(sync_conn, fach["id"])
        assert [z[0] for z in zeilen] == ["Alpha"]
        assert zeilen[0][1]["seed_id"].endswith("-alpha")

    @pytest.mark.asyncio
    async def test_zweiter_lauf_unveraendert(
        self, test_client, fach, fachschaft_headers
    ):
        for _ in range(2):
            antwort = await test_client.post(
                PFAD, params={"fach": fach["slug"], "probelauf": "false"},
                files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
            )
        assert antwort.json()["unveraendert"] == 1

    @pytest.mark.asyncio
    async def test_zip_mit_abbildung(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        zusatz = (
            "illustrationen:\n  - datei: _Abb/schema.svg\n"
            "    beschreibung: \"Ein Kreis.\"\n"
        )
        roh = _zip({
            "Alpha.md": _md("Alpha", zusatz=zusatz),
            "_Abb/schema.svg": SVG.encode("utf-8"),
        })
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("pilot.zip", roh)], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["warnungen"] == []
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert metadata["illustrationen"][0]["svg"] == SVG

    @pytest.mark.asyncio
    async def test_einzelne_abbildung_ohne_ordner(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """Frontmatter nennt `schema.svg`, im Bündel liegt `_Abb/schema.svg`.

        ⚠️ **Die Angabe ohne Ordner ist der Punkt.** Wer zwei Dateien auswählt statt
        ein Archiv, denkt nicht in Vault-Pfaden — und die Oberfläche vergleicht an
        derselben Stelle seit jeher Dateinamen statt Pfade (`abbildungen.js`). Mit
        `_Abb/schema.svg` im Frontmatter träfe schon der genaue Pfad, und der
        Rückgriff bliebe ungeprüft (beim ersten Anlauf genau so passiert).
        """
        zusatz = (
            "illustrationen:\n  - datei: schema.svg\n"
            "    beschreibung: \"Ein Kreis.\"\n"
        )
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[
                _datei("Alpha.md", _md("Alpha", zusatz=zusatz)),
                _datei("schema.svg", SVG.encode("utf-8")),
            ],
            headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert metadata["illustrationen"][0]["svg"] == SVG


# ── Ein Fach, nicht irgendeins ───────────────────────────────────────────────

class TestFachbindung:
    @pytest.mark.asyncio
    async def test_fremdes_fach_in_der_datei_wird_gemeldet(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """⚠️ **Kein stilles Umhängen.** Das Fach steht in der Datei, weil jemand es
        dort hingeschrieben hat; es zu überstimmen, ohne es zu sagen, verwandelt einen
        Tippfehler in einen Knoten am falschen Ort."""
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha", fach="Anderesfach"))],
            headers=fachschaft_headers,
        )
        bericht = antwort.json()
        assert bericht["neu"] == 0
        # Der Wortlaut zählt: „hat keine Fachschaftsgruppe" wäre dieselbe Zahl aus
        # einem ganz anderen Grund — und hat die Gegenprobe einmal grün gehalten.
        assert any(
            "importiert wird nach Importfach" in w for w in bericht["warnungen"]
        ), bericht
        assert _knoten(sync_conn, fach["anderes_id"]) == []

    @pytest.mark.asyncio
    async def test_datei_ohne_fach_landet_im_gewaehlten(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha", fach=None))],
            headers=fachschaft_headers,
        )
        assert antwort.json()["neu"] == 1, antwort.text
        assert len(_knoten(sync_conn, fach["id"])) == 1


# ── Grenzen ──────────────────────────────────────────────────────────────────

class TestGrenzenAmEndpunkt:
    """Die Mechanik steht in `tests/unit/test_fachbegriffe_upload.py`.

    Hier hängt nur die Frage, ob der Riegel am Endpunkt wirklich angeschlossen ist —
    einmal pro Art von Riegel, mit echten Daten statt verkleinerten Grenzen.
    """

    @pytest.mark.asyncio
    async def test_falsche_endung(self, test_client, fach, fachschaft_headers):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Notizen.docx", b"x")], headers=fachschaft_headers,
        )
        assert antwort.status_code == 415

    @pytest.mark.asyncio
    async def test_zip_bombe(self, test_client, fach, fachschaft_headers):
        """25 MB Nullen komprimieren auf wenige Kilobyte — das Archiv sieht harmlos
        aus und ist es nicht."""
        roh = _zip({"gross.md": b"\x00" * (25 * 1024 * 1024)})
        assert len(roh) < 100_000, "das Archiv soll klein sein, sonst prüft es nichts"
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("bombe.zip", roh)], headers=fachschaft_headers,
        )
        assert antwort.status_code == 413

    @pytest.mark.asyncio
    async def test_pfad_aus_dem_buendel_heraus(
        self, test_client, fach, fachschaft_headers
    ):
        roh = _zip({"../heimlich.md": _md("Heimlich")})
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("pilot.zip", roh)], headers=fachschaft_headers,
        )
        assert antwort.status_code == 400

    @pytest.mark.asyncio
    async def test_abbildung_mit_skript(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """Die Abbildung fällt weg, der Knoten bleibt — und der Bericht sagt warum."""
        zusatz = (
            "illustrationen:\n  - datei: _Abb/boese.svg\n"
            "    beschreibung: \"Angeblich ein Kreis.\"\n"
        )
        roh = _zip({
            "Alpha.md": _md("Alpha", zusatz=zusatz),
            "_Abb/boese.svg": SVG_BOESE.encode("utf-8"),
        })
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("pilot.zip", roh)], headers=fachschaft_headers,
        )
        bericht = antwort.json()
        assert any("abgelehnt" in w and "script" in w for w in bericht["warnungen"]), bericht
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert "svg" not in metadata["illustrationen"][0]
