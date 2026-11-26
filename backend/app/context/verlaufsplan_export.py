"""Export eines Jahresverlaufsplans als PDF, DOCX oder ODT (Päckchen BD Teil B, Schritt 7).

Für die Fachschaftsakte, im Querformat: Kopf (Schule, Titel, Stand, Fach · Klasse · Schuljahr ·
Wochenstunden · Planungsart, Wochen), eine Tabelle der Abschnitte mit Wochen, Zeitraum, Bezug,
Hinweisen und Notiz, darunter die Stundenbilanz je Kapitel und was noch keinen Abschnitt hat.

Grundlage ist :func:`app.context.verlaufsplan.kompakt` — dieselbe Fassung, die ein KI-Programm
liest, mit Titeln auch archivierter Bezüge. :func:`aufbereiten` macht daraus Zeilen in Klartext
(rein, ohne Datenbank); PDF (weasyprint, Vorlage `templates/verlaufsplan_pdf.html`) und
DOCX/ODT (Pandoc-AST, `app.export.office`) setzen nur noch.
"""
from __future__ import annotations

import os
from datetime import date
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.context.verlaufsplan import NICHT_MEHR_IM_CURRICULUM

#: Sätze unter der Bilanz, wie auf der Planseite (`VerlaufsplanBilanz.svelte`)
BAND_HINWEIS = "Das Curriculum gilt für mehrere Stufen; „Soll“ ist die Stundenzahl für das ganze Band."
OHNE_STUNDEN_HINWEIS = "Ohne Wochenstunden im Curriculum zählt die Bilanz nur Wochen."

#: Richtgröße eines Abschnitts (wie `RICHTGROESSE` in `lib/verlaufsplan.js`)
RICHTGROESSE = 6


def _tag(iso: Optional[str]) -> str:
    if not iso:
        return ""
    j, m, t = str(iso).split("-")
    return f"{t}.{m}."


def _datum(iso: Optional[str]) -> str:
    if not iso:
        return ""
    j, m, t = str(iso).split("-")
    return f"{t}.{m}.{j}"


def _wochen(n) -> str:
    return f"{n} {'Woche' if n == 1 else 'Wochen'}"


def hinweise(a: dict) -> list[str]:
    """Wie `hinweise()` in `lib/verlaufsplan.js` — Export und Planseite sagen dasselbe."""
    aus = [f"über die {f}" for f in a.get("ueber_ferien") or []]
    if a.get("vor_ferien"):
        aus.append(f"endet vor den {a['vor_ferien']}")
    if a.get("halbjahreswechsel"):
        aus.append("Halbjahreswechsel")
    if (a.get("wochen") or 0) > RICHTGROESSE:
        aus.append(f"länger als {RICHTGROESSE} Wochen")
    if a.get("ausserhalb"):
        aus.append(f"{_wochen(a['ausserhalb'])} nach Schuljahresende")
    return aus


def _bezug(a: dict) -> str:
    if a.get("puffer"):
        return "Puffer"
    eintraege = a.get("lernsequenzen") if "lernsequenzen" in a else a.get("kapitel") or []
    teile = []
    for e in eintraege:
        t = e["titel"]
        # Ohne gefundenen Titel heißt er schon so — den Zusatz dann nicht noch einmal
        if e.get("kapitel") and e["kapitel"] != NICHT_MEHR_IM_CURRICULUM and "lernsequenzen" in a:
            t = f"{t} ({e['kapitel']})"
        if e.get("nicht_mehr_im_curriculum") and t != NICHT_MEHR_IM_CURRICULUM:
            t += f" – {NICHT_MEHR_IM_CURRICULUM}"
        teile.append(t)
    return "; ".join(teile)


def _zeitraum(a: dict) -> tuple[str, str]:
    """(„Woche 1–4“, „15.09.–10.10.“); leer ohne Kalender."""
    if a.get("von_woche") is None:
        return "", ""
    woche = f"Woche {a['von_woche']}" if a["von_woche"] == a["bis_woche"] else f"Woche {a['von_woche']}–{a['bis_woche']}"
    von, bis = _tag(a.get("beginn")), _tag(a.get("ende"))
    tage = "" if not von else (von if von == bis or not bis else f"{von}–{bis}")
    return woche, tage


