#!/usr/bin/env python3
"""Prüfsatz für die semantische Suche — misst, ob sie findet, was sie finden soll.

Verwendung:
    python scripts/search_eval.py                        # ganzer Prüfsatz
    python scripts/search_eval.py --details              # zusätzlich die Trefferlisten
    python scripts/search_eval.py --frage "Fotosynthese" --fach Biologie
    python scripts/search_eval.py --json vorher.json     # für Vorher/Nachher-Vergleich

Gemessen wird gegen drei Läufe derselben Anfrage:

* **produktiv** — die Suche, die Nutzer:innen tatsächlich bekommen
  (``app.context.search.suche``, also Identifikation **und** thematische Auswahl in der
  Reihenfolge des Ergebnisumschlags). Daraus stammen
  Fach@1 und der Rang des erwarteten Knotens. Aufgerufen wird die **echte Funktion**,
  nicht eine Nachbildung: Was hier gemessen wird, ist damit zwangsläufig das, was läuft.
* **exakt** — vollständiger Durchlauf aller Vektoren, rein semantisch. Die Wahrheit über
  die Ähnlichkeit, und die Bezugsgröße für den Recall.
* **Index** — dieselbe semantische Abfrage mit dem Ausführungsplan, den PostgreSQL von
  sich aus wählt.

Die Abweichung zwischen den letzten beiden ist der Recall. Er ist der Wächter gegen einen
wiederkehrenden Vektorindex, weil dessen Ausfall **still** ist: Er wirft keinen Fehler,
er liefert nur schlechtere Ergebnisse.

Kein pytest-Test, sondern ein Skript: Die Frage ergibt nur gegen den echten Wissensgraph
und ein echtes Embedding-Modell Sinn — ohne Bildungsplan-Import und laufenden
LiteLLM-Proxy misst sie nichts.

⚠️ **Je Messung eine frische Verbindung, und der Plan wird verifiziert.** Beides ist
nicht Vorsicht, sondern Notwendigkeit: Verwendet man dieselbe Verbindung weiter, hält
PostgreSQL den Ausführungsplan des vorbereiteten Statements fest, und die zweite Messung
läuft mit dem Plan der ersten. Bei der ersten Fassung dieser Messung kam so für **jede**
Anfrage ein Recall von 100 % heraus — verglichen wurde in Wahrheit der exakte Durchlauf
mit sich selbst, während der Index in Wirklichkeit die Hälfte der Treffer verfehlte.
"""

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import asyncpg
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.context.search import _FACHBONUS as FACHBONUS
from app.config import settings
from app.context.embedding import generate_embedding

PRUEFSATZ_VORGABE = (
    Path(__file__).resolve().parents[2] / "config" / "search_eval.yaml"
)

INDEXNAME = "idx_context_nodes_embedding"

# Bewusst so nah wie möglich an der thematischen Auswahl der Suchschicht: Gemessen
# werden soll die Suche, die Nutzer:innen bekommen, nicht eine idealisierte Variante. Der
# `owner_pseudonym`-Zweig der Originalabfrage fehlt — private Knoten einzelner Personen
# gehören nicht in einen Prüfsatz, der den gemeinsamen Bestand bewertet.
#
# ⚠️ Der Fachbonus muss hier **denselben** Cast tragen wie dort. Ohne
# `CAST(... AS double precision)` leitet PostgreSQL den Parametertyp aus `ELSE 0` ab,
# rundet den Bonus auf 0 — und der Prüfsatz bescheinigte einer Änderung, dass sie nichts
# bewirkt, obwohl in Wahrheit nur die Messung kaputt wäre.
_SQL = """
SELECT c.id, c.title, c.content_type, s.name AS fach,
       coalesce(c.metadata->>'kompetenz_nr', c.metadata->>'nr', '') AS nr,
       1 - (c.embedding <=> CAST($1 AS vector)) AS sim
FROM context_nodes c
LEFT JOIN subjects s ON s.id = c.subject_id
WHERE c.status = 'active'
  AND c.embedding IS NOT NULL
  AND c.read_scope IN ('global', 'school', 'subject', 'group')
ORDER BY (c.embedding <=> CAST($1 AS vector))
       - CASE WHEN c.subject_id = $3
              THEN CAST($4 AS double precision)
              ELSE 0 END
LIMIT $2
"""


