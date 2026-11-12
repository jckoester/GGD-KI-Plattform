"""`scripts/seed_assistants.py` mit Schüler-Assistenten und Auslöser-Beispielen (26.10.2026).

Anlegen mit allen Feldern, zweiter Lauf ohne Dubletten, Nachtrag der Beispiele bei einem
schon vorhandenen Assistenten — und kein Überschreiben eigener Beispiele.
Erfordert TEST_DATABASE_URL.
"""
import importlib.util
from pathlib import Path

import pytest
import pytest_asyncio
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.assistants import ausloeser
from app.db.models import Assistant, AssistantDocument, Subject

pytestmark = pytest.mark.asyncio

_spec = importlib.util.spec_from_file_location(
    "seed_assistants", Path(__file__).resolve().parents[2] / "scripts/seed_assistants.py"
)
SEED = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SEED)

PRAEFIX = "SEED "
SLUG = "seedtest-chemie"


@pytest_asyncio.fixture
async def sitzungen(async_engine):
    fabrik = async_sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)
    async with fabrik() as db:
        if not (await db.execute(sa.select(Subject.id).where(Subject.slug == SLUG))).first():
            db.add(Subject(name="Seedtest Chemie", slug=SLUG))
            await db.commit()
    yield fabrik
    async with fabrik() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.commit()


def _yaml(tmp_path, eintraege: str) -> Path:
    datei = tmp_path / "assistants.yaml"
    datei.write_text("assistants:\n" + eintraege, encoding="utf-8")
    return datei


EINTRAG = f"""
  - name: {PRAEFIX}Rechenhilfe
    system_prompt: P
    audience: student
    scope: all_students
    subject: {SLUG}
    min_grade: 8
    max_grade: 13
    model: chat-komplex
    disabled_augmentations: [metacognitive_nudges]
    documents: [config/prompts/stoechiometrie_pse_schulwerte.md]
    suggest: specific
    suggestion_text: "  Eine Rechenhilfe.  "
    fallbacks: [{PRAEFIX}Allgemein]
    trigger_examples: [eins, zwei, eins]
    trigger_counterexamples: [drei]
  - name: {PRAEFIX}Allgemein
    system_prompt: P
    audience: student
    scope: all_students
    suggest: fallback
"""


async def _lade(sitzungen, name):
    async with sitzungen() as db:
        a = (await db.execute(sa.select(Assistant).where(Assistant.name == name))).scalar_one()
        return a, await ausloeser.lade(db, a.id), list(
            (await db.execute(sa.select(AssistantDocument).where(AssistantDocument.assistant_id == a.id))).scalars()
        )


async def test_anlegen_mit_allen_feldern(sitzungen, tmp_path):
    stand = await SEED.seed(_yaml(tmp_path, EINTRAG), session_factory=sitzungen)
    assert stand["angelegt"] == 2 and stand["fehler"] == 0

    a, listen, docs = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    rueck, _, _ = await _lade(sitzungen, f"{PRAEFIX}Allgemein")
    assert (a.min_grade, a.max_grade, a.model, a.scope, a.audience) == (8, 13, "chat-komplex", "all_students", "student")
    assert a.disabled_augmentations == ["metacognitive_nudges"]
    assert a.subject_id is not None
    assert (a.suggest, a.suggestion_text) == ("specific", "Eine Rechenhilfe.")
    assert a.fallbacks == [rueck.id]
    assert listen == {"beispiel": ["eins", "zwei"], "gegenbeispiel": ["drei"]}
    assert [d.filename for d in docs] == ["stoechiometrie_pse_schulwerte.md"]
    assert docs[0].content.strip()


async def test_zweiter_lauf_legt_nichts_doppelt_an(sitzungen, tmp_path):
    datei = _yaml(tmp_path, EINTRAG)
    await SEED.seed(datei, session_factory=sitzungen)
    stand = await SEED.seed(datei, session_factory=sitzungen)
    assert (stand["angelegt"], stand["nachgetragen"], stand["uebersprungen"]) == (0, 0, 2)
    _, listen, docs = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    assert listen["beispiel"] == ["eins", "zwei"] and len(docs) == 1


