#!/usr/bin/env python3
"""Die Schwelle der Vorab-Suche nachmessen (Paket 9, N11).

    cd backend && venv/bin/python scripts/vorab_schwelle.py

Stellt fachliche Nachrichten beiläufigen gegenüber und zeigt je Nachricht die Distanz
zu den drei nächsten Bausteinen. `VORAB_SCHWELLE` in `app/context/search.py` gehört
**unter** den kleinsten unerwünschten Wert; dort steht die Messung vom 26.09.2026.

⚠️ **Nachmessen, wenn der Bestand wächst.** Die Schwelle trennt heute mit 0,05 Abstand.
Jeder neue Baustein kann diese Lücke schließen — dann muss die Regel enger werden
(Typen, Fachbezug), nicht die Schwelle weicher.
"""
import asyncio, sys
sys.path.insert(0, ".")
import sqlalchemy as sa
from app.db.session import AsyncSessionLocal
from app.db.models import ContextNode, Subject
from app.context.search import vektor_oder_none
from app.context.taxonomy import VORAB_TYPEN

FACHLICH = [
    "Beim Sieden zerfällt Wasser in Wasserstoff und Sauerstoff, oder?",
    "Ist Salzsäure eine Säure?",
    "Was bedeutet das Zeichen mit der Flamme auf der Flasche?",
    "Wie heißt die Bindung im Wassermolekül richtig?",
    "Was ist eine Oxidation?",
    "Wie viel Mol sind 18 g Wasser?",
]
BEILAEUFIG = [
    "Danke!",
    "Hilf mir bei meiner Bewerbung um ein Praktikum.",
    "Was heißt „to consider“ auf Deutsch?",
    "Wie geht es dir?",
    "Kannst du mir einen Witz erzählen?",
    "Wann sind nochmal die Sommerferien?",
    "Ich muss ein Gedicht von Goethe interpretieren.",
]

async def main():
    async with AsyncSessionLocal() as db:
        for name, fragen in (("FACHLICH", FACHLICH), ("BEILÄUFIG", BEILAEUFIG)):
            print(f"\n── {name} ──")
            for f in fragen:
                v = await vektor_oder_none(f)
                if v is None:
                    print(" kein Embedding"); continue
                d = ContextNode.embedding.cosine_distance(v)
                zeilen = (await db.execute(
                    sa.select(ContextNode.title, d.label("d"))
                    .where(ContextNode.status == "active",
                           ContextNode.embedding.is_not(None),
                           ContextNode.content_type.in_(VORAB_TYPEN))
                    .order_by(d).limit(3)
                )).all()
                beste = " · ".join(f"{t} {x:.3f}" for t, x in zeilen)
                print(f" {zeilen[0][1]:.3f}  {f[:44]:<46} {beste}")

asyncio.run(main())