@dataclass
class Fall:
    frage: str
    fach: str | None = None          # Fach, aus dem der beste Treffer kommen soll
    chat_fach: str | None = None     # Fach der Konversation, in der gefragt wird
    knoten: str | None = None
    notiz: str | None = None


@dataclass
class Treffer:
    id: str
    titel: str
    content_type: str
    fach: str | None
    nr: str
    sim: float


@dataclass
class Lauf:
    treffer: list[Treffer]
    ms: float
    planart: str  # 'exakt' | 'Index' | '?'


@dataclass
class Ergebnis:
    fall: Fall
    index: Lauf
    exakt: Lauf
    produktiv: list[Treffer]
    nachschlagen: bool
    recall: float
    fach_ok: bool | None
    rang: int | None
    # Abschnittsgrößen des Umschlags (ADR-017). AP4 und AP6 messen daran, ob eine
    # Änderung am Matching thematische Anfragen mit Namensträgern überschwemmt.
    ident_n: int = 0
    thema_n: int = 0
    operatoren_top3: int = 0
    warnungen: list[str] = field(default_factory=list)


def _dsn() -> str:
    """`settings.database_url` für asyncpg — ohne SQLAlchemy-Treiberpräfix.

    asyncpg wird hier direkt verwendet, nicht die App-Session: Der Prüfsatz muss den
    Ausführungsplan steuern (`enable_indexscan`) und den Statement-Cache abschalten
    können. Beides geht über die ORM-Schicht nicht verlässlich.
    """
    url = settings.database_url
    for praefix in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql+psycopg2://"):
        if url.startswith(praefix):
            return "postgresql://" + url[len(praefix):]
    return url


def _planart(plan: str) -> str:
    if "Seq Scan" in plan:
        return "exakt"
    if INDEXNAME in plan:
        return "Index"
    return "?"


async def _suche(
    dsn: str, vektor: str, top_k: int, *, exakt: bool, subject_id: int | None = None
) -> Lauf:
    """Eine Messung auf einer **frischen** Verbindung, ohne Statement-Cache."""
    con = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        if exakt:
            await con.execute("SET enable_indexscan = off")
            await con.execute("SET enable_bitmapscan = off")
        args = (vektor, top_k, subject_id, FACHBONUS)
        plan = "\n".join(
            r[0] for r in await con.fetch("EXPLAIN (COSTS OFF) " + _SQL, *args)
        )
        t0 = time.perf_counter()
        rows = await con.fetch(_SQL, *args)
        ms = (time.perf_counter() - t0) * 1000
    finally:
        await con.close()
    return Lauf(
        treffer=[
            Treffer(
                id=str(r["id"]), titel=r["title"] or "", content_type=r["content_type"] or "",
                fach=r["fach"], nr=r["nr"] or "", sim=float(r["sim"]),
            )
            for r in rows
        ],
        ms=ms,
        planart=_planart(plan),
    )


def _rang(treffer: list[Treffer], knoten: str | None) -> int | None:
    """Platz des ersten Treffers, der zum erwarteten Knoten passt.

    Verglichen wird gegen die Kompetenznummer **oder** gegen den Titel; damit taugt das
    Feld sowohl für `3.3.2(1)` als auch für ein Stichwort wie `Pythagoras`. Mehrere
    Fassungen derselben Kompetenz zählen als ein Treffer — der beste Platz gewinnt.
    """
    if not knoten:
        return None
    gesucht = knoten.strip().lower()
    for i, t in enumerate(treffer, 1):
        if t.nr.strip().lower() == gesucht or gesucht in t.titel.lower():
            return i
    return None


