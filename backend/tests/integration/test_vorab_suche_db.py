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
from app.context.search import (_KANDIDATEN_FAKTOR, VORAB_ANGEBOT, VORAB_ANGEBOT_MAX, VORAB_MAX,
                                VORAB_SCHWELLE, Suchprofil, Vorabergebnis, vorab)
from app.db.models import ContextNode, NodeAlias, Subject

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
    """Die Titel der **sicheren** Stufe — was als Inhalt in den Prompt geht."""
    ergebnis = await vorab("egal", _profil(**extra), db, vektor=FRAGE)
    return [t["title"] for t in ergebnis.sicher]


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


class TestBezugsfaecher:
    """Die Bezugsfächer des Chat-Fachs im Suchprofil (0.16, Schritt 2).

    Noch ohne Wirkung auf die Suche — hier geht es nur darum, dass das Profil sie trägt,
    gerichtet und aus dem Fach der Konversation.
    """

    async def test_aufgeloest_und_gerichtet(self, db_session, bestand):
        from app.context.service import bezugsfaecher_von
        fach, anderes, _ = bestand
        fach.bezugsfaecher = [anderes.slug, "gibt-es-nicht"]
        await db_session.flush()
        assert await bezugsfaecher_von(db_session, fach.id) == (anderes.id,)
        assert await bezugsfaecher_von(db_session, anderes.id) == ()
        assert await bezugsfaecher_von(db_session, None) == ()

    async def _profil_im_chat(self, db_session, monkeypatch, subject_id):
        from app.context import service
        from app.db.models import Conversation
        konv = Conversation(pseudonym="p-n11", model_used="chat-standard", subject_id=subject_id)
        db_session.add(konv)
        await db_session.flush()
        gesehen = []

        async def _vorab(frage, profil, db, *, vektor):
            gesehen.append(profil)
            return Vorabergebnis()
        monkeypatch.setattr(service, "vorab", _vorab)
        await service._grundschicht("egal", db_session, pseudonym="p-n11", rollen=("student",),
                                    chat_id=konv.id, anchor_ids=(), jwt_stufe=None, vektor=FRAGE)
        return gesehen[0]

    async def test_profil_traegt_die_bezugsfaecher_des_chat_fachs(self, db_session, bestand, monkeypatch):
        fach, anderes, _ = bestand
        fach.bezugsfaecher = [anderes.slug]
        await db_session.flush()
        profil = await self._profil_im_chat(db_session, monkeypatch, fach.id)
        assert profil.bezugsfaecher == (anderes.id,)

    async def test_ohne_fach_keine_bezugsfaecher(self, db_session, bestand, monkeypatch):
        """Gegenprobe: Der freie Chat hat kein Fach, also auch nichts, das es mitliest."""
        fach, anderes, _ = bestand
        fach.bezugsfaecher = [anderes.slug]
        await db_session.flush()
        profil = await self._profil_im_chat(db_session, monkeypatch, None)
        assert profil.bezugsfaecher == ()