async def test_nachtrag_bei_vorhandenem_ohne_beispiele(sitzungen, tmp_path):
    """Der Prod-Fall: von Hand angelegt, ohne Beispiele, `suggest` auf der Vorgabe."""
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="eigener Prompt", model="",
                         audience="student", scope="all_students", suggest="never", fallbacks=[]))
        await db.commit()

    stand = await SEED.seed(_yaml(tmp_path, EINTRAG), session_factory=sitzungen)
    assert stand["nachgetragen"] == 1

    a, listen, docs = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    assert listen["beispiel"] == ["eins", "zwei"]
    assert (a.suggest, a.suggestion_text) == ("specific", "Eine Rechenhilfe.")
    # Seit 0.32.1 auch die übrigen leeren Felder (Prod 04.11.2026: ohne Fach und Stufen) …
    assert (a.min_grade, a.max_grade) == (8, 13) and a.subject_id is not None
    assert len(docs) == 1
    # … aber nie Prompt und Modell — sie sind Entscheidungen der Schule.
    assert (a.system_prompt, a.model) == ("eigener Prompt", "")


async def test_eigene_beispiele_werden_nicht_ueberschrieben(sitzungen, tmp_path):
    async with sitzungen() as db:
        a = Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="P", model="", audience="student",
                      scope="all_students", suggest="fallback", fallbacks=[])
        db.add(a)
        await db.flush()
        await ausloeser.setze(db, a.id, ausloeser.BEISPIEL, ["meins"])
        await db.commit()

    await SEED.seed(_yaml(tmp_path, EINTRAG), session_factory=sitzungen)

    a, listen, _ = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    assert listen["beispiel"] == ["meins"] and a.suggest == "fallback"


async def test_unbekanntes_fach_ist_ein_fehler(sitzungen, tmp_path):
    stand = await SEED.seed(_yaml(tmp_path, f"""
  - name: {PRAEFIX}Ohne Fach
    system_prompt: P
    subject: gibt-es-nicht
"""), session_factory=sitzungen)
    assert (stand["angelegt"], stand["fehler"]) == (0, 1)


async def test_rueckfaelle_bei_vorhandenem_nachtragen(sitzungen, tmp_path):
    """Chemie-Assistent schon da (ohne Rückfälle), Rückfall-Assistent kommt neu dazu."""
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="P", model="", audience="student",
                         scope="all_students", suggest="specific", fallbacks=[]))
        await db.commit()
    await SEED.seed(_yaml(tmp_path, EINTRAG), session_factory=sitzungen)
    a, _, _ = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    rueck, _, _ = await _lade(sitzungen, f"{PRAEFIX}Allgemein")
    assert a.fallbacks == [rueck.id]


async def test_operator_faecher_beim_anlegen(sitzungen, tmp_path):
    """Päckchen AF: Fächer, die es hier nicht gibt, werden übergangen, nicht als Fehler."""
    stand = await SEED.seed(_yaml(tmp_path, f"""
  - name: {PRAEFIX}NW
    system_prompt: P
    audience: student
    operator_faecher: [{SLUG.upper()}, gibt-es-nicht]
"""), session_factory=sitzungen)
    assert (stand["angelegt"], stand["fehler"]) == (1, 0)
    a, _, _ = await _lade(sitzungen, f"{PRAEFIX}NW")
    assert a.operator_faecher == [SLUG]


async def test_operator_faecher_nachtragen(sitzungen, tmp_path):
    """Der Prod-Fall nach 0.22: der NW-Assistent ist da, das Feld leer. Eigene bleiben."""
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}NW", system_prompt="P", model="", audience="student",
                         scope="all_students", suggest="fallback", fallbacks=[]))
        db.add(Assistant(name=f"{PRAEFIX}Eigen", system_prompt="P", model="", audience="student",
                         scope="all_students", suggest="never", fallbacks=[], operator_faecher=["andere"]))
        await db.commit()
    await SEED.seed(_yaml(tmp_path, f"""
  - name: {PRAEFIX}NW
    system_prompt: P
    operator_faecher: [{SLUG}]
  - name: {PRAEFIX}Eigen
    system_prompt: P
    operator_faecher: [{SLUG}]
"""), session_factory=sitzungen)
    nw, _, _ = await _lade(sitzungen, f"{PRAEFIX}NW")
    eigen, _, _ = await _lade(sitzungen, f"{PRAEFIX}Eigen")
    assert (nw.operator_faecher, eigen.operator_faecher) == ([SLUG], ["andere"])


# ── Leere Felder nachtragen (0.32.1) ─────────────────────────────────────────────


