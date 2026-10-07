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
from unittest.mock import AsyncMock, patch

import psycopg2
import pytest

from app.config import settings
from app.context.embedding import EmbeddingStapel

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
def ohne_drossel():
    """Den Zähler vor jedem Test leeren.

    ⚠️ Der Store ist prozess-lokal und **überlebt** den Test: Ab dem einundzwanzigsten
    Lauf in fünf Minuten antwortete der Endpunkt mit 429, und die Tests danach
    scheiterten an einer Grenze, die sie gar nicht prüfen wollten. Genau so passiert,
    als diese Datei über zwanzig Anfragen hinauswuchs.

    Dass die Drossel überhaupt hängt, prüft `tests/unit/test_beitritt_router.py`-artig
    die Verdrahtung — hier wäre sie nur Rauschen.
    """
    from app.ratelimit import store

    store.reset()
    yield
    store.reset()


#: Seit 0.14 (F7) bettet der Endpunkt nach einem echten Lauf im Hintergrund ein.
STAPEL = "app.crons.embedding_backfill_service.generate_embeddings"


@pytest.fixture(autouse=True)
def einbettung():
    """Eine Attrappe für jeden Test hier — sonst ginge jeder echte Lauf an den Proxy.

    Je Text derselbe Vektor in der konfigurierten Breite; die Tests unten lesen die
    Aufrufe mit.
    """
    async def _f(texte):
        return EmbeddingStapel(
            vektoren=[[0.5] * settings.embedding_dimensions for _ in texte],
            tokens=len(texte) * 10,
        )
    attrappe = AsyncMock(side_effect=_f)
    with patch(STAPEL, attrappe):
        yield attrappe


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
        """Lehrkraft ja — aber nicht in dieser Fachschaft.

        ⚠️ Die **Meldung** ist mitgeprüft, nicht nur der Status. „Nur die Fachschaft
        kann das" liest eine Chemielehrkraft als Widerspruch: Sie *ist* in der
        Fachschaft, nur nicht in der Gruppe, aus der die Plattform das ableitet. Ohne
        Ursache und Fach in der Meldung sucht sie den Fehler bei sich.
        """
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fremde_headers,
        )
        assert antwort.status_code == 403
        meldung = antwort.json()["detail"]
        assert "Fachschaftsgruppe" in meldung
        assert "Importfach" in meldung, "das betroffene Fach fehlt"
        assert "Schulkonto" in meldung, "der Grund fehlt"

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

    @pytest.mark.asyncio
    async def test_abbildung_mit_eingebettetem_png(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """0.14.1: Die Orbital-Abbildungen der Chemie sind PNGs in einer SVG-Hülle. Bis
        0.14.0 meldete der Import „verweist mit `href` nach außen" und legte den Eintrag
        ohne Bild an."""
        png = ("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlE"
               "QVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==")
        orbital = ('<svg xmlns="http://www.w3.org/2000/svg" '
                   'xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10">'
                   f'<image xlink:href="{png}" width="10" height="10"/></svg>')
        zusatz = (
            "illustrationen:\n  - datei: _Abb/p_z-Orbital.svg\n"
            "    beschreibung: \"Hantelförmiges p-Orbital.\"\n"
        )
        roh = _zip({
            "Alpha.md": _md("Alpha", zusatz=zusatz),
            "_Abb/p_z-Orbital.svg": orbital.encode("utf-8"),
        })
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("pilot.zip", roh)], headers=fachschaft_headers,
        )
        assert antwort.json()["warnungen"] == [], antwort.json()["warnungen"]
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert metadata["illustrationen"][0]["svg"] == orbital

    @pytest.mark.asyncio
    async def test_neuimport_bringt_das_abgelehnte_bild_zurueck(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """Die Zusage im CHANGELOG zu 0.14.1: Nach dem Update genügt ein Neuimport.

        Erster Lauf wie unter 0.14.0 (Prüfung lehnt ab, Eintrag ohne Bild); zweiter Lauf
        mit denselben Dateien. Er darf den Knoten nicht für handbearbeitet halten — sonst
        bliebe er „übersprungen" und das Bild weg."""
        from unittest.mock import patch

        png = "data:image/png;base64,iVBORw0KGgo="
        orbital = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1 1">'
                   f'<image href="{png}" width="1" height="1"/></svg>')
        zusatz = "illustrationen:\n  - datei: _Abb/s-Orbital.svg\n    beschreibung: \"Kugel.\"\n"
        roh = _zip({"Alpha.md": _md("Alpha", zusatz=zusatz),
                    "_Abb/s-Orbital.svg": orbital.encode("utf-8")})

        def senden():
            return test_client.post(
                PFAD, params={"fach": fach["slug"], "probelauf": "false"},
                files=[_datei("pilot.zip", roh)], headers=fachschaft_headers,
            )

        with patch("app.context.fachbegriffe_upload.pruefe_svg",
                   return_value="verweist mit `href` nach außen — `data:image/png`"):
            await senden()
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert "svg" not in metadata["illustrationen"][0], "Stand 0.14.0 nicht nachgestellt"

        bericht = (await senden()).json()
        assert [z["zustand"] for z in bericht["dateien"]] == ["aktualisiert"], bericht
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert metadata["illustrationen"][0]["svg"] == orbital


