"""Export → Import auf demselben Bestand = nichts ändert sich (Paket 10, AP5).

⚠️ **Der Wächter des ganzen Pakets.** Zwei Richtungen sprechen dasselbe Format, und das
lässt sich nicht durch Lesen prüfen: Jede Kleinigkeit — eine Überschriftsebene, eine
Liste, die im Frontmatter statt im Text steht, eine Abbildung mit oder ohne Inhalt —
fällt erst auf, wenn man einmal im Kreis geht. Geht der Kreis nicht auf, meldet jeder
zweite Import „aktualisiert" für Einträge, an denen niemand etwas geändert hat, und der
Bericht wird unlesbar.

Gemessen wird am **Bestand**, nicht am Text: Dateien dürfen sich unterscheiden (der
Export schreibt den Stand des Speichers, nicht die Datei von vorgestern). Gleich bleiben
müssen Knoten, Kanten und Aliase.
"""
import uuid

import pytest
import sqlalchemy as sa

from app.db.models import ContextNode, Group, NodeAlias, Subject

pytestmark = pytest.mark.asyncio

from pathlib import Path

VAULT = Path(__file__).resolve().parents[1] / "fixtures" / "fachbegriffe"


def _buendel() -> dict[str, bytes]:
    dateien = {p.name: p.read_bytes() for p in sorted(VAULT.glob("*.md"))}
    dateien |= {
        f"_Abb/{p.name}": p.read_bytes() for p in sorted((VAULT / "_Abb").glob("*"))
    }
    return dateien


@pytest.fixture(scope="module")
def seed():
    from app.context import fachbegriffe_import
    return fachbegriffe_import


@pytest.fixture(scope="module")
def export():
    from app.context import fachbegriffe_export
    return fachbegriffe_export


@pytest.fixture
async def testfach(db_session):
    fach = Subject(
        slug=f"rundfach-{uuid.uuid4().hex[:8]}", name="Testfach", fach_code="RF"
    )
    db_session.add(fach)
    await db_session.flush()
    kennung = uuid.uuid4().hex[:8]
    db_session.add(Group(
        name="FS Testfach", slug=f"fs-rund-{kennung}", type="subject_department",
        subject_id=fach.id, sso_group_id=f"fs-rund-{kennung}",
    ))
    for nr, titel in (
        ("3.2.1.1(1)", "3.2.1.1(1) die erste Kompetenz"),
        ("3.2.1.1(10)", "3.2.1.1(10) die zehnte Kompetenz"),
    ):
        db_session.add(ContextNode(
            category="knowledge", content_type="ik_kompetenz", title=titel, content="x",
            subject_id=fach.id, bp_version="2016.V2", status="active",
            read_scope="school", write_scope="school", metadata_={"kompetenz_nr": nr},
        ))
    db_session.add(ContextNode(
        category="knowledge", content_type="leitidee", title="3.2.1.1 Die Leitidee",
        content="x", subject_id=fach.id, bp_version="2016.V2", status="active",
        read_scope="school", write_scope="school", metadata_={"nr": "3.2.1.1"},
    ))
    await db_session.flush()
    return fach


async def _bestand(db_session, fach):
    """Knoten, Kanten und Aliase des Fachs — der Vergleichsgegenstand."""
    knoten = (await db_session.execute(
        sa.select(ContextNode.id, ContextNode.title, ContextNode.content,
                  ContextNode.metadata_)
        .where(ContextNode.subject_id == fach.id,
               ContextNode.content_type.in_(("begriff", "stoffsteckbrief")))
        .order_by(ContextNode.title)
    )).all()
    ids = [z[0] for z in knoten]
    kanten = (await db_session.execute(
        sa.select(sa.func.count()).select_from(sa.text("context_edges"))
        .where(sa.text("from_node_id = ANY(:ids)")).params(ids=ids)
    )).scalar_one() if ids else 0
    aliase = (await db_session.execute(
        sa.select(sa.func.count()).select_from(NodeAlias)
        .where(NodeAlias.node_id.in_(ids))
    )).scalar_one() if ids else 0
    return {
        "knoten": {t: (c, m) for _i, t, c, m in knoten},
        "kanten": kanten,
        "aliase": aliase,
    }