def _bewerte(
    fall: Fall, index: Lauf, exakt: Lauf, produktiv: list[Treffer],
    ident_n: int, thema_n: int,
) -> Ergebnis:
    nachschlagen = ident_n > 0
    ids_exakt = {t.id for t in exakt.treffer}
    ids_index = {t.id for t in index.treffer}
    recall = len(ids_index & ids_exakt) / len(ids_exakt) if ids_exakt else 0.0

    warnungen: list[str] = []
    if fall.knoten and _rang(produktiv, fall.knoten) is None:
        warnungen.append(
            f"erwarteter Knoten '{fall.knoten}' nicht in der Trefferliste — entweder von "
            f"ähnlicheren Knoten verdrängt (dann ist der Fall echt) oder nicht im Bestand "
            f"(dann stimmt die Erwartung nicht)"
        )
    if index.planart == exakt.planart == "exakt":
        warnungen.append("kein Vektorindex im Einsatz — beide Läufe sind identisch")

    return Ergebnis(
        fall=fall, index=index, exakt=exakt, produktiv=produktiv,
        nachschlagen=nachschlagen, recall=recall,
        ident_n=ident_n, thema_n=thema_n,
        fach_ok=(produktiv[0].fach == fall.fach) if (fall.fach and produktiv) else None,
        rang=_rang(produktiv, fall.knoten),
        operatoren_top3=sum(1 for t in produktiv[:3] if t.content_type == "operator"),
        warnungen=warnungen,
    )


def _spanne(lauf: Lauf) -> float:
    """Abstand zwischen bestem und schlechtestem Treffer der Liste.

    Eine Liste, deren Werte alle beieinanderliegen, trennt nicht — dort entscheidet
    Rauschen über die Reihenfolge. Der Wert sagt nichts über die absolute Güte.
    """
    if len(lauf.treffer) < 2:
        return 0.0
    return lauf.treffer[0].sim - lauf.treffer[-1].sim


def _z(wert: bool | None) -> str:
    return "·" if wert is None else ("✓" if wert else "✗")


def _r(rang: int | None) -> str:
    return "—" if rang is None else str(rang)


def _ausgabe(ergebnisse: list[Ergebnis], top_k: int, details: bool) -> None:
    print()
    print(f"  {'Anfrage':<40}{'Chat-Fach':<14}{'Recall':>7}{'Name':>6}{'Thema':>6}"
          f"{'Fach@1':>8}{'Rang':>6}{'Spanne':>8}")
    print("  " + "─" * 95)
    for e in ergebnisse:
        frage = e.fall.frage if len(e.fall.frage) <= 39 else e.fall.frage[:38] + "…"
        chat = (e.fall.chat_fach or "—")[:13]
        print(
            f"  {frage:<40}{chat:<14}{e.recall*100:>6.0f}%"
            f"{(str(e.ident_n) if e.ident_n else '·'):>6}{e.thema_n:>6}"
            f"{_z(e.fach_ok):>8}{_r(e.rang):>6}{_spanne(e.exakt):>8.3f}"
        )

    n = len(ergebnisse)
    mit_fach = [e for e in ergebnisse if e.fall.fach]
    mit_knoten = [e for e in ergebnisse if e.fall.knoten]
    print("  " + "─" * 95)
    print(f"\n  {n} {'Fall' if n == 1 else 'Fälle'} · Recall@{top_k} im Mittel "
          f"{sum(e.recall for e in ergebnisse)/n*100:.0f} %")
    if mit_fach:
        print(f"  Richtiges Fach auf Platz 1:   "
              f"{sum(1 for e in mit_fach if e.fach_ok):>2}/{len(mit_fach)}")
    if mit_knoten:
        raenge = [e.rang for e in mit_knoten if e.rang]
        print(f"  Erwarteter Knoten gefunden:   {len(raenge):>2}/{len(mit_knoten)}"
              + (f"   (mittlerer Rang {sum(raenge)/len(raenge):.1f})" if raenge else ""))
    print(f"  Namensträger gefunden:        "
          f"{sum(1 for e in ergebnisse if e.ident_n):>2}/{n}"
          f"   (größter Abschnitt: {max((e.ident_n for e in ergebnisse), default=0)})")
    # Wächter für AP4: Eine thematische Anfrage soll keinen großen Namensträger-Block
    # bekommen. „Thematisch" heißt hier: Der Prüfsatz erwartet einen Fachtreffer.
    thematische = [e for e in ergebnisse if e.fall.fach and e.ident_n]
    if thematische:
        print(f"  davon thematische Fälle:      {len(thematische):>2}"
              f"   (größter Abschnitt: {max(e.ident_n for e in thematische)})")
    mit_op = [e for e in ergebnisse if e.operatoren_top3]
    print(f"  Operatoren unter den Top-3 (exakt): {sum(e.operatoren_top3 for e in ergebnisse)} "
          f"in {len(mit_op)} von {n} Fällen")
    # Enthält die Planung, weil jede Messung eine frische Verbindung ohne Statement-Cache
    # nimmt (siehe Modulkopf). Für einen Geschwindigkeitsvergleich taugen die Werte
    # deshalb nur grob — sie liegen über dem, was der laufende Betrieb sieht.
    print(f"  Laufzeit im Mittel (inkl. Planung):  Index "
          f"{sum(e.index.ms for e in ergebnisse)/n:.0f} ms  ·  "
          f"exakt {sum(e.exakt.ms for e in ergebnisse)/n:.0f} ms")

    warnungen = [(e.fall.frage, w) for e in ergebnisse for w in e.warnungen]
    if warnungen:
        print("\n  Hinweise:")
        gesehen: set[str] = set()
        for frage, w in warnungen:
            if w.startswith("kein Vektorindex"):
                if w in gesehen:
                    continue
                gesehen.add(w)
                print(f"    · {w}")
            else:
                print(f"    · {frage}: {w}")

    if details:
        for e in ergebnisse:
            print(f"\n  ── {e.fall.frage}")
            print(f"     produktiv{' (Nachschlagen)' if e.nachschlagen else ''}")
            for i, t in enumerate(e.produktiv[:5], 1):
                print(f"       {i}. {str(t.fach or '—'):<18}{t.content_type:<14}"
                      f"{t.titel[:52]}")
            for name, lauf in (("Index", e.index), ("exakt", e.exakt)):
                print(f"     {name} [{lauf.planart}], {lauf.ms:.0f} ms")
                for i, t in enumerate(lauf.treffer[:5], 1):
                    print(f"       {i}. {t.sim:.3f}  {str(t.fach or '—'):<18}"
                          f"{t.content_type:<14}{t.titel[:52]}")