async def test_gesetztes_bleibt(sitzungen, tmp_path):
    """Nur Leeres wird gefüllt: eigenes Fach, eine eigene Stufengrenze, eigene Schlagwörter,
    ein eigenes Dokument und ein bewusst gesetzter Vorschlag bleiben."""
    async with sitzungen() as db:
        fach = Subject(name="Seedtest Eigenes", slug=f"{SLUG}-eigen")
        db.add(fach)
        await db.flush()
        a = Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="P", model="", audience="student",
                      scope="all_students", suggest="fallback", fallbacks=[], subject_id=fach.id,
                      min_grade=10, tags=["eigen"], suggestion_text="Mein Text")
        db.add(a)
        await db.flush()
        db.add(AssistantDocument(assistant_id=a.id, filename="eigen.md", mime_type="text/markdown",
                                 size_bytes=1, content="x"))
        await db.commit()
        fach_id = fach.id

    await SEED.seed(_yaml(tmp_path, EINTRAG), session_factory=sitzungen)

    a, _, docs = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    assert (a.subject_id, a.min_grade, a.max_grade) == (fach_id, 10, None), "eine Grenze allein bleibt"
    assert a.tags == ["eigen"] and (a.suggest, a.suggestion_text) == ("fallback", "Mein Text")
    assert [d.filename for d in docs] == ["eigen.md"]
    async with sitzungen() as db:
        await db.execute(sa.delete(Assistant).where(Assistant.name.like(f"{PRAEFIX}%")))
        await db.execute(sa.delete(Subject).where(Subject.id == fach_id))
        await db.commit()


async def test_probelauf_aendert_nichts(sitzungen, tmp_path):
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="P", model="", audience="student",
                         scope="all_students", suggest="never", fallbacks=[]))
        await db.commit()

    stand = await SEED.seed(_yaml(tmp_path, EINTRAG), dry_run=True, session_factory=sitzungen)
    assert stand["nachgetragen"] == 1

    a, listen, docs = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    assert (a.suggest, a.subject_id, a.min_grade) == ("never", None, None) and not a.tags
    assert listen["beispiel"] == [] and docs == []


async def test_unbekanntes_fach_beim_nachtragen_wird_uebergangen(sitzungen, tmp_path):
    """Beim Anlegen ein Fehler, beim Nachtragen nicht: Die übrigen Felder kommen trotzdem."""
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="P", model="", audience="student",
                         scope="all_students", suggest="never", fallbacks=[]))
        await db.commit()

    eintrag = EINTRAG.replace(f"subject: {SLUG}", "subject: gibt-es-nicht")
    stand = await SEED.seed(_yaml(tmp_path, eintrag), session_factory=sitzungen)
    assert stand["fehler"] == 0

    a, _, _ = await _lade(sitzungen, f"{PRAEFIX}Rechenhilfe")
    assert a.subject_id is None and (a.min_grade, a.suggest) == (8, "specific")


async def test_vollstaendiger_assistent_wird_uebersprungen(sitzungen, tmp_path):
    datei = _yaml(tmp_path, EINTRAG)
    await SEED.seed(datei, session_factory=sitzungen)
    stand = await SEED.seed(datei, session_factory=sitzungen)
    assert (stand["nachgetragen"], stand["uebersprungen"]) == (0, 2)



async def test_stellt_her_beim_anlegen_und_als_nachtrag(sitzungen, tmp_path):
    """0.40: `produces` wird angelegt und bei einem Vorhandenen nachgetragen, wenn leer (S3)."""
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}Schaltplan", system_prompt="P", model="",
                         audience="all", scope="all", suggest="never", fallbacks=[]))
        await db.commit()

    eintraege = f"""
  - name: {PRAEFIX}Schaltplan
    system_prompt: P
    produces: [diagram]
  - name: {PRAEFIX}Neu
    system_prompt: P
    produces: [year_plan, zeitreise, image]
"""
    await SEED.seed(_yaml(tmp_path, eintraege), session_factory=sitzungen)

    vorhanden, _, _ = await _lade(sitzungen, f"{PRAEFIX}Schaltplan")
    neu, _, _ = await _lade(sitzungen, f"{PRAEFIX}Neu")
    assert vorhanden.produces == ["diagram"]
    # Unbekanntes wird übergangen, der Rest in Listenreihenfolge.
    assert neu.produces == ["image", "year_plan"]


async def test_gesetztes_stellt_her_bleibt(sitzungen, tmp_path):
    """Auch eine abgewählte Angabe ist eine Entscheidung — nur ein gesetzter Wert ist erkennbar."""
    async with sitzungen() as db:
        db.add(Assistant(name=f"{PRAEFIX}Schaltplan", system_prompt="P", model="", audience="all",
                         scope="all", suggest="never", fallbacks=[], produces=["document"]))
        await db.commit()

    await SEED.seed(_yaml(tmp_path, f"""
  - name: {PRAEFIX}Schaltplan
    system_prompt: P
    produces: [diagram]
"""), session_factory=sitzungen)

    a, _, _ = await _lade(sitzungen, f"{PRAEFIX}Schaltplan")
    assert a.produces == ["document"]
