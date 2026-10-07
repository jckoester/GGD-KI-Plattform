#!/usr/bin/env python3
"""Die Schwelle der Vorab-Suche nachmessen (Paket 9, N11).

    cd backend && venv/bin/python scripts/vorab_schwelle.py

Stellt fachliche Nachrichten beiläufigen gegenüber und zeigt je Nachricht die Distanz
zu den drei nächsten Bausteinen. `VORAB_SCHWELLE` in `app/context/search.py` gehört
**zwischen** den größten erwünschten und den kleinsten unerwünschten Wert; dort stehen
die Messungen vom 26.09. und 06.10.2026.

Am Ende stehen beide Grenzwerte, die Lücke und ob die Schwelle darin liegt — nachmessen
ist ein Aufruf und ein Blick (0.14, Schritt 6). Liegt sie nicht dazwischen, endet das
Skript mit Exit-Code 1.

⚠️ **Nachmessen, wenn der Bestand wächst.** Die Schwelle trennt mit knapp 0,05 Abstand.
Jeder neue Baustein kann diese Lücke schließen — dann muss die Regel enger werden
(Typen, Fachbezug), nicht die Schwelle weicher.
"""
import argparse
import asyncio
import sys
from dataclasses import dataclass

sys.path.insert(0, ".")

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
]
#: Fälle, bei denen ein Treffer **richtig** wäre, die aber keine Schwelle vom
#: Unerwünschten trennt. Sie zählen zu keiner Grenze — gezeigt wird, wo sie liegen.
GRENZFAELLE = [
    "Ich muss ein Gedicht von Goethe interpretieren.",
]


@dataclass(frozen=True)
class Messwert:
    frage: str
    titel: str          # nächster Treffer
    distanz: float


@dataclass(frozen=True)
class Grenzen:
    erwuenscht: Messwert      # größte Distanz unter den fachlichen
    unerwuenscht: Messwert    # kleinste Distanz unter den beiläufigen
    schwelle: float

    @property
    def luecke(self) -> float:
        return self.unerwuenscht.distanz - self.erwuenscht.distanz

    @property
    def trennt(self) -> bool:
        """Liegt die Schwelle **strikt** dazwischen? Ein Treffer gilt bis einschließlich
        der Schwelle (`distanz > VORAB_SCHWELLE` fällt heraus)."""
        return self.erwuenscht.distanz <= self.schwelle < self.unerwuenscht.distanz


def grenzen(fachlich: list[Messwert], beilaeufig: list[Messwert], schwelle: float) -> Grenzen:
    return Grenzen(
        erwuenscht=max(fachlich, key=lambda m: m.distanz),
        unerwuenscht=min(beilaeufig, key=lambda m: m.distanz),
        schwelle=schwelle,
    )


def bericht(g: Grenzen, grenzfaelle: list[Messwert]) -> list[str]:
    zeilen = [
        f"  erwünscht höchstens   {g.erwuenscht.distanz:.3f}  "
        f"{g.erwuenscht.frage[:40]} → {g.erwuenscht.titel}",
        f"  unerwünscht ab        {g.unerwuenscht.distanz:.3f}  "
        f"{g.unerwuenscht.frage[:40]} → {g.unerwuenscht.titel}",
        f"  Lücke                 {g.luecke:.3f}",
        f"  VORAB_SCHWELLE        {g.schwelle:.3f}  "
        + ("liegt dazwischen ✓" if g.trennt else "liegt NICHT dazwischen ✗"),
    ]
    for m in grenzfaelle:
        lage = ("innerhalb" if m.distanz <= g.schwelle else "außerhalb")
        zeilen.append(f"  Grenzfall             {m.distanz:.3f}  {m.frage[:40]} → {m.titel} "
                      f"({lage} der Schwelle)")
    return zeilen


async def messe(db, fragen: list[str]) -> list[Messwert]:
    import sqlalchemy as sa
    from app.context.search import vektor_oder_none
    from app.context.taxonomy import VORAB_TYPEN
    from app.db.models import ContextNode

    werte = []
    for f in fragen:
        v = await vektor_oder_none(f)
        if v is None:
            print(f"  kein Embedding  {f}")
            continue
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
        werte.append(Messwert(f, zeilen[0][0], float(zeilen[0][1])))
    return werte


async def main(trotzdem: bool) -> int:
    from app.context.embedding import vor_einer_messung
    from app.context.search import VORAB_SCHWELLE
    from app.context.taxonomy import VORAB_TYPEN
    from app.db.session import AsyncSessionLocal

    # ⚠️ Am 06.10.2026 zeigte dieses Skript eine scheinbar zerbrochene Schwelle — gemessen
    # war, dass 100 von 107 Begriffen keinen Vektor hatten. Deshalb zuerst die Lücken.
    await vor_einer_messung(VORAB_TYPEN, trotzdem=trotzdem)
    async with AsyncSessionLocal() as db:
        gruppen = {}
        for name, fragen in (("FACHLICH", FACHLICH), ("BEILÄUFIG", BEILAEUFIG),
                             ("GRENZFALL", GRENZFAELLE)):
            print(f"\n── {name} ──")
            gruppen[name] = await messe(db, fragen)
    if not gruppen["FACHLICH"] or not gruppen["BEILÄUFIG"]:
        print("\nZu wenig Messwerte für eine Aussage.")
        return 1
    g = grenzen(gruppen["FACHLICH"], gruppen["BEILÄUFIG"], VORAB_SCHWELLE)
    print("\n── ERGEBNIS ──")
    print("\n".join(bericht(g, gruppen["GRENZFALL"])))
    return 0 if g.trennt else 1


if __name__ == "__main__":
    _p = argparse.ArgumentParser(description="Schwelle der Vorab-Suche nachmessen")
    _p.add_argument("--trotzdem", action="store_true",
                    help="Auch messen, wenn Knoten ohne Vektor sind (sonst Abbruch)")
    sys.exit(asyncio.run(main(_p.parse_args().trotzdem)))
