"""Die Vorab-Suche als Grundschicht jedes Chats (Paket 9, N11).

⚠️ **Hier landet Kontext im Prompt, ohne dass jemand darum gebeten hat.** Deshalb ist
jede Regel dieses Wegs eng und einzeln geprüft: die Ähnlichkeitsschwelle, die
Beschränkung auf Knotenarten, die Schüler:innen im Unterricht in die Hand bekommen, und
der Anker eines Assistenten, der zusätzlich einschränkt. Ein Fehler hier ist teurer als
in der Werkzeugsuche: Dort sieht das Modell einen unpassenden Treffer als Antwort auf
seine eigene Anfrage, hier als Wissen der Schule.

**Die Vektoren stehen von Hand**, nicht aus dem Einbettungsdienst: Nur so ist die
Distanz eine bekannte Zahl und die Schwelle prüfbar. Der Einheitsvektor entlang einer
Achse hat zu jedem anderen eine Kosinus-Distanz, die sich aus dem Winkel ergibt.
"""
import math
import uuid

import pytest

from app.config import settings
from app.context.search import VORAB_SCHWELLE, Suchprofil, vorab
from app.db.models import ContextNode, Subject

pytestmark = pytest.mark.asyncio

DIM = settings.embedding_dimensions


def _vektor(winkel: float) -> list[float]:
    """Einheitsvektor in der 0-1-Ebene — Kosinus-Distanz zur 0-Achse ist ``1-cos(winkel)``."""
    v = [0.0] * DIM
    v[0], v[1] = math.cos(winkel), math.sin(winkel)
    return v


#: Anfragevektor: die 0-Achse.
FRAGE = _vektor(0.0)


def _fuer_distanz(d: float) -> list[float]:
    """Ein Knotenvektor mit genau der Kosinus-Distanz ``d`` zur Anfrage."""
    return _vektor(math.acos(1.0 - d))


@pytest.fixture
async def bestand(db_session):
    fach = Subject(slug=f"vf-{uuid.uuid4().hex[:8]}", name="Testfach N11", fach_code="VN11")
    anderes = Subject(slug=f"vg-{uuid.uuid4().hex[:8]}", name="Anderes N11", fach_code="VN12")
    db_session.add_all([fach, anderes])
    await db_session.flush()

    def knoten(typ, titel, distanz, subject=fach, category="concept"):
        return ContextNode(
            category=category, content_type=typ, title=titel, content="Inhalt",
            subject_id=subject.id, status="active", read_scope="school",
            write_scope="school", embedding=_fuer_distanz(distanz),
        )

    return fach, anderes, knoten


def _profil(**extra) -> Suchprofil:
    return Suchprofil(pseudonym="p-n11", rollen=("student",), **extra)


async def _titel(db, **extra) -> list[str]:
    treffer = await vorab("egal", _profil(**extra), db, vektor=FRAGE)
    return [t["title"] for t in treffer]


class TestSchwelle:
    async def test_naher_treffer_kommt_mit(self, db_session, bestand):
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Nah dran", VORAB_SCHWELLE - 0.05))
        await db_session.flush()
        assert "Nah dran" in await _titel(db_session)

    async def test_ferner_treffer_bleibt_draussen(self, db_session, bestand):
        """Die Gegenprobe zur Regel: Ohne Schwelle stünde auch dieser Knoten im Prompt."""
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Zu weit weg", VORAB_SCHWELLE + 0.05))
        await db_session.flush()
        assert await _titel(db_session) == []

    async def test_fachbonus_hebt_die_schwelle_nicht_auf(self, db_session, bestand):
        """⚠️ **Die Schwelle gilt auf der rohen Distanz.**

        Fach- und Eigentümerbonus verschieben die Reihenfolge. Zöge man sie vor dem
        Vergleich ab, rutschte ein zu ferner Knoten allein deshalb in den Prompt, weil
        er aus dem Fach der Konversation stammt — der Bonus ist 0,05 groß, die
        Entscheidung „passt das überhaupt?" darf davon nicht abhängen.
        """
        fach, _, knoten = bestand
        db_session.add(knoten("begriff", "Knapp zu weit", VORAB_SCHWELLE + 0.02))
        await db_session.flush()
        assert await _titel(db_session, subject_id=fach.id) == []