class TestAngebot:
    """Die zweite Stufe der Vorab-Suche (0.16): Titel ohne Inhalt.

    Angeboten wird, was **nicht sicher** ist und roh höchstens :data:`VORAB_ANGEBOT` entfernt
    liegt — zuerst im Satz Genanntes (aus dem Fach der Konversation, seinen Bezugsfächern
    oder fachlos), dann Nähe aus derselben Kandidatenabfrage wie die sichere Stufe.
    """

    SATZ = "Letzte Stunde haben wir etwas über {} gelernt, das ich nicht ganz verstanden habe."
    IM_BAND = (VORAB_SCHWELLE + VORAB_ANGEBOT) / 2      # über der Schwelle, im Angebot

    async def _vorab(self, db, frage, **extra) -> Vorabergebnis:
        return await vorab(frage, _profil(**extra), db, vektor=FRAGE)

    @staticmethod
    def _angebot(ergebnis: Vorabergebnis) -> list[tuple[str, str]]:
        return [(t["title"], t["quelle"]) for t in ergebnis.angebot]

    async def test_genannt_im_band_wird_angeboten_nicht_eingefuegt(self, db_session, bestand):
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Elektronegativität", self.IM_BAND))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, self.SATZ.format("Elektronegativität"))
        assert ergebnis.sicher == []
        assert self._angebot(ergebnis) == [("Elektronegativität", "nennung")]
        assert ergebnis.angebot[0]["fach"] == "Testfach N11"

    async def test_ungenannt_im_band_kommt_ueber_die_distanz(self, db_session, bestand):
        """Gegenprobe zur Quelle: derselbe Knoten, nicht genannt — angeboten wird er trotzdem,
        nur aus der Distanz."""
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Elektronegativität", self.IM_BAND))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, self.SATZ.format("die Bindung"))
        assert self._angebot(ergebnis) == [("Elektronegativität", "distanz")]

    async def test_hinter_dem_band_kein_angebot(self, db_session, bestand):
        """„Wie geht es dir?" und „ein Eis essen": Ohne Nähe kein Angebot — auch nicht, wenn
        der Titel im Satz steht. Das Band ist die einzige Grenze."""
        _, _, knoten = bestand
        db_session.add_all([knoten("begriff", "Eis", VORAB_ANGEBOT + 0.05),
                            knoten("begriff", "Elektronegativität", VORAB_ANGEBOT + 0.05)])
        await db_session.flush()
        for frage in ("Wie geht es dir?", "Wir wollen nachher ein Eis essen."):
            ergebnis = await self._vorab(db_session, frage)
            assert (ergebnis.sicher, ergebnis.angebot) == ([], []), frage

    async def test_alltagswort_hoechstens_als_angebot(self, db_session, bestand):
        """„Dein Hemd ist aus einem tollen Stoff." nennt die Stoffe — höchstens als Titel,
        nie als Inhalt (Reihe 2, 14.10.2026)."""
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Stoffe", self.IM_BAND))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, "Dein Hemd ist aus einem tollen Stoff.")
        assert ergebnis.sicher == []
        assert self._angebot(ergebnis) == [("Stoffe", "nennung")]

    async def test_sicherer_treffer_nicht_zusaetzlich_im_angebot(self, db_session, bestand):
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Elektronegativität", VORAB_SCHWELLE - 0.05))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, self.SATZ.format("Elektronegativität"))
        assert [t["title"] for t in ergebnis.sicher] == ["Elektronegativität"]
        assert ergebnis.angebot == []

    async def test_hoechstens_fuenf_titel_nennungen_vorn(self, db_session, bestand):
        """Sechs Kandidaten im Band, zwei davon genannt: fünf Titel, die genannten zuerst —
        obwohl die ungenannten näher liegen."""
        _, _, knoten = bestand
        db_session.add_all([knoten("begriff", f"Nachbar {i}", VORAB_SCHWELLE + 0.005 + i / 1000)
                            for i in range(4)])
        db_session.add_all([knoten("begriff", "Elektronegativität", VORAB_ANGEBOT - 0.01),
                            knoten("begriff", "Oxidation", VORAB_ANGEBOT - 0.005)])
        await db_session.flush()
        frage = "Was haben Elektronegativität und Oxidation miteinander zu tun?"
        ergebnis = await self._vorab(db_session, frage)
        assert len(ergebnis.angebot) == VORAB_ANGEBOT_MAX
        assert self._angebot(ergebnis) == [
            ("Elektronegativität", "nennung"), ("Oxidation", "nennung"),
            ("Nachbar 0", "distanz"), ("Nachbar 1", "distanz"), ("Nachbar 2", "distanz"),
        ]

    async def test_vom_deckel_verdraengt_wird_angeboten(self, db_session, bestand):
        """Ein Knoten unter der Schwelle, den der Deckel aus der sicheren Stufe drängt, fällt
        nicht durch beide Stufen — genannt wie ungenannt."""
        _, _, knoten = bestand
        db_session.add_all([knoten("begriff", f"Nachbar {i}", 0.10 + i / 1000)
                            for i in range(VORAB_MAX + 1)])
        db_session.add(knoten("begriff", "Elektronegativität", VORAB_SCHWELLE - 0.05))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, self.SATZ.format("Elektronegativität"))
        assert [t["title"] for t in ergebnis.sicher] == [f"Nachbar {i}" for i in range(VORAB_MAX)]
        assert self._angebot(ergebnis) == [
            ("Elektronegativität", "nennung"), (f"Nachbar {VORAB_MAX}", "distanz"),
        ]

    async def test_nennung_auch_hinter_vielen_naeheren(self, db_session, bestand):
        """F4: Mehr nähere Knoten, als die Abfrage an Kandidaten holt, verdrängen den genannten
        nicht aus dem Angebot."""
        _, _, knoten = bestand
        n = VORAB_MAX * _KANDIDATEN_FAKTOR + 1
        db_session.add_all([knoten("begriff", f"Nachbar {i:02d}", 0.10 + i / 1000) for i in range(n)])
        db_session.add(knoten("begriff", "Elektronegativität", self.IM_BAND))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, self.SATZ.format("Elektronegativität"))
        assert len(ergebnis.sicher) == VORAB_MAX
        assert self._angebot(ergebnis)[0] == ("Elektronegativität", "nennung")

    async def test_alias_fuehrt_zum_angebot(self, db_session, bestand):
        _, _, knoten = bestand
        k = knoten("begriff", "Edelgasregel", self.IM_BAND)
        db_session.add(k)
        await db_session.flush()
        db_session.add(NodeAlias(node_id=k.id, alias="Oktettregel"))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, self.SATZ.format("die Oktettregel"))
        assert self._angebot(ergebnis) == [("Edelgasregel", "nennung")]

    async def test_endungen_im_satz(self, db_session, bestand):
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Ion", self.IM_BAND))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, "Ich verstehe Ionen nicht.")
        assert self._angebot(ergebnis) == [("Ion", "nennung")]

    async def test_fach_ohne_bezug_nicht_ueber_die_nennung(self, db_session, bestand):
        """Der Fachfilter der Nennung bleibt (Kriterium 7 von Schritt 1). Über die Distanz darf
        der Knoten kommen — geprüft wird die Quelle, nicht sein Fehlen (Plan § 7.7 Nr. 5)."""
        fach, anderes, knoten = bestand
        db_session.add(knoten("begriff", "Fotosynthese", self.IM_BAND, subject=anderes))
        await db_session.flush()
        frage = self.SATZ.format("die Fotosynthese")
        ohne_bezug = await self._vorab(db_session, frage, subject_id=fach.id)
        assert self._angebot(ohne_bezug) == [("Fotosynthese", "distanz")]
        mit_bezug = await self._vorab(db_session, frage, subject_id=fach.id, bezugsfaecher=(anderes.id,))
        assert self._angebot(mit_bezug) == [("Fotosynthese", "nennung")]
        assert self._angebot(await self._vorab(db_session, frage)) == [("Fotosynthese", "nennung")]

    async def test_fachlose_zaehlen_immer(self, db_session, bestand):
        fach, _, knoten = bestand
        k = knoten("methodenblatt", "Gruppenpuzzle", self.IM_BAND, category="knowledge")
        k.subject_id = None
        db_session.add(k)
        await db_session.flush()
        ergebnis = await self._vorab(db_session, "Wir machen ein Gruppenpuzzle.", subject_id=fach.id)
        assert self._angebot(ergebnis) == [("Gruppenpuzzle", "nennung")]

    async def test_fachbonus_oeffnet_das_band_nicht(self, db_session, bestand):
        """Wie bei der Schwelle: Das Band gilt auf der rohen Distanz, nicht auf der sortierten."""
        fach, _, knoten = bestand
        db_session.add(knoten("begriff", "Elektronegativität", VORAB_ANGEBOT + 0.02))
        await db_session.flush()
        frage = self.SATZ.format("Elektronegativität")
        ergebnis = await self._vorab(db_session, frage, subject_id=fach.id)
        assert ergebnis.angebot == []

    async def test_ohne_vektor_kein_angebot(self, db_session, bestand):
        """Das Band braucht eine Distanz — ohne Embedding kein Rückfall auf den Namen im Satz."""
        _, _, knoten = bestand
        db_session.add(knoten("begriff", "Elektronegativität", self.IM_BAND))
        await db_session.flush()
        frage = self.SATZ.format("Elektronegativität")
        ergebnis = await vorab(frage, _profil(), db_session, vektor=None)
        assert (ergebnis.sicher, ergebnis.angebot) == ([], [])

    async def test_index_kennt_neue_begriffe_erst_nach_dem_verwerfen(self, db_session, bestand):
        """Der Namensindex liegt im Speicher — wer ihn nicht verwirft, sieht den alten Stand.
        Bis dahin kommt der Knoten nur über die Distanz."""
        from app.context import nennung
        _, _, knoten = bestand
        frage = self.SATZ.format("Elektronegativität")
        assert (await self._vorab(db_session, frage)).angebot == []
        db_session.add(knoten("begriff", "Elektronegativität", self.IM_BAND))
        await db_session.flush()
        assert self._angebot(await self._vorab(db_session, frage)) == [("Elektronegativität", "distanz")]
        nennung.verwerfen()
        assert self._angebot(await self._vorab(db_session, frage)) == [("Elektronegativität", "nennung")]