def stand(k: dict, heute: Optional[date] = None) -> str:
    """„Beschlossen am 03.10.2026“ oder „Entwurf, Stand 26.11.2026“."""
    if k.get("status") == "entwurf":
        return f"Entwurf, Stand {(heute or date.today()).strftime('%d.%m.%Y')}"
    return f"Beschlossen am {_datum(k['beschlossen_am'])}" if k.get("beschlossen_am") else "Beschlossen"


def aufbereiten(k: dict, *, heute: Optional[date] = None) -> dict:
    """Kopf, Zeilen und Bilanz in Klartext aus der kompakten Fassung."""
    meta = [k.get("fach") or "", f"Klasse {k.get('stufe')}", f"Schuljahr {k.get('schuljahr')}"]
    if k.get("wochenstunden"):
        meta.append(f"{k['wochenstunden']} Wochenstunden")
    meta.append(k.get("planungsart") or "")
    summe = None
    if k.get("unterrichtswochen") is not None:
        # Puffer zählen zu den verplanten Wochen (`lage.belegt`)
        verplant = f"{k.get('verplant', 0)} verplant"
        if k.get("puffer_wochen"):
            verplant += f" (davon {k['puffer_wochen']} Puffer)"
        teile = [f"{k['unterrichtswochen']} Unterrichtswochen", verplant]
        if k.get("frei"):
            teile.append(f"{k['frei']} frei")
        if k.get("nach_schuljahresende"):
            teile.append(f"{k['nach_schuljahresende']} nach Schuljahresende")
        summe = ", ".join(teile)
    zeilen = [{
        "nr": a["nr"], "thema": a.get("titel") or ("Puffer" if a.get("puffer") else "ohne Thema"),
        "puffer": bool(a.get("puffer")), "wochen": a.get("wochen"),
        "woche": _zeitraum(a)[0], "tage": _zeitraum(a)[1], "zeitraum": ", ".join(t for t in _zeitraum(a) if t),
        "bezug": _bezug(a), "hinweise": ", ".join(hinweise(a)), "notiz": a.get("notiz") or "",
    } for a in k.get("abschnitte") or []]
    bilanz = [{
        "titel": b.get("kapitel") or b.get("lernsequenz") or "",
        "fremd": bool(b.get("nicht_mehr_im_curriculum"))
                 and (b.get("kapitel") or b.get("lernsequenz")) != NICHT_MEHR_IM_CURRICULUM,
        "soll": "" if b.get("soll_stunden") is None else str(b["soll_stunden"]),
        "geplant": "" if b.get("geplant_stunden") is None else f"{b['geplant_stunden']:g}",
        "wochen": "" if b.get("wochen") is None else f"{b['wochen']:g}",
    } for b in k.get("bilanz") or []]
    fehlt = list(k.get("kapitel_ohne_abschnitt") or [])
    return {
        "titel": k.get("titel") or "", "stand": stand(k, heute), "entwurf": k.get("status") == "entwurf",
        "meta": " · ".join(m for m in meta if m), "summe": summe, "hinweis": k.get("hinweis"),
        "zeilen": zeilen, "bilanz": bilanz,
        "bilanz_hinweise": [h for h, gilt in ((BAND_HINWEIS, k.get("band")),
                                               (OHNE_STUNDEN_HINWEIS, not k.get("wochenstunden"))) if gilt]
                           if bilanz else [],
        "kapitel_ohne_abschnitt": fehlt,
        "lernsequenzen_ohne_abschnitt": list(k.get("lernsequenzen_ohne_abschnitt") or []),
    }


_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "Ä": "Ae", "Ö": "Oe", "Ü": "Ue", "ß": "ss"})


def dateiname(k: dict, fmt: str) -> str:
    """Nur ASCII: Starlette schreibt Header in Latin-1, ein Fachname mit „č“ endete sonst in 500."""
    import unicodedata

    roh = unicodedata.normalize("NFKD", (k.get("fach") or "plan").translate(_UMLAUTE))
    fach = "".join(c for c in roh.encode("ascii", "ignore").decode() if c.isalnum()) or "plan"
    sj = (k.get("schuljahr") or "").replace("/", "-")
    return f"jahresverlaufsplan_{fach}_{k.get('stufe')}_{sj}.{fmt}"