class TestVorschau:
    """Was der Dialog anzeigt (AP4): eine Zeile je Datei, nicht nur Summen."""

    @pytest.mark.asyncio
    async def test_eine_zeile_je_datei(self, test_client, fach, fachschaft_headers):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[
                _datei("Alpha.md", _md("Alpha")),
                _datei("Beta.md", _md("Beta")),
            ],
            headers=fachschaft_headers,
        )
        zeilen = antwort.json()["dateien"]
        assert [z["datei"] for z in zeilen] == ["Alpha", "Beta"]
        assert {z["zustand"] for z in zeilen} == {"neu"}
        assert [z["titel"] for z in zeilen] == ["Alpha", "Beta"]

    @pytest.mark.asyncio
    async def test_die_summen_sind_die_summe_der_zeilen(
        self, test_client, fach, fachschaft_headers
    ):
        """⚠️ Zwei Darstellungen desselben Laufs. Liefen sie auseinander, zeigte der
        Dialog eine Tabelle, die nicht zur Zeile darüber passt — und niemand wüsste,
        welcher der beiden zu glauben ist."""
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[
                _datei("Alpha.md", _md("Alpha")),
                _datei("Beta.md", _md("Beta")),
            ],
            headers=fachschaft_headers,
        )
        b = antwort.json()
        zustaende = [z["zustand"] for z in b["dateien"]]
        assert zustaende.count("neu") == b["neu"] == 1
        assert zustaende.count("unveraendert") == b["unveraendert"] == 1

    @pytest.mark.asyncio
    async def test_uebergangene_dateien_fehlen_nicht(
        self, test_client, fach, fachschaft_headers
    ):
        """Eine Datei, die nicht geschrieben wird, muss trotzdem in der Tabelle stehen.

        Sonst zeigte der Dialog weniger Dateien an, als hochgeladen wurden — der
        verwirrendste aller Zustände.
        """
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"]},
            files=[
                _datei("Alpha.md", _md("Alpha")),
                _datei("Fremd.md", _md("Fremd", fach="Anderesfach")),
            ],
            headers=fachschaft_headers,
        )
        zeilen = {z["datei"]: z["zustand"] for z in antwort.json()["dateien"]}
        assert zeilen == {"Alpha": "neu", "Fremd": "uebergangen"}

    @pytest.mark.asyncio
    async def test_knoten_id_fuer_den_sprung_in_die_sammlung(
        self, test_client, fach, fachschaft_headers
    ):
        """Nach dem Import verlinkt der Dialog auf das Eingespielte — dafür die ID."""
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        (zeile,) = antwort.json()["dateien"]
        assert zeile["node_id"]

    @pytest.mark.asyncio
    async def test_pruefstatus_wird_gemeldet_nicht_importiert(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha", zusatz="pruefstatus: entwurf\n"))],
            headers=fachschaft_headers,
        )
        (zeile,) = antwort.json()["dateien"]
        assert zeile["pruefstatus"] == "entwurf" and zeile["entwurf"] is True
        (_, metadata), = _knoten(sync_conn, fach["id"])
        assert "pruefstatus" not in metadata, "Import ist Freigabe — kein Status am Knoten"