class TestFachfilter:
    """F8 (0.16): Im Chat mit Fach legt die sichere Stufe über die Distanz nur Knoten aus dem
    Fach, seinen Bezugsfächern und fachlose als Inhalt vor. Ein Fach ohne Bezug wird angeboten.

    Gemessen am 15.10.2026: „schriftliche Addition" im Mathe-Chat traf die Chemie-Addition
    (0,392) — mit Filter fielen die sieben Fehltreffer aus Fächern ohne Bezug weg, kein
    erwarteter Knoten ging verloren.
    """

    FRAGE = "Wie funktioniert die schriftliche Addition?"

    async def _vorab(self, db, frage=FRAGE, **extra) -> Vorabergebnis:
        return await vorab(frage, _profil(**extra), db, vektor=FRAGE)

    async def test_fach_ohne_bezug_wird_angeboten_statt_eingefuegt(self, db_session, bestand):
        fach, anderes, knoten = bestand
        db_session.add(knoten("begriff", "Addition", VORAB_SCHWELLE - 0.05, subject=anderes))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, subject_id=fach.id)
        assert ergebnis.sicher == []
        assert [(t["title"], t["quelle"]) for t in ergebnis.angebot] == [("Addition", "distanz")]

    async def test_mit_bezug_bleibt_er_sicher(self, db_session, bestand):
        """Gegenprobe: derselbe Knoten, das andere Fach ist Bezugsfach."""
        fach, anderes, knoten = bestand
        db_session.add(knoten("begriff", "Addition", VORAB_SCHWELLE - 0.05, subject=anderes))
        await db_session.flush()
        ergebnis = await self._vorab(db_session, subject_id=fach.id, bezugsfaecher=(anderes.id,))
        assert [t["title"] for t in ergebnis.sicher] == ["Addition"]

    async def test_im_freien_chat_gibt_es_keinen_filter(self, db_session, bestand):
        _, anderes, knoten = bestand
        db_session.add(knoten("begriff", "Addition", VORAB_SCHWELLE - 0.05, subject=anderes))
        await db_session.flush()
        assert [t["title"] for t in (await self._vorab(db_session)).sicher] == ["Addition"]

    async def test_fachlose_bleiben_sicher(self, db_session, bestand):
        fach, _, knoten = bestand
        k = knoten("methodenblatt", "Gruppenpuzzle", VORAB_SCHWELLE - 0.05, category="knowledge")
        k.subject_id = None
        db_session.add(k)
        await db_session.flush()
        ergebnis = await self._vorab(db_session, "Wir machen ein Gruppenpuzzle.", subject_id=fach.id)
        assert [t["title"] for t in ergebnis.sicher] == ["Gruppenpuzzle"]

    async def test_namenstreffer_filtert_er_nicht(self, db_session, bestand):
        """Wer den Namen nennt, meint den Eintrag — auch aus einem Fach ohne Bezug."""
        fach, anderes, knoten = bestand
        db_session.add(knoten("begriff", "Addition", 0.9, subject=anderes))
        await db_session.flush()
        ergebnis = await vorab("Was ist eine Addition?", _profil(subject_id=fach.id), db_session,
                               vektor=None)
        assert [t["title"] for t in ergebnis.sicher] == ["Addition"]

    async def test_ein_eigener_rueckt_nach(self, db_session, bestand):
        """Der gefilterte Platz geht an den nächsten zulässigen Knoten unter der Schwelle."""
        fach, anderes, knoten = bestand
        db_session.add_all([knoten("begriff", "Addition", 0.20, subject=anderes),
                            knoten("begriff", "Summand", 0.30)])
        await db_session.flush()
        ergebnis = await self._vorab(db_session, subject_id=fach.id)
        assert [t["title"] for t in ergebnis.sicher] == ["Summand"]
        assert [t["title"] for t in ergebnis.angebot] == ["Addition"]


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
        ergebnis = await vorab(frage, _profil(**extra), db, vektor=None)
        return [t["title"] for t in ergebnis.sicher]

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

    async def _kontext(self, db_session, monkeypatch):
        from app.context import service

        async def _vektor(_frage):
            return FRAGE
        monkeypatch.setattr(service, "vektor_oder_none", _vektor)
        return await service.kontext_fuer_frage(
            None, "p-n11", "egal", None, db_session, rollen=("student",),
        )

    async def test_angebot_als_satz_ohne_inhalt(self, db_session, bestand, monkeypatch):
        """Nur ein Angebot: ein Satz mit Titel und Fach, kein JSON-Block, kein Inhalt."""
        _, _, knoten = bestand
        k = knoten("begriff", "Elektronegativität", TestAngebot.IM_BAND)
        k.content = "Unverwechselbarer Inhalt"
        db_session.add(k)
        await db_session.flush()
        kontext = await self._kontext(db_session, monkeypatch)
        assert ("Im Wissensspeicher der Schule gibt es dazu: Elektronegativität (Testfach N11) — "
                "den Inhalt holst du mit dem Werkzeug, wenn er für die Antwort zählt.") in kontext.text
        assert "Unverwechselbarer Inhalt" not in kontext.text
        assert "automatisch zur letzten Nachricht" not in kontext.text
        assert kontext.bausteine == []
        assert [(a.titel, a.quelle) for a in kontext.angebot] == [("Elektronegativität", "distanz")]

    async def test_was_der_anker_als_inhalt_bringt_wird_nicht_angeboten(
        self, db_session, bestand, monkeypatch,
    ):
        """Ein Anker-Assistent bekommt die Bausteine seines Teilgraphen als Inhalt — ein
        Angebot dafür schickte das Modell nach etwas suchen, das schon dasteht."""
        from app.context import service
        from app.db.models import Assistant, AssistantContextAnchor, ContextEdge
        _, _, knoten = bestand
        anker = knoten("themengebiet", "Anker N11", 0.90, category="knowledge")
        drin = knoten("begriff", "Elektronegativität", TestAngebot.IM_BAND)
        drin.content = "Unverwechselbarer Inhalt"
        db_session.add_all([anker, drin])
        await db_session.flush()
        db_session.add(ContextEdge(from_node_id=drin.id, to_node_id=anker.id,
                                   relation="part_of", metadata_={}))
        assistent = Assistant(name="Anker-Helfer N11", system_prompt="Hilf.",
                              model="chat-standard", status="active")
        db_session.add(assistent)
        await db_session.flush()
        db_session.add(AssistantContextAnchor(assistant_id=assistent.id, node_id=anker.id,
                                              role="retrieval_scope"))
        await db_session.flush()

        async def _vektor(_frage):
            return FRAGE
        monkeypatch.setattr(service, "vektor_oder_none", _vektor)
        kontext = await service.kontext_fuer_frage(
            assistent.id, "p-n11", "egal", None, db_session, rollen=("student",),
        )
        assert "Unverwechselbarer Inhalt" in kontext.text
        assert "gibt es dazu" not in kontext.text
        assert kontext.angebot == []

    async def test_angebot_hinter_den_sicheren_heisst_ausserdem(self, db_session, bestand, monkeypatch):
        _, _, knoten = bestand
        db_session.add_all([knoten("begriff", "Elektronenpaarbindung", 0.10),
                            knoten("begriff", "Elektronegativität", TestAngebot.IM_BAND)])
        await db_session.flush()
        text = (await self._kontext(db_session, monkeypatch)).text
        assert text.index("automatisch zur letzten Nachricht") < text.index(
            "Im Wissensspeicher der Schule gibt es außerdem: Elektronegativität (Testfach N11)")
        assert "gibt es dazu" not in text