async def _produktiv(
    frage: str, top_k: int, subject_id: int | None
) -> tuple[list[Treffer], int, int]:
    """Die echte Suchfunktion — keine Nachbildung.

    Der Prüfsatz spiegelt für den Recall-Vergleich rohes SQL (er braucht Kontrolle über
    den Ausführungsplan). Für die inhaltliche Bewertung wäre eine zweite Nachbildung
    gefährlich: Sie würde beim nächsten Umbau der Suche stillschweigend etwas anderes
    messen als das, was läuft.

    Bewertet wird der Umschlag in Lesereihenfolge: erst die Namensträger, dann die
    nächstliegenden Bausteine — die Reihenfolge, in der auch Modell und Oberfläche sie
    sehen. Zurück kommen zusätzlich die beiden Abschnittsgrößen.
    """
    from app.context.search import Suchprofil, suche
    from app.db.session import AsyncSessionLocal

    profil = Suchprofil(
        pseudonym="pruefsatz",
        subject_id=subject_id,
        identifikation=top_k,
        thematisch=top_k,
    )
    async with AsyncSessionLocal() as db:
        ergebnis = await suche(frage, profil, db)

    treffer = ergebnis.identifikation.treffer + ergebnis.thematisch.treffer
    return [
        Treffer(id=t["node_id"], titel=t.get("title") or "",
                content_type=t.get("content_type") or "", fach=t.get("fach"),
                nr=t.get("nr") or "", sim=0.0)
        for t in treffer
    ], ergebnis.identifikation.geliefert, ergebnis.thematisch.geliefert


async def _fach_ids(dsn: str) -> dict[str, int]:
    con = await asyncpg.connect(dsn, statement_cache_size=0)
    try:
        return {r["name"]: r["id"] for r in await con.fetch("SELECT id, name FROM subjects")}
    finally:
        await con.close()


def _lade(pfad: Path) -> tuple[list[Fall], int]:
    daten = yaml.safe_load(pfad.read_text(encoding="utf-8")) or {}
    faelle = [
        Fall(frage=f["frage"], fach=f.get("fach"), chat_fach=f.get("chat_fach"), knoten=(
            None if f.get("knoten") is None else str(f["knoten"])
        ), notiz=f.get("notiz"))
        for f in daten.get("faelle", [])
    ]
    return faelle, int(daten.get("top_k", 10))


