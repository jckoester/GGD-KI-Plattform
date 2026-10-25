#!/usr/bin/env python3
"""Systemtext eines Zugs nachbauen und ins Mess-JSON schreiben (Stöchiometrie-Plan, Lauf 4, 24.10.2026).

    cd backend && venv/bin/python scripts/assistent_systemtext.py <verlauf.json> <fall-id> <konto-präfix>

Für jedes Protokoll-JSON eines Assistenten-Messlaufs (`kopf.assistent`, `faelle[].zuege[].schueler`,
`faelle[].stufe`) — etwa aus `stoechiometrie_messung.py`. Ergebnis unter `systemtext`: die
Systemnachrichten in der Reihenfolge, in der `chat/router.py` sie baut — Guardrail ·
Assistenten-Dokumente · Pädagogik + Kontext + Assistentenprompt · Ausgabeformat —, dazu die
Schülerfrage von Zug 1 des Falls.

⚠️ **Nachgebaut, nicht mitgeschnitten.** LiteLLM speichert auf Dev keine Nachrichten in den
Spend-Logs. Das Skript ruft dieselben Funktionen wie der Router, aber nicht den Router selbst:
Ändert sich dort die Reihenfolge oder kommt ein Baustein dazu (etwa die Hausversuchs-Warnung,
die nur bei passenden Fragen erscheint, oder die Bezugszeile einer Stunde), fehlt er hier.
Annahmen: Schüler:in ohne Unterrichtsgruppe, Fach aus dem Assistenten, kein Stundenbezug — wie
in den Messläufen. Die Hilfskonversation wird nicht gespeichert (Rollback).
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.chat.router import _get_guardrail_prompt
from app.config import settings
from app.context.service import kontext_fuer_frage, stufe_der_person
from app.db.models import Assistant, AssistantDocument, Conversation
from app.pedagogy.compose import compose_system_content, is_student_treatment
from app.pedagogy.config import load_pedagogy


async def main(datei: Path, fall_id: str, konto: str) -> None:
    daten = json.loads(datei.read_text(encoding="utf-8"))
    fall = next(f for f in daten["faelle"] if f["id"] == fall_id)
    frage = fall["zuege"][0]["schueler"]
    engine = create_async_engine(settings.database_url)
    async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as db:
        assistent = await db.get(Assistant, daten["kopf"]["assistent"])
        pseudonym = (await db.execute(sa.text(
            "SELECT pseudonym FROM pseudonym_audit WHERE pseudonym LIKE :p"), {"p": konto + "%"})).scalar_one()
        # Wie beim Anlegen im Router: Fach aus dem Assistenten, keine Gruppe (Konto ohne Gruppe).
        konv = Conversation(pseudonym=pseudonym, model_used=assistent.model or "", assistant_id=assistent.id,
                            subject_id=assistent.subject_id, system_prompt_snapshot=assistent.system_prompt)
        db.add(konv)
        await db.flush()
        teile: list[dict] = []
        guardrail = await _get_guardrail_prompt(db)
        if guardrail:
            teile.append({"role": "system", "quelle": "Guardrail", "content": guardrail})
        docs = (await db.execute(sa.select(AssistantDocument).where(AssistantDocument.assistant_id == assistent.id)
                                 .order_by(AssistantDocument.created_at))).scalars().all()
        if docs:
            teile.append({"role": "system", "quelle": "Assistenten-Dokumente", "content": "\n\n---\n\n".join(
                f"Hintergrunddokument \"{d.filename}\":\n\n{d.content}" for d in docs)})
        kontext = await kontext_fuer_frage(assistant_id=assistent.id, pseudonym=pseudonym, query_text=frage,
                                           chat_id=konv.id, db=db, rollen=["student"],
                                           jwt_stufe=str(fall["stufe"]))
        pedagogy = load_pedagogy()
        teile.append({"role": "system", "quelle": "Pädagogik + Kontext + Assistentenprompt", "content":
                      compose_system_content(
                          pedagogy,
                          student_treatment=is_student_treatment(assistent.audience, True),
                          stufe=await stufe_der_person(db, konv.id, str(fall["stufe"])),
                          bezug=None,
                          context_str=kontext.text,
                          assistant_system_prompt=assistent.system_prompt,
                          disabled_augmentations=assistent.disabled_augmentations,
                      )})
        if pedagogy.output_format.strip():
            teile.append({"role": "system", "quelle": "Ausgabeformat", "content": pedagogy.output_format.strip()})
        await db.rollback()          # die Hilfskonversation nicht speichern
    await engine.dispose()
    daten["systemtext"] = {
        "hinweis": "nachgebaut mit den Funktionen aus chat/router.py (gleiche Reihenfolge), nicht der gesendete "
                   "Text; Fall " + fall_id + ", Zug 1",
        "nachrichten": teile,
        "user": frage,
    }
    datei.write_text(json.dumps(daten, ensure_ascii=False, indent=2), encoding="utf-8")
    for t in teile:
        print(f"[{t['quelle']}] {len(t['content'])} Zeichen")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    asyncio.run(main(Path(sys.argv[1]), sys.argv[2], sys.argv[3]))