async def _kanten(db_session, fach):
    """(Von-Titel, Relation, Nach-Titel, Metadata) — ohne IDs, damit vergleichbar."""
    von = sa.orm.aliased(ContextNode)
    nach = sa.orm.aliased(ContextNode)
    from app.db.models import ContextEdge

    zeilen = (await db_session.execute(
        sa.select(von.title, ContextEdge.relation, nach.title, ContextEdge.metadata_)
        .join(von, von.id == ContextEdge.from_node_id)
        .join(nach, nach.id == ContextEdge.to_node_id)
        .where(von.subject_id == fach.id,
               von.content_type.in_(("begriff", "stoffsteckbrief")))
        .order_by(von.title, ContextEdge.relation, nach.title)
    )).all()
    return [(a, r, b, dict(m or {})) for a, r, b, m in zeilen]


async def _hin_und_zurueck(seed, export, db_session, fach):
    """Fixtures importieren, exportieren, das Ergebnis wieder importieren."""
    erst = await seed.importiere(db_session, _buendel(), nur_fach=fach)
    await db_session.flush()
    vorher = await _bestand(db_session, fach)

    dateien, exportbilanz = await export.exportiere(db_session, fach)
    buendel = {d.pfad: d.inhalt for d in dateien}

    zweit = await seed.importiere(db_session, buendel, nur_fach=fach)
    await db_session.flush()
    nachher = await _bestand(db_session, fach)
    return erst, exportbilanz, zweit, vorher, nachher


class TestRundreise:
    async def test_der_zweite_import_aendert_nichts(
        self, seed, export, db_session, testfach
    ):
        """Die Zusage aus dem Plan, wörtlich: „0 neu, 0 aktualisiert"."""
        erst, _, zweit, _, _ = await _hin_und_zurueck(seed, export, db_session, testfach)
        assert erst.neu > 0, "ohne ersten Import belegt der Kreis nichts"
        assert (zweit.neu, zweit.aktualisiert) == (0, 0), (
            f"Export→Import ist nicht neutral: {zweit.warnungen}"
        )
        assert zweit.unveraendert == erst.neu

    async def test_auch_die_kanten_bleiben(self, seed, export, db_session, testfach):
        """⚠️ Nicht im Plan, aber derselbe Gedanke: Ein Rundgang, der die Knoten
        stehen lässt und die Kanten neu setzt, ist keiner. Kanten stecken nicht im
        Stand-Hash — ohne diese Zeile fiele ihr Verlust nicht auf."""
        _, _, zweit, vorher, nachher = await _hin_und_zurueck(
            seed, export, db_session, testfach
        )
        assert nachher["kanten"] == vorher["kanten"]
        assert zweit.kanten_geaendert == 0

    async def test_titel_text_und_metadaten_unveraendert(
        self, seed, export, db_session, testfach
    ):
        _, _, _, vorher, nachher = await _hin_und_zurueck(
            seed, export, db_session, testfach
        )
        assert set(nachher["knoten"]) == set(vorher["knoten"])
        for titel, (content, metadata) in vorher["knoten"].items():
            neu_content, neu_metadata = nachher["knoten"][titel]
            assert neu_content == content, titel
            assert neu_metadata == metadata, titel

    async def test_aliase_bleiben(self, seed, export, db_session, testfach):
        _, _, _, vorher, nachher = await _hin_und_zurueck(
            seed, export, db_session, testfach
        )
        assert vorher["aliase"] > 0 and nachher["aliase"] == vorher["aliase"]

    async def test_die_selbstpruefung_meldet_nichts(
        self, seed, export, db_session, testfach
    ):
        """Jede Datei liest sich selbst zurück. Bei den Fixtures muss das glattgehen —
        sonst stünde im Bündel ein Beipackzettel, den niemand erwartet."""
        _, exportbilanz, _, _, _ = await _hin_und_zurueck(
            seed, export, db_session, testfach
        )
        assert exportbilanz.warnungen == []
        assert exportbilanz.knoten > 0 and exportbilanz.abbildungen > 0


# ── Ein Bündel, in dem die Ziele wirklich da sind ────────────────────────────

ALPHA = """---
knotentyp: begriff
titel: Alpha
fach: Testfach
oberbegriff: ["[[Ober]]"]
verwandt: ["[[Beta]]"]
voraussetzung: ["[[Ober]]"]
vertieft_in: ["[[Beta]]"]
---

## Definition

Alpha ist ein erfundener Begriff.

## Abgrenzung

- [[Beta]] – ist etwas anderes, trotz der Vertiefung.
- [[Ober]] und [[Beta]] – gelten beide gemeinsam.
"""

