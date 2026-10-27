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
    # Alles andere bleibt, wie die Schule es eingerichtet hat.
    assert (a.system_prompt, a.model, a.min_grade) == ("eigener Prompt", "", None)
    assert docs == []


async def test_eigene_beispiele_werden_nicht_ueberschrieben(sitzungen, tmp_path):
    async with sitzungen() as db:
        a = Assistant(name=f"{PRAEFIX}Rechenhilfe", system_prompt="P", model="", audience="student",
                      scope="all_students", suggest="fallback", fallbacks=[])
        db.add(a)
        await db.flush()
        await ausloeser.setze(db, a.id, ausloeser.BEISPIEL, ["meins"])
        await db.commit()

    stand = await SEED.seed(_yaml(tmp_path, EINTRAG), session_factory=sitzungen)
    assert stand["nachgetragen"] == 0

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