class TestKnotenarten:
    async def test_nur_was_schueler_in_die_hand_bekommen(self, db_session, bestand):
        """Eine Bildungsplan-Kompetenz ist näher dran und bleibt trotzdem draußen."""
        _, _, knoten = bestand
        db_session.add_all([
            knoten("ik_kompetenz", "Sehr nahe Kompetenz", 0.01, category="knowledge"),
            knoten("begriff", "Fernerer Begriff", VORAB_SCHWELLE - 0.05),
        ])
        await db_session.flush()
        assert await _titel(db_session) == ["Fernerer Begriff"]

    async def test_alle_vier_erlaubten_arten_kommen(self, db_session, bestand):
        from app.context.taxonomy import VORAB_TYPEN
        _, _, knoten = bestand
        db_session.add_all([
            knoten(typ, f"Art {typ}", 0.10,
                   category="knowledge" if typ.endswith("blatt") else "concept")
            for typ in VORAB_TYPEN
        ])
        await db_session.flush()
        assert len(await _titel(db_session)) == len(VORAB_TYPEN)


class TestFachwahl:
    async def test_fach_der_konversation_kommt_zuerst(self, db_session, bestand):
        fach, anderes, knoten = bestand
        db_session.add_all([
            knoten("begriff", "Aus anderem Fach", 0.10, subject=anderes),
            knoten("begriff", "Aus dem Fach", 0.12),
        ])
        await db_session.flush()
        assert (await _titel(db_session, subject_id=fach.id))[0] == "Aus dem Fach"

    async def test_ohne_fach_gewinnt_die_naehe(self, db_session, bestand):
        """Gegenprobe zum Test darunter: dieselben zwei Knoten, kein Fachbezug."""
        _, anderes, knoten = bestand
        db_session.add_all([
            knoten("begriff", "Aus anderem Fach", 0.10, subject=anderes),
            knoten("begriff", "Aus meinem Fach", 0.11),
        ])
        await db_session.flush()
        assert (await _titel(db_session))[0] == "Aus anderem Fach"

    async def test_eigene_faecher_ziehen_vor(self, db_session, bestand):
        """Der freie Chat: kein Fach an der Konversation, aber die Person hat Unterricht.

        ⚠️ Der Abstand der beiden Knoten (0,01) ist **kleiner** als der Vorzug (0,02) —
        sonst prüfte der Test nichts: Bei größerem Abstand gewänne die Nähe, und das
        wäre ebenfalls richtig. Der Vorzug ist eine Sortierstufe, kein Filter.
        """
        fach, anderes, knoten = bestand
        db_session.add_all([
            knoten("begriff", "Aus anderem Fach", 0.10, subject=anderes),
            knoten("begriff", "Aus meinem Fach", 0.11),
        ])
        await db_session.flush()
        titel = await _titel(db_session, eigene_faecher=(fach.id,))
        assert titel[0] == "Aus meinem Fach"


class TestAnker:
    async def test_anker_schraenkt_weiter_ein(self, db_session, bestand):
        """Ein Assistent mit Wissensbereich findet auch vorab nur, was darunter hängt."""
        from app.db.models import ContextEdge
        _, _, knoten = bestand
        anker = knoten("themengebiet", "Anker N11", 0.90, category="knowledge")
        drin = knoten("begriff", "Unter dem Anker", 0.10)
        draussen = knoten("begriff", "Daneben", 0.05)
        db_session.add_all([anker, drin, draussen])
        await db_session.flush()
        db_session.add(ContextEdge(
            from_node_id=drin.id, to_node_id=anker.id, relation="part_of", metadata_={},
        ))
        await db_session.flush()
        assert await _titel(db_session, anchor_ids=(anker.id,)) == ["Unter dem Anker"]