BETA = """---
knotentyp: stoffsteckbrief
titel: Beta
fach: Testfach
formel: "\\\\ce{H2O}"
stoffklasse: "[[Ober]]"
---

## Definition

Beta ist ein erfundener Stoff.
"""

OBER = """---
knotentyp: begriff
titel: Ober
fach: Testfach
---

## Definition

Ober ist der Oberbegriff.
"""

MIT_KANTEN = {
    "Alpha.md": ALPHA.encode("utf-8"),
    "Beta.md": BETA.encode("utf-8"),
    "Ober.md": OBER.encode("utf-8"),
}


class TestRundreiseMitKanten:
    """⚠️ **Die Fixtures allein belegen die Kanten nicht.**

    In `tests/fixtures/fachbegriffe/` zeigen fast alle Wikilinks auf Ziele, die es im
    Bündel nicht gibt — Absicht, dort geht es um offene Verweise. Übrig bleiben die
    Fundstellen, und genau deshalb blieb die Gegenprobe „Abgrenzungen weglassen" beim
    ersten Anlauf **grün**: Es gab keine. Hier stehen drei Dateien, die sich
    gegenseitig kennen.
    """

    async def _kreis(self, seed, export, db_session, fach):
        erst = await seed.importiere(db_session, MIT_KANTEN, nur_fach=fach)
        await db_session.flush()
        vorher = await _kanten(db_session, fach)
        dateien, bilanz = await export.exportiere(db_session, fach)
        zweit = await seed.importiere(
            db_session, {d.pfad: d.inhalt for d in dateien}, nur_fach=fach
        )
        await db_session.flush()
        return erst, bilanz, zweit, vorher, await _kanten(db_session, fach), dateien

    async def test_alle_kantenarten_ueberstehen_den_kreis(
        self, seed, export, db_session, testfach
    ):
        erst, bilanz, zweit, vorher, nachher, _ = await self._kreis(
            seed, export, db_session, testfach
        )
        assert erst.neu == 3 and erst.kanten > 0
        assert (zweit.neu, zweit.aktualisiert) == (0, 0), zweit.warnungen
        assert zweit.kanten_geaendert == 0
        assert nachher == vorher, "die Kanten haben sich verändert"
        assert bilanz.warnungen == []

    async def test_die_doppelte_lesart_bleibt_erhalten(
        self, seed, export, db_session, testfach
    ):
        """⚠️ Der Fall, für den `vereinige()` `arten` überhaupt führt.

        „Beta" ist von „Alpha" aus **Vertiefung und Abgrenzung** zugleich; die Datenbank
        kann dazwischen nur **eine** `related_to`-Kante halten. Schriebe der Export nur
        die Gewinner-Art zurück, verlöre jeder Rundgang die andere — lautlos, denn am
        Knoten ändert sich dabei nichts.
        """
        _, _, _, vorher, nachher, dateien = await self._kreis(
            seed, export, db_session, testfach
        )
        alpha = next(d for d in dateien if d.pfad == "Alpha.md").inhalt.decode()
        assert "vertieft_in" in alpha and "## Abgrenzung" in alpha
        beta_kante = [
            k for k in nachher if k[0] == "Alpha" and k[2] == "Beta"
        ]
        assert beta_kante, nachher
        arten = beta_kante[0][3].get("arten")
        assert arten == ["abgrenzung", "vertiefung"], beta_kante[0][3]
        assert nachher == vorher

    async def test_der_steckbrief_bekommt_stoffklasse_nicht_oberbegriff(
        self, seed, export, db_session, testfach
    ):
        """Beide Felder ergeben dieselbe Relation — die Datenbank sähe keinen
        Unterschied. Die Fachschaft schon: `_Format.md` kennt `stoffklasse` nur beim
        Steckbrief, und in ihrem Vault soll das Wort stehen, das sie benutzt."""
        _, _, _, _, _, dateien = await self._kreis(seed, export, db_session, testfach)
        beta = next(d for d in dateien if d.pfad == "Beta.md").inhalt.decode()
        assert "stoffklasse:" in beta and "oberbegriff:" not in beta

    async def test_abbildungen_stehen_als_einbettung_in_der_datei(
        self, seed, export, db_session, testfach
    ):
        """⚠️ Für den Rundgang wäre das gleichgültig — `{{abbildung:…}}` liest sich
        genauso wieder ein. Der Grund ist der Mensch: Wer die Datei in Obsidian öffnet,
        soll das Bild sehen und keinen Platzhalter. Die Gegenprobe zu dieser Zeile blieb
        deshalb grün, bis es diesen Fall gab."""
        await seed.importiere(db_session, _buendel(), nur_fach=testfach)
        await db_session.flush()
        dateien, _ = await export.exportiere(db_session, testfach)
        fiktivum = next(d for d in dateien if d.pfad == "Fiktivum.md").inhalt.decode()
        assert "![[schema.svg]]" in fiktivum
        assert "{{abbildung:" not in fiktivum