class TestUeberschreibenJeZeile:
    """Die Wahl „behalten"/„überschreiben" je Knoten (AP4).

    ⚠️ **Der Unterschied zu `--ueberschreiben`** des Skripts: Das gilt für alle. Im
    Dialog fällt die Entscheidung je Zeile verschieden aus — an einem Knoten hat jemand
    gearbeitet, am nächsten nicht.
    """

    async def _handarbeit(self, test_client, fach, headers, sync_conn):
        """Zwei Knoten einspielen und beide in der Oberfläche verändern."""
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha")), _datei("Beta.md", _md("Beta"))],
            headers=headers,
        )
        with sync_conn.cursor() as cur:
            cur.execute(
                "UPDATE context_nodes SET content = 'In der Oberfläche geändert.'"
                " WHERE subject_id = %s", (fach["id"],)
            )
        sync_conn.commit()

    @pytest.mark.asyncio
    async def test_ohne_auswahl_bleibt_alles_stehen(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        await self._handarbeit(test_client, fach, fachschaft_headers, sync_conn)
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha")), _datei("Beta.md", _md("Beta"))],
            headers=fachschaft_headers,
        )
        assert sorted(antwort.json()["uebersprungen"]) == ["Alpha", "Beta"]
        inhalte = {
            t: m for t, m in
            [(z[0], z[1]) for z in _knoten(sync_conn, fach["id"])]
        }
        assert set(inhalte) == {"Alpha", "Beta"}

    @pytest.mark.asyncio
    async def test_nur_die_genannte_zeile_wird_ersetzt(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        await self._handarbeit(test_client, fach, fachschaft_headers, sync_conn)
        antwort = await test_client.post(
            PFAD,
            params={
                "fach": fach["slug"], "probelauf": "false", "ueberschreiben": ["Alpha"],
            },
            files=[_datei("Alpha.md", _md("Alpha")), _datei("Beta.md", _md("Beta"))],
            headers=fachschaft_headers,
        )
        zeilen = {z["datei"]: z["zustand"] for z in antwort.json()["dateien"]}
        assert zeilen == {"Alpha": "aktualisiert", "Beta": "uebersprungen"}

        with sync_conn.cursor() as cur:
            cur.execute(
                "SELECT title, content FROM context_nodes WHERE subject_id = %s"
                " ORDER BY title", (fach["id"],)
            )
            inhalte = dict(cur.fetchall())
        assert "Ein Text über Alpha." in inhalte["Alpha"]
        assert inhalte["Beta"] == "In der Oberfläche geändert.", (
            "Beta stand nicht in der Auswahl und muss unangetastet bleiben"
        )


class TestDrossel:
    """Dass die Drossel überhaupt hängt — sonst nimmt sie ihr eigener Test heraus.

    ⚠️ Die übrigen Fälle setzen den Zähler vor jedem Lauf zurück (`ohne_drossel`),
    weil sie sonst an einer Grenze scheiterten, die sie nicht prüfen wollen. Damit
    prüft **keiner** von ihnen mehr, dass es sie gibt. Diese Klasse tut es — an der
    Abhängigkeit selbst, ohne einundzwanzig echte Importläufe.
    """

    @pytest.mark.asyncio
    async def test_nach_dem_limit_kommt_429(self, jwt_service):
        from fastapi import HTTPException

        from app.auth.jwt import JwtPayload
        from app.context.router import _fachbegriffe_nutzer
        from app.ratelimit.config import resolve

        nutzer = JwtPayload(
            sub="drossel-probe", roles=["teacher"], grade=None,
            jti="00000000-0000-4000-8000-000000000000", iat=0, exp=2**31,
        )
        limit, _ = resolve("fachbegriffe_import", nutzer.roles)
        for _ in range(limit):
            assert await _fachbegriffe_nutzer(nutzer) is nutzer
        with pytest.raises(HTTPException) as fehler:
            await _fachbegriffe_nutzer(nutzer)
        assert fehler.value.status_code == 429


EXPORT = "/context/fachbegriffe/export"


class TestExport:
    """Der Rückweg über die API (AP5, D1).

    Die Mechanik des Formats prüft `test_fachbegriffe_rundreise.py`; hier geht es um
    die Verdrahtung — Rechte, Kopfzeilen und der Kreis **durch beide Endpunkte**.
    """

    @pytest.mark.asyncio
    async def test_zip_enthaelt_die_eingespielten_dateien(
        self, test_client, fach, fachschaft_headers
    ):
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        antwort = await test_client.get(
            EXPORT, params={"fach": fach["slug"]}, headers=fachschaft_headers
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.headers["content-type"] == "application/zip"
        assert ".zip" in antwort.headers["content-disposition"]
        with zipfile.ZipFile(io.BytesIO(antwort.content)) as archiv:
            # Der Beipackzettel liegt immer bei — er sagt, was der Export **nicht**
            # mitbringen kann, und das hängt nicht vom einzelnen Lauf ab.
            assert sorted(archiv.namelist()) == ["Alpha.md", "_Export-Hinweise.txt"]
            assert "titel: Alpha" in archiv.read("Alpha.md").decode("utf-8")

    @pytest.mark.asyncio
    async def test_rundreise_durch_beide_endpunkte(
        self, test_client, fach, fachschaft_headers
    ):
        """⚠️ **Die Probe, die beide Richtungen zusammenhält.** Der Kreis im
        Modultest läuft am HTTP-Weg vorbei: Dort entsteht das Zip erst, wird wieder
        entpackt, der Wurzelordner abgeschnitten, die SVG geprüft. Jeder dieser
        Schritte könnte das Bündel verändern, ohne dass es auffiele."""
        zusatz = (
            "illustrationen:\n  - datei: _Abb/schema.svg\n"
            '    beschreibung: "Ein Kreis."\n'
        )
        hin = _zip({
            "Alpha.md": _md("Alpha", zusatz=zusatz),
            "_Abb/schema.svg": SVG.encode("utf-8"),
        })
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("pilot.zip", hin)], headers=fachschaft_headers,
        )
        heraus = await test_client.get(
            EXPORT, params={"fach": fach["slug"]}, headers=fachschaft_headers
        )
        assert heraus.status_code == 200
        with zipfile.ZipFile(io.BytesIO(heraus.content)) as archiv:
            assert sorted(archiv.namelist()) == [
                "Alpha.md", "_Abb/schema.svg", "_Export-Hinweise.txt",
            ]

        zurueck = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("zurueck.zip", heraus.content)], headers=fachschaft_headers,
        )
        bericht = zurueck.json()
        assert (bericht["neu"], bericht["aktualisiert"]) == (0, 0), bericht
        assert bericht["unveraendert"] == 1
        assert bericht["kanten_geaendert"] == 0

    @pytest.mark.asyncio
    async def test_schuelerin_nicht(self, test_client, fach, schuelerin_headers):
        antwort = await test_client.get(
            EXPORT, params={"fach": fach["slug"]}, headers=schuelerin_headers
        )
        assert antwort.status_code == 403

    @pytest.mark.asyncio
    async def test_fremde_lehrkraft_nicht(self, test_client, fach, fremde_headers):
        antwort = await test_client.get(
            EXPORT, params={"fach": fach["slug"]}, headers=fremde_headers
        )
        assert antwort.status_code == 403

    @pytest.mark.asyncio
    async def test_unbekanntes_fach(self, test_client, fachschaft_headers):
        antwort = await test_client.get(
            EXPORT, params={"fach": "gibtesnicht"}, headers=fachschaft_headers
        )
        assert antwort.status_code == 404


