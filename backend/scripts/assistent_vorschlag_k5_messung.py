"""K5 in der Assistenten-Konversation — mit dem Dienst selbst, ohne Chat.

Ruft `vorschlag.vorschlagen` so auf wie der Chat (Vorfilter < `IM_ASSISTENTEN`, dann der
Klassifikator mit der letzten Assistenten-Nachricht `vorher`), nur ohne Ruheregel und ohne
Antwort des Assistenten (K9 misst `assistent_vorschlag_chatmessung.py`). Kosten: ein
Klassifikator-Aufruf je Fall mit Kandidat im Band, über das Systemkonto.

    cd backend && venv/bin/python scripts/assistent_vorschlag_k5_messung.py \\
        --ziel "<Vault>/Plaene/Messungen-Vorschlag" --lauf k5-2

Ausgewertet wird je Art (bleiben / wechsel) und getrennt nach Herkunft (`frisch`). Richtig ist
ein Fall, wenn das Ergebnis `erwartet` (bei `wechsel` mit dem richtigen Ziel) ist oder in `darf`
steht.

Dazu offline der Vorfilter mit dem **Mittel der drei nächsten Beispiele** statt des besten
(Jan, 29.10.2026): je Schwelle, wie viele Aufrufe es gäbe und ob das richtige Ziel im Band läge.
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parent))

#: Schwellen für den Vorfilter aus dem Mittel (das Mittel liegt immer über dem besten Beispiel).
RASTER_MITTEL = (0.45, 0.50, 0.55)
HERKUNFT = {None: "bisher", True: "frisch (k5-1)", 3: "Folgefragen mit fremdem Fachwort",
            4: "Gegenprobe (frisch nach der Prompt-Schärfung)"}


def richtig(fall: dict, ergebnis: str, ziel: str | None) -> bool:
    return ((ergebnis == fall["erwartet"] and (ergebnis != "wechsel" or ziel == fall.get("wechsel_zu")))
            or ergebnis in (fall.get("darf") or []))


def vorfilter(zeilen: list[dict], schluessel: str, schwelle: float) -> dict:
    """Offline: Aufrufe bei `bleiben`, Ziel im Band bei `wechsel` — mit `abstand` oder `mittel`."""
    aufrufe = sum(1 for z in zeilen if z["erwartet"] == "bleiben"
                  and any(k[schluessel] < schwelle for k in z["kandidaten"]))
    wechsel = [z for z in zeilen if z["erwartet"] == "wechsel"]
    im_band = sum(1 for z in wechsel if any(k["name"] == z.get("wechsel_zu") and k[schluessel] < schwelle
                                            for k in z["kandidaten"]))
    return {"aufrufe": aufrufe, "bleiben": sum(1 for z in zeilen if z["erwartet"] == "bleiben"),
            "im_band": im_band, "wechsel": len(wechsel)}


async def main_async(args) -> None:
    import httpx
    import sqlalchemy as sa

    from app.assistants import vorschlag as v
    from app.assistants.sichtbarkeit import Zugang
    from app.config import settings
    from app.context.embedding import generate_embeddings
    from app.db.models import Assistant
    from app.db.session import AsyncSessionLocal

    satz = yaml.safe_load((HIER / "szenarien/assistent_vorschlag.yaml").read_text(encoding="utf-8"))
    faelle = satz["in_assistent"]
    vektoren = (await generate_embeddings([f["text"] for f in faelle])).vektoren
    kosten_sql = sa.text("SELECT coalesce(sum(kosten_usd), 0) FROM system_spend WHERE tag = current_date")
    zeilen = []
    async with AsyncSessionLocal() as db, httpx.AsyncClient(timeout=30, verify=settings.litellm_verify_ssl) as client:
        vorher_kosten = float((await db.execute(kosten_sql)).scalar() or 0)
        ids = {n: i for i, n in (await db.execute(sa.select(Assistant.id, Assistant.name))).all()}
        for f, vek in zip(faelle, vektoren):
            zugang = Zugang(pseudonym="k5-messung", rollen=frozenset({"student"}), gruppen=frozenset(),
                            lehrgruppen=frozenset(), stufe=f["stufe"])
            kandidaten, _ = await v._kandidaten(db, zugang, vek, ids[f["aktuell"]])
            try:
                r = await v.vorschlagen(db, nachricht=f["text"], vektor=vek, zugang=zugang,
                                        aktuell_id=ids[f["aktuell"]], schon_vorgeschlagen=set(),
                                        konversationsfach=None, client=client, letzte_antwort=f.get("vorher"))
                fehler = None
            except Exception as e:           # ein Fehler im Dienst heißt im Chat: kein Vorschlag
                r, fehler = None, type(e).__name__
            ergebnis, ziel = ("wechsel", r.optionen[0].name) if r and r.optionen else ("bleiben", None)
            band = v.im_assistenten_band(kandidaten)
            zeilen.append({**f, "ergebnis": ergebnis, "ziel": ziel, "richtig": richtig(f, ergebnis, ziel),
                           "aufruf": bool(band), "fehler": fehler, "roh": (r.debug.get("klassifikator") if r else None),
                           "band": [k.name for k in band],
                           "kandidaten": [{"name": k.name, "abstand": k.abstand, "mittel": k.mittel}
                                          for k in kandidaten.values()]})
        db.expire_all()
        kosten = float((await db.execute(kosten_sql)).scalar() or 0) - vorher_kosten

    def bilanz(auswahl):
        aus = {}
        for art in ("bleiben", "wechsel"):
            teil = [z for z in auswahl if z["erwartet"] == art]
            aus[art] = (sum(z["richtig"] for z in teil), len(teil))
        return aus

    t = [f"# K5 in der Assistenten-Konversation — Lauf {args.lauf}", "",
         f"- **Datum:** {datetime.now(timezone.utc).astimezone().strftime('%d.%m.%Y, %H:%M')}",
         f"- **Regel:** Vorfilter bestes Beispiel < {v.IM_ASSISTENTEN}, dann Klassifikator "
         f"`{settings.vorschlag_model}` mit der letzten Assistenten-Nachricht; kein „beenden“",
         f"- **Fälle:** {len(zeilen)}; Aufrufe {sum(z['aufruf'] for z in zeilen)}; "
         f"Fehler {sum(1 for z in zeilen if z['fehler'])}; Kosten {kosten:.5f} USD".replace(".", ","), "",
         "## Ergebnis", ""]
    for name, auswahl in [("alle", zeilen)] + [
            (titel, [z for z in zeilen if z.get("frisch") == h]) for h, titel in HERKUNFT.items()]:
        b = bilanz(auswahl)
        t.append(f"- **{name}:** bleiben {b['bleiben'][0]}/{b['bleiben'][1]}, wechsel {b['wechsel'][0]}/{b['wechsel'][1]}")
    t += ["", "## Fehler", "", "| Herkunft | Nachricht | aktuell | erwartet | Ergebnis | Band | Klassifikator |",
          "|---|---|---|---|---|---|---|"]
    for z in zeilen:
        if z["richtig"]:
            continue
        soll = z["erwartet"] + (f" → {z['wechsel_zu']}" if z.get("wechsel_zu") else "")
        ist = z["ergebnis"] + (f" → {z['ziel']}" if z["ziel"] else "") + (f" ({z['fehler']})" if z["fehler"] else "")
        roh = (z["roh"] or "").replace("|", "/").replace("\n", " ")[:80]
        t.append(f"| {HERKUNFT.get(z.get('frisch'), z.get('frisch'))} | {z['text'][:60]} | {z['aktuell']} | {soll} "
                 f"| {ist} | {', '.join(z['band'][:3])} | {roh} |")
    t += ["", "## Vorfilter offline: bestes Beispiel oder Mittel der drei nächsten", "",
          "Aufrufe = `bleiben`-Fälle mit Kandidat im Band; im Band = `wechsel`-Fälle, deren Ziel im Band liegt.", "",
          "| Maß | Schwelle | Aufrufe bei bleiben | Ziel im Band bei wechsel |", "|---|---|---|---|"]
    for schluessel, schwellen in (("abstand", (0.45,)), ("mittel", RASTER_MITTEL)):
        for s in schwellen:
            b = vorfilter(zeilen, schluessel, s)
            t.append(f"| {'bestes' if schluessel == 'abstand' else 'Mittel'} | {s:.2f} | "
                     f"{b['aufrufe']}/{b['bleiben']} | {b['im_band']}/{b['wechsel']} |".replace(".", ","))
    text = "\n".join(t) + "\n"
    if args.ziel:
        args.ziel.mkdir(parents=True, exist_ok=True)
        (args.ziel / f"vorschlag-{args.lauf}.md").write_text(text, encoding="utf-8")
        print(f"Protokoll: {args.ziel / f'vorschlag-{args.lauf}.md'}")
    print(text)


def main() -> None:
    p = argparse.ArgumentParser(description="K5 in der Assistenten-Konversation (Dienst, ohne Chat)")
    p.add_argument("--lauf", default="k5-2")
    p.add_argument("--ziel", type=Path)
    asyncio.run(main_async(p.parse_args()))


if __name__ == "__main__":
    main()