class TestNamenstreffer:
    """Der zweite Weg hinein: Wer den Eintrag beim Namen nennt, braucht keine Schwelle.

    ⚠️ **Ohne Embedding.** Die Tests übergeben ``vektor=None`` — so ist belegt, dass der
    Weg allein trägt. Das ist kein künstlicher Fall: Fällt der Einbettungsdienst aus,
    bleibt er die einzige Quelle der Grundschicht (einen ILIKE-Rückfall gibt es hier
    bewusst nicht, er schriebe bei jeder Floskel Beliebiges in den Prompt).
    """

    async def _titel(self, db, frage, **extra):
        treffer = await vorab(frage, _profil(**extra), db, vektor=None)
        return [t["title"] for t in treffer]

    async def test_exakter_titel_wird_gefunden(self, db_session, bestand):
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Oxidation", 0.9))
        await db_session.flush()
        assert await self._titel(db_session, "Was ist eine Oxidation?") == ["Oxidation"]

    async def test_suchbegriff_wird_gefunden(self, db_session, bestand):
        """„Mol" ist kein Titel, sondern ein Alias der Stoffmenge — genau dafür sind sie da."""
        from app.db.models import NodeAlias
        _, _, knoten = bestand
        n = knoten("begriff", "Stoffmenge", 0.9)
        db_session.add(n)
        await db_session.flush()
        db_session.add(NodeAlias(node_id=n.id, alias="Mol"))
        await db_session.flush()
        assert await self._titel(db_session, "Was ist ein Mol?") == ["Stoffmenge"]

    async def test_falsche_knotenart_bleibt_auch_beim_namen_draussen(self, db_session, bestand):
        """Gegenprobe zur Typregel auf **diesem** Weg — sie gilt nicht nur semantisch."""
        _, _, knoten = bestand
        db_session.add(knoten("ik_kompetenz", "Oxidation", 0.9, category="knowledge"))
        await db_session.flush()
        assert await self._titel(db_session, "Was ist eine Oxidation?") == []

    async def test_fremder_name_findet_nichts(self, db_session, bestand):
        """Gegenprobe: Der Weg ist **exakt**, keine Teilstringsuche."""
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Oxidation", 0.9))
        await db_session.flush()
        assert await self._titel(db_session, "Wie geht es dir?") == []


class TestImKontextblock:
    """Die Verdrahtung: Kommt die Grundschicht auch wirklich im Prompt an?

    Die Tests darüber prüfen die Auswahl, dieser den Weg dorthin —
    :func:`app.context.service.get_context_for_query` ist die einzige Stelle, die der
    Chat-Router aufruft.
    """

    async def test_treffer_steht_im_kontextblock(self, db_session, bestand, monkeypatch):
        from app.context import service
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Elektronenpaarbindung", 0.10))
        await db_session.flush()

        async def _vektor(_frage):
            return FRAGE
        monkeypatch.setattr(service, "vektor_oder_none", _vektor)

        ctx = await service.get_context_for_query(
            assistant_id=None, pseudonym="p-n11", query_text="egal",
            chat_id=None, db=db_session, rollen=("student",),
        )
        assert "Wissensspeicher der Schule" in ctx
        assert "Elektronenpaarbindung" in ctx

    async def test_ohne_treffer_bleibt_der_block_weg(self, db_session, bestand, monkeypatch):
        """Gegenprobe: Ein leerer Abschnitt im Prompt wäre schlimmer als keiner — er
        sagte dem Modell, im Wissensspeicher stehe nichts."""
        from app.context import service
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Viel zu weit weg", 0.95))
        await db_session.flush()

        async def _vektor(_frage):
            return FRAGE
        monkeypatch.setattr(service, "vektor_oder_none", _vektor)

        ctx = await service.get_context_for_query(
            assistant_id=None, pseudonym="p-n11", query_text="egal",
            chat_id=None, db=db_session, rollen=("student",),
        )
        assert "Wissensspeicher der Schule" not in ctx