class TestEinzelneDateiHerunterladen:
    """„Als Markdown herunterladen" in der Detailansicht."""

    async def _alpha_id(self, test_client, fach, headers, sync_conn):
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=headers,
        )
        with sync_conn.cursor() as cur:
            cur.execute(
                "SELECT id FROM context_nodes WHERE subject_id = %s AND title = 'Alpha'",
                (fach["id"],),
            )
            return cur.fetchone()[0]

    @pytest.mark.asyncio
    async def test_liefert_markdown_mit_dateinamen(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        node_id = await self._alpha_id(test_client, fach, fachschaft_headers, sync_conn)
        antwort = await test_client.get(
            f"/context/nodes/{node_id}/markdown", headers=fachschaft_headers
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.headers["content-type"].startswith("text/markdown")
        assert 'filename="Alpha.md"' in antwort.headers["content-disposition"]
        assert antwort.text.startswith("---\n")

    @pytest.mark.asyncio
    async def test_auch_fuer_eine_fremde_lehrkraft(
        self, test_client, fach, fachschaft_headers, fremde_headers, sync_conn
    ):
        """Eine einzelne Datei ist kein Massenvorgang: Der Inhalt steht in der
        Detailansicht ohnehin offen, geprüft wird nur das Leserecht."""
        node_id = await self._alpha_id(test_client, fach, fachschaft_headers, sync_conn)
        antwort = await test_client.get(
            f"/context/nodes/{node_id}/markdown", headers=fremde_headers
        )
        assert antwort.status_code == 200

    @pytest.mark.asyncio
    async def test_fremder_knotentyp_ist_kein_download(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        with sync_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO context_nodes (category, content_type, title, content,"
                " subject_id, status, read_scope, write_scope, metadata)"
                " VALUES ('knowledge','methode','Eine Methode','x',%s,'active',"
                "'school','school','{}') RETURNING id",
                (fach["id"],),
            )
            node_id = cur.fetchone()[0]
        sync_conn.commit()
        antwort = await test_client.get(
            f"/context/nodes/{node_id}/markdown", headers=fachschaft_headers
        )
        assert antwort.status_code == 404


class TestVorlageHerunterladen:
    """„Vorlage herunterladen" im Dialog (AP6)."""

    @pytest.mark.asyncio
    async def test_liefert_ein_zip_mit_mustern(self, test_client, fachschaft_headers):
        antwort = await test_client.get(
            "/context/fachbegriffe/vorlage", headers=fachschaft_headers
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.headers["content-type"] == "application/zip"
        with zipfile.ZipFile(io.BytesIO(antwort.content)) as archiv:
            namen = archiv.namelist()
        assert "_Format.md" in namen
        assert any(n.startswith("_Abb/") for n in namen)
        assert len([n for n in namen if n.endswith(".md") and not n.startswith("_")]) == 3

    @pytest.mark.asyncio
    async def test_ohne_fach_und_ohne_fachschaft(
        self, test_client, fremde_headers
    ):
        """Eine Anleitung, kein Bestand: Wer wissen will, wie das Format aussieht, soll
        es ansehen können, bevor er irgendwo Mitglied ist."""
        antwort = await test_client.get(
            "/context/fachbegriffe/vorlage", headers=fremde_headers
        )
        assert antwort.status_code == 200

    @pytest.mark.asyncio
    async def test_nicht_fuer_schuelerinnen(self, test_client, schuelerin_headers):
        antwort = await test_client.get(
            "/context/fachbegriffe/vorlage", headers=schuelerin_headers
        )
        assert antwort.status_code == 403

    @pytest.mark.asyncio
    async def test_die_vorlage_laesst_sich_sofort_einspielen(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        """⚠️ **Der Weg, den eine Lehrkraft wirklich geht:** herunterladen, hochladen,
        ansehen. Dass die Dateien zum Format passen, prüft der Modultest; dass sie
        **durch beide Endpunkte** kommen, nur dieser."""
        vorlage = await test_client.get(
            "/context/fachbegriffe/vorlage", headers=fachschaft_headers
        )
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("fachbegriffe-vorlage.zip", vorlage.content)],
            headers=fachschaft_headers,
        )
        bericht = antwort.json()
        assert bericht["neu"] == 3, bericht
        assert bericht["warnungen"] == [], bericht["warnungen"]
        assert len(_knoten(sync_conn, fach["id"])) == 3


# ── Vektoren gleich nach dem Import (0.14, F7) ───────────────────────────────

def _vektor_da(sync_conn, subject_id) -> dict[str, bool]:
    with sync_conn.cursor() as cur:
        cur.execute("SELECT title, embedding IS NOT NULL FROM context_nodes"
                    " WHERE subject_id = %s", (subject_id,))
        return dict(cur.fetchall())


class TestVektorenSofort:
    """Bis 0.14 setzte der Import `embedding = NULL` und wartete auf den Backfill um
    3:15 Uhr. Wer importierte und gleich fragte, fand die neuen Begriffe in der
    Vorab-Suche nicht."""

    @pytest.mark.asyncio
    async def test_neuer_begriff_hat_nach_dem_import_einen_vektor(
        self, test_client, fach, fachschaft_headers, sync_conn, einbettung
    ):
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        assert _vektor_da(sync_conn, fach["id"]) == {"Alpha": True}
        texte = [t for aufruf in einbettung.await_args_list for t in aufruf.args[0]]
        assert any("Ein Text über Alpha" in t for t in texte)

    @pytest.mark.asyncio
    async def test_geaenderter_begriff_bekommt_einen_neuen(
        self, test_client, fach, fachschaft_headers, sync_conn, einbettung
    ):
        for zusatz in ("", "ab_klasse: 9\n"):
            await test_client.post(
                PFAD, params={"fach": fach["slug"], "probelauf": "false"},
                files=[_datei("Alpha.md", _md("Alpha", zusatz=zusatz))],
                headers=fachschaft_headers,
            )
        assert _vektor_da(sync_conn, fach["id"]) == {"Alpha": True}
        assert einbettung.await_count == 2

    @pytest.mark.asyncio
    async def test_probelauf_bettet_nicht_ein(
        self, test_client, fach, fachschaft_headers, einbettung
    ):
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "true"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        einbettung.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unveraenderter_lauf_bettet_nichts_neu_ein(
        self, test_client, fach, fachschaft_headers, einbettung
    ):
        for _ in range(2):
            await test_client.post(
                PFAD, params={"fach": fach["slug"], "probelauf": "false"},
                files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
            )
        assert einbettung.await_count == 1, "der zweite Lauf hat einen Vektor neu berechnet"

    @pytest.mark.asyncio
    async def test_scheitert_das_einbetten_bleibt_der_import_stehen(
        self, test_client, fach, fachschaft_headers, sync_conn, einbettung
    ):
        """Proxy weg: Der Import ist gespeichert, der Knoten wartet auf die Nacht."""
        einbettung.side_effect = RuntimeError("Proxy nicht erreichbar")
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["neu"] == 1
        assert _vektor_da(sync_conn, fach["id"]) == {"Alpha": False}

    @pytest.mark.asyncio
    async def test_probelauf_beruehrt_auch_bestehende_knoten_ohne_vektor_nicht(
        self, test_client, fach, fachschaft_headers, sync_conn, einbettung
    ):
        """⚠️ Die Zusage „ein Probelauf schreibt nichts" gilt auch für Vektoren — ein
        Knoten, dem seit früher einer fehlt, bleibt im Probelauf ohne."""
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        with sync_conn.cursor() as cur:
            cur.execute("UPDATE context_nodes SET embedding = NULL WHERE subject_id = %s",
                        (fach["id"],))
        sync_conn.commit()
        vorher = einbettung.await_count
        await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "true"},
            files=[_datei("Alpha.md", _md("Alpha"))], headers=fachschaft_headers,
        )
        assert einbettung.await_count == vorher
        assert _vektor_da(sync_conn, fach["id"]) == {"Alpha": False}


# ── Umlaute im Dateinamen (0.14, Schritt 8) ──────────────────────────────────

def _kennungen(sync_conn, subject_id) -> dict[str, tuple[str, str]]:
    with sync_conn.cursor() as cur:
        cur.execute("SELECT title, metadata->>'seed_id', metadata->>'seed_quelle'"
                    " FROM context_nodes WHERE subject_id = %s", (subject_id,))
        return {t: (k, q) for t, k, q in cur.fetchall()}


class TestUmlauteImDateinamen:
    """Bis 0.14 ergab eine Zip ohne UTF-8-Kennzeichen eine andere Kennung als dieselbe
    Datei einzeln — und der nächste Import einen zweiten Knoten."""

    @pytest.mark.asyncio
    async def test_zip_ohne_kennzeichen_ergibt_die_richtige_kennung(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        import unicodedata
        from tests.unit.test_fachbegriffe_namen import zip_ohne_kennzeichen

        nfd = unicodedata.normalize("NFD", "Hückel-Regel")
        archiv = zip_ohne_kennzeichen(f"{nfd}.md".encode("utf-8"), _md("Hückel-Regel"))
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei("vault.zip", archiv)], headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        kennung, quelle = _kennungen(sync_conn, fach["id"])["Hückel-Regel"]
        assert kennung.endswith("-hueckel-regel")
        assert quelle == "Hückel-Regel" and unicodedata.is_normalized("NFC", quelle)

        # Dieselbe Datei einzeln, mit zerlegtem Namen: derselbe Knoten, kein zweiter.
        einzeln = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[_datei(f"{nfd}.md", _md("Hückel-Regel"))], headers=fachschaft_headers,
        )
        assert einzeln.json()["neu"] == 0, einzeln.json()
        assert len(_kennungen(sync_conn, fach["id"])) == 1

    @pytest.mark.asyncio
    async def test_wikilink_mit_zerlegtem_ziel_findet_die_datei(
        self, test_client, fach, fachschaft_headers, sync_conn
    ):
        import unicodedata

        ziel_nfd = unicodedata.normalize("NFD", "Hückel-Regel")
        antwort = await test_client.post(
            PFAD, params={"fach": fach["slug"], "probelauf": "false"},
            files=[
                _datei("Hückel-Regel.md", _md("Hückel-Regel")),
                _datei("Aromaten.md", _md("Aromaten", zusatz=f'oberbegriff: "[[{ziel_nfd}]]"\n')),
            ],
            headers=fachschaft_headers,
        )
        assert antwort.status_code == 200, antwort.text
        assert antwort.json()["offene_ziele"] == [], "das Ziel wurde nicht gefunden"
        with sync_conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) FROM context_edges e"
                " JOIN context_nodes v ON v.id = e.from_node_id"
                " JOIN context_nodes n ON n.id = e.to_node_id"
                " WHERE v.title = 'Aromaten' AND n.title = 'Hückel-Regel'"
                " AND v.subject_id = %s", (fach["id"],))
            assert cur.fetchone()[0] == 1