# ── PDF ───────────────────────────────────────────────────────────────────────

TEMPLATES = os.path.join(os.path.dirname(__file__), "templates")


def pdf_html(k: dict) -> str:
    """Das HTML für weasyprint (eigene Funktion, damit Tests das Layout prüfen können)."""
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    from app.config import settings

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"]))
    return env.get_template("verlaufsplan_pdf.html").render(schule=settings.export_school_name or "", plan=aufbereiten(k))


async def render_pdf(k: dict) -> bytes:
    import asyncio

    import weasyprint

    html = pdf_html(k)
    return await asyncio.to_thread(lambda: weasyprint.HTML(string=html, base_url=TEMPLATES).write_pdf())


# ── DOCX / ODT ────────────────────────────────────────────────────────────────

async def render_office(db: AsyncSession, k: dict, fmt: str, reference_doc: Optional[str] = None) -> bytes:
    """Querformat wie das PDF. Alles Klartext, auch die Notiz (ein einzeiliges Feld): Als Markdown
    würde „# …“ zur Überschrift und „<Name>“ verschwände — PDF und Seite zeigen sie roh."""
    from app.config import settings
    from app.export import office as o

    p = aufbereiten(k)
    _, api = await o.markdown_zu_bloecken(db, {})   # nur die API-Fassung von Pandoc

    def zelle(s: str) -> list:
        return [o.schlicht(o.text(s))] if s else []

    dok = []
    if settings.export_school_name:
        dok.append(o.absatz(o.text(settings.export_school_name)))
    dok.append(o.ueberschrift(1, o.text(p["titel"])))
    dok.append(o.absatz([o.fett(o.text(p["stand"]))]))
    dok.append(o.absatz(o.text(p["meta"])))
    if p["summe"]:
        dok.append(o.absatz(o.text(p["summe"])))
    if p["hinweis"]:
        dok.append(o.absatz(o.text(p["hinweis"])))
    dok.append(o.tabelle(
        ["Nr.", "Abschnitt", "Wochen", "Zeitraum", "Sequenzen/Kapitel", "Hinweise", "Notiz"],
        [[zelle(str(z["nr"])), zelle(z["thema"]), zelle(str(z["wochen"] or "")), zelle(z["zeitraum"]),
          zelle(z["bezug"]), zelle(z["hinweise"]), zelle(z["notiz"])]
         for z in p["zeilen"]],
        breiten=[0.04, 0.17, 0.06, 0.14, 0.27, 0.14, 0.18],
    ))
    if p["bilanz"]:
        dok += o.SEITENUMBRUCH   # die Bilanz auf eine eigene Seite (Jan 26.11.2026)
        dok.append(o.ueberschrift(2, o.text("Stunden je Kapitel")))
        dok += [o.absatz(o.text(h)) for h in p["bilanz_hinweise"]]
        dok.append(o.tabelle(
            ["Kapitel", "Soll (Std.)", "Geplant (Std.)", "Wochen"],
            [[zelle(b["titel"] + (" – nicht mehr im Curriculum" if b["fremd"] else "")),
              zelle(b["soll"]), zelle(b["geplant"]), zelle(b["wochen"])] for b in p["bilanz"]],
            breiten=[0.55, 0.15, 0.15, 0.15],
        ))
    if p["kapitel_ohne_abschnitt"]:
        dok.append(o.absatz([o.fett(o.text("Kapitel ohne Abschnitt:")), {"t": "Space"},
                             *o.text(", ".join(p["kapitel_ohne_abschnitt"]))]))
    if p["lernsequenzen_ohne_abschnitt"]:
        dok.append(o.absatz([o.fett(o.text("Lernsequenzen ohne Abschnitt:")), {"t": "Space"},
                             *o.text(", ".join(p["lernsequenzen_ohne_abschnitt"]))]))
    return await o.dokument_zu_office(dok, api_version=api, fmt=fmt, reference_doc=reference_doc, quer=True)