class TestSelbstpruefung:
    """Was der Export nicht abbilden kann, sagt er — statt es zu verschweigen."""

    async def test_ueberschrift_im_text_wird_gemeldet(
        self, export, db_session, testfach
    ):
        """Ein im Editor angelegter Knoten kann alles im Text stehen haben — auch eine
        `##`-Überschrift. Die zerlegte der Import beim Wiedereinlesen in einen eigenen
        Abschnitt, und der Text wäre ein anderer."""
        db_session.add(ContextNode(
            category="knowledge", content_type="begriff", title="Handarbeit",
            content="Ein Satz.\n\n## Eigener Abschnitt\n\nUnd noch einer.",
            subject_id=testfach.id, status="active",
            read_scope="school", write_scope="school", metadata_={},
        ))
        await db_session.flush()
        _, bilanz = await export.exportiere(db_session, testfach)
        assert any("als geändert" in w for w in bilanz.warnungen), bilanz.warnungen

    async def test_hinweise_landen_im_buendel_und_stoeren_den_import_nicht(
        self, seed, export, db_session, testfach
    ):
        """Der Beipackzettel trägt einen Unterstrich — `lies_buendel` übergeht ihn."""
        db_session.add(ContextNode(
            category="knowledge", content_type="begriff", title="Handarbeit",
            content="Ein Satz.\n\n## Eigener Abschnitt\n\nUnd noch einer.",
            subject_id=testfach.id, status="active",
            read_scope="school", write_scope="school", metadata_={},
        ))
        await db_session.flush()
        dateien, bilanz = await export.exportiere(db_session, testfach)
        hinweis = export.hinweisdatei(bilanz)
        assert hinweis is not None and hinweis.pfad.startswith("_")

        bilanz2 = seed.Bilanz()
        gelesen = seed.lies_buendel({hinweis.pfad: hinweis.inhalt}, bilanz2)
        assert gelesen == [] and bilanz2.warnungen == []

    async def test_der_beipackzettel_liegt_immer_bei(
        self, seed, export, db_session, testfach
    ):
        """⚠️ Auch ohne Befund. Was der Export nicht mitbringen **kann**, hängt nicht
        davon ab, ob diesmal etwas aufgefallen ist — und genau das muss jemand wissen,
        bevor er damit seinen Vault überschreibt. Gemessen am Chemie-Pilot fehlen 251
        Verweise auf Begriffe, die es noch nicht gibt."""
        await seed.importiere(db_session, MIT_KANTEN, nur_fach=testfach)
        await db_session.flush()
        _, bilanz = await export.exportiere(db_session, testfach)
        assert bilanz.warnungen == []
        hinweis = export.hinweisdatei(bilanz)
        text = hinweis.inhalt.decode("utf-8")
        assert "noch nicht gibt" in text and "Arbeitsliste" in text


class TestEinzelnerKnoten:
    async def test_nur_ein_knoten_aber_mit_seinen_kanten(
        self, seed, export, db_session, testfach
    ):
        """Die Detailansicht lädt eine Datei herunter — die Wikilinks darin müssen
        trotzdem auf die Dateinamen der **anderen** zeigen."""
        await seed.importiere(db_session, MIT_KANTEN, nur_fach=testfach)
        await db_session.flush()
        alpha_id = (await db_session.execute(
            sa.select(ContextNode.id).where(
                ContextNode.subject_id == testfach.id, ContextNode.title == "Alpha"
            )
        )).scalar_one()

        dateien, _ = await export.exportiere(db_session, testfach, nur=alpha_id)
        assert [d.pfad for d in dateien] == ["Alpha.md"]
        assert "[[Ober]]" in dateien[0].inhalt.decode()