async def run(faelle: list[Fall], top_k: int, details: bool, json_pfad: Path | None) -> int:
    dsn = _dsn()
    ergebnisse: list[Ergebnis] = []
    fach_ids = await _fach_ids(dsn)
    unbekannt = {f.chat_fach for f in faelle if f.chat_fach and f.chat_fach not in fach_ids}
    if unbekannt:
        print(f"  ⚠️  Unbekanntes chat_fach im Prüfsatz: {sorted(unbekannt)} — "
              f"diese Fälle laufen ohne Fachbezug.", file=sys.stderr)

    for fall in faelle:
        vektor_werte = await generate_embedding(fall.frage)
        vektor = "[" + ",".join(f"{v:.10f}" for v in vektor_werte) + "]"
        subject_id = fach_ids.get(fall.chat_fach) if fall.chat_fach else None
        # Der Index-Lauf zuerst: Er soll den Plan sehen, den PostgreSQL im Normalbetrieb
        # wählt — unbeeinflusst von den Planer-Schaltern des exakten Laufs.
        index = await _suche(dsn, vektor, top_k, exakt=False, subject_id=subject_id)
        exakt = await _suche(dsn, vektor, top_k, exakt=True, subject_id=subject_id)
        if exakt.planart != "exakt":
            print(f"  ⚠️  '{fall.frage}': exakter Lauf verwendete Plan '{exakt.planart}' — "
                  f"die Messung ist wertlos. Abbruch.", file=sys.stderr)
            return 2
        produktiv, ident_n, thema_n = await _produktiv(fall.frage, top_k, subject_id)
        ergebnisse.append(_bewerte(fall, index, exakt, produktiv, ident_n, thema_n))

    _ausgabe(ergebnisse, top_k, details)

    if json_pfad:
        json_pfad.write_text(json.dumps([
            {
                "frage": e.fall.frage, "fach": e.fall.fach,
                "chat_fach": e.fall.chat_fach, "knoten": e.fall.knoten,
                "recall": e.recall, "fach_ok": e.fach_ok, "rang": e.rang,
                "nachschlagen": e.nachschlagen, "operatoren_top3": e.operatoren_top3,
                "planart_index": e.index.planart, "ms_index": e.index.ms,
                "ms_exakt": e.exakt.ms, "spanne_exakt": _spanne(e.exakt),
                "top_exakt": [
                    {"fach": t.fach, "typ": t.content_type, "nr": t.nr,
                     "titel": t.titel, "sim": t.sim}
                    for t in e.exakt.treffer[:5]
                ],
            }
            for e in ergebnisse
        ], ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n  Ergebnisse geschrieben: {json_pfad}")

    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        description="Prüfsatz für die semantische Suche (Recall, Fachtreffer, Rang)"
    )
    p.add_argument("--pruefsatz", type=Path, default=PRUEFSATZ_VORGABE,
                   help=f"YAML mit den Prüffällen (Vorgabe: {PRUEFSATZ_VORGABE})")
    p.add_argument("--frage", help="Einzelne Anfrage statt des Prüfsatzes")
    p.add_argument("--fach", help="Erwartetes Fach zu --frage")
    p.add_argument("--knoten", help="Erwartete Kompetenznummer oder Titelstück zu --frage")
    p.add_argument("--chat-fach", dest="chat_fach",
                   help="Fach der Konversation zu --frage (dessen Treffer werden vorgezogen)")
    p.add_argument("--top-k", type=int, help="Trefferzahl (Vorgabe aus dem Prüfsatz)")
    p.add_argument("--details", action="store_true", help="Trefferlisten mit ausgeben")
    p.add_argument("--json", type=Path, help="Ergebnisse zusätzlich als JSON schreiben")
    args = p.parse_args()

    if args.frage:
        faelle = [Fall(frage=args.frage, fach=args.fach, chat_fach=args.chat_fach,
                       knoten=args.knoten)]
        top_k = args.top_k or 10
    else:
        if not args.pruefsatz.exists():
            p.error(f"Prüfsatz nicht gefunden: {args.pruefsatz}")
        faelle, top_k = _lade(args.pruefsatz)
        if not faelle:
            p.error(f"Prüfsatz enthält keine Fälle: {args.pruefsatz}")
        top_k = args.top_k or top_k

    sys.exit(asyncio.run(run(faelle, top_k, args.details, args.json)))


if __name__ == "__main__":
    main()
