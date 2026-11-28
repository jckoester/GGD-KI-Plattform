"""Vernetzung der Fächer mit Zeitachse (Päckchen BE, Teil A, Schritt 2).

Ein Fach steht in der Mitte; geliefert wird, was die Zeitachse braucht: die Stufen mit Schuljahr,
Fassung und Kalender, die Kapitel des Fachs und der mit ihm vernetzten Fächer samt Lage, die Bezüge
zwischen Kapiteln und die Leitperspektiven und Leitlinien der Kapitel des Fachs.

Entschieden (Jan, 28.11.2026, Plan `Vernetzung-Zeitachse-BE-Plan`):

- **Bezug (F1):** eine Absprache (AY Teil 2); ein Querverweis des Bildungsplans (`related_to`,
  beide Richtungen) von einer Kompetenz des einen Kapitels auf eine des anderen (`kompetenz`) oder
  auf einen Bereich, unter dem eine Kompetenz des anderen hängt (`bereich`, schwacher Bezug); ein
  eigener Verweis `#[…](ik:…)` in den Hinweisen zählt wie ein Querverweis. Benachbarte Kapitel
  desselben Curriculums zählen im eigenen Fach nicht. Geliefert werden nur Bezüge mit dem Fach in
  der Mitte (Befund 9: keine Bezüge zwischen zwei Spurfächern).
- **Fassung (F2):** veröffentlichte Curricula, mit `entwuerfe` tritt ein Entwurf an die Stelle
  seines Originals (wie die Leitlinien-Übersicht, AU F3). Je Stufe gilt die Fassung, die der
  Editionsfahrplan für Stufe und Schuljahr vorsieht (`aktive_bp_version`, F13) — im Übergangsjahr
  stehen für Kl. 8 sonst zwei Curricula übereinander.
- **Lage (F3, F13):** je Stufe der Jahresverlaufsplan ihres Schuljahrs (beschlossen, sonst der
  Entwurf; auch archivierte früherer Jahre), sonst geschätzt (`vernetzung_zeit`).
- **Leitperspektiven, Leitlinien (F6):** nur für Kapitel des Fachs in der Mitte, aus den Kanten
  `references` der Lernsequenzen, Aspekte zu ihrer Leitperspektive bzw. Leitlinie gefasst.

Leserecht wie die Leitlinien-Übersicht: Curricula mit offenem Lesebereich, Entwürfe nur mit
`darf_entwurf_lesen`. Jahresverlaufspläne lesen alle Lehrkräfte (`vp.LESBAR`); die Route
(Schritt 3) ist nur für Lehrkräfte.
"""
from __future__ import annotations

import uuid
from collections import defaultdict
from datetime import timedelta
from typing import Optional

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.context import verlaufsplan as vp
from app.context import vernetzung_zeit as vz
from app.context.absprachen import GEGENART, pruefung_dict
from app.context.curriculum_entwurf import ENTWURF, darf_entwurf_lesen
from app.context.editions import aktive_bp_version, parse_schuljahr_start
from app.context.leitlinien import LFDB_TYPEN
from app.context.querverweise import _SICHTBAR, _bereich_kompetenzen, _umlenken, kurztitel, nummer
from app.db.models import ContextEdge, ContextNode, Subject

_OFFEN = ("global", "school", "subject")
_LP_TYPEN = ("leitperspektive", "leitperspektive_aspekt", *LFDB_TYPEN)
_LL_TYPEN = ("leitbild", "leitbild_aspekt")
#: höchstens so viele Beispiele (Nummernpaare) je Bezug
BEISPIELE = 3
#: Unterrichtswochen, wenn für ein Schuljahr kein Kalender liegt und auch der laufende fehlt
WOCHEN_OHNE_KALENDER = 38


def _stufen_von(c: ContextNode) -> list[int]:
    if c.min_grade is None:
        return []
    return list(range(c.min_grade, (c.max_grade if c.max_grade is not None else c.min_grade) + 1))


def _fach_dict(s: Subject) -> dict:
    return {"id": s.id, "code": s.fach_code, "name": s.name, "color": s.color, "icon": s.icon}


async def _curricula(db: AsyncSession, user, status: tuple[str, ...], *, fach_id: Optional[int] = None,
                     stufen: Optional[tuple[int, int]] = None) -> list[ContextNode]:
    from app.auth.vorschau import eigenes_zaehlt

    q = sa.select(ContextNode).where(
        ContextNode.content_type == "curriculum", ContextNode.status.in_(status),
        ContextNode.min_grade.isnot(None),
        sa.or_(ContextNode.read_scope.in_(_OFFEN),
               sa.and_(sa.literal(eigenes_zaehlt(user.sub)), ContextNode.owner_pseudonym == user.sub)))
    if fach_id is not None:
        q = q.where(ContextNode.subject_id == fach_id)
    if stufen is not None:
        q = q.where(ContextNode.min_grade <= stufen[1],
                    sa.func.coalesce(ContextNode.max_grade, ContextNode.min_grade) >= stufen[0])
    return list((await db.execute(q.order_by(ContextNode.title))).scalars())


def _waehlen(kandidaten: list[ContextNode], geltend: Optional[str]) -> list[ContextNode]:
    """Die Curricula eines Fachs für eine Stufe: die geltende Fassung (ohne Fahrplan alle), ein
    Entwurf ersetzt sein Original, und je Band gewinnt der Entwurf."""
    passend = [c for c in kandidaten if geltend is None or (c.metadata_ or {}).get("bp_version") == geltend]
    ersetzt = {str((c.metadata_ or {}).get("kopie_von")) for c in passend
               if c.status == ENTWURF and (c.metadata_ or {}).get("kopie_von")}
    passend = [c for c in passend if str(c.id) not in ersetzt]
    je_band: dict = defaultdict(list)
    for c in passend:
        je_band[(c.metadata_ or {}).get("band")].append(c)
    aus = []
    for gruppe in je_band.values():
        entwuerfe = [c for c in gruppe if c.status == ENTWURF]
        aus.extend(entwuerfe or gruppe)
    return aus


def _jahr(schuljahr: str, aktuelles: str) -> dict:
    """Kalender eines Schuljahrs für die Achse: Unterrichtswochen, Ferien, Kalenderwochen,
    die laufende Woche. Ohne Kalenderdatei nur die Zahl der Wochen (vom laufenden Jahr geliehen)."""
    from app.budget.schulwochen import unterrichtswochen
    from app.planning.calendar import kalender_fuer
    from app.planning.verlaufsplan_zeit import ferienmarken

    cfg = kalender_fuer(schuljahr)
    if cfg is None:
        ersatz = kalender_fuer(aktuelles)
        n = len(unterrichtswochen(ersatz)) if ersatz else WOCHEN_OHNE_KALENDER
        return {"schuljahr": schuljahr, "kalender": False, "wochen": n, "ferien": [],
                "kalenderwochen": None, "heute_woche": None}
    wochen = unterrichtswochen(cfg)
    n = len(wochen)
    heute = vp.heute()
    heute_woche = None
    if schuljahr == aktuelles:
        heute_woche = next((w.index for w in wochen if w.montag <= heute < w.montag + timedelta(days=7)), None)
    return {
        "schuljahr": schuljahr, "kalender": True, "wochen": n,
        "ferien": [{"name": m.name, "nach_woche": m.nach_woche} for m in ferienmarken(cfg, wochen) if m.nach_woche < n],
        "kalenderwochen": [w.montag.isocalendar()[1] for w in wochen],
        "heute_woche": heute_woche,
    }


async def vernetzung(db: AsyncSession, user, fach_id: int, *, modus: str = vz.SCHULJAHR,
                     schuljahr: Optional[str] = None, bezugsstufe: Optional[int] = None,
                     entwuerfe: bool = False) -> dict:
    """Alles für die Zeitachse eines Fachs. `LookupError`, wenn es das Fach nicht gibt;
    `ValueError` bei widersprüchlichem Zeitraum."""
    fach = await db.get(Subject, fach_id)
    if fach is None:
        raise LookupError("Fach nicht gefunden")
    entwuerfe = entwuerfe and darf_entwurf_lesen(user)
    status = ("active", ENTWURF) if entwuerfe else ("active",)
    aktuelles = vp.aktuelles_schuljahr()

    eigene = await _curricula(db, user, status, fach_id=fach_id)
    stufen = sorted({s for c in eigene for s in _stufen_von(c)})
    leer = {"fach": _fach_dict(fach), "zeitraum": {"modus": modus, "schuljahr": schuljahr, "bezugsstufe": bezugsstufe,
                                                    "aktuelles_schuljahr": aktuelles, "entwuerfe": entwuerfe},
            "stufen": [], "faecher": [], "kapitel": [], "bezuege": [], "fach_absprachen": [], "leitlinien": {}}
    if not stufen:
        return leer
    if modus == vz.WEG and bezugsstufe is None:
        bezugsstufe = stufen[0]
    sj = vz.schuljahre(stufen, aktuelles, modus=modus, schuljahr=schuljahr, bezugsstufe=bezugsstufe)
    leer["zeitraum"]["bezugsstufe"] = bezugsstufe if modus == vz.WEG else None

    # ── Curricula je Fach und Stufe ─────────────────────────────────────────
    alle = await _curricula(db, user, status, stufen=(stufen[0], stufen[-1]))
    faecher_ids = {c.subject_id for c in alle if c.subject_id is not None}
    versionen: dict[int, set[str]] = defaultdict(set)
    for f, v in (await db.execute(sa.select(ContextNode.subject_id, ContextNode.bp_version).where(
            ContextNode.subject_id.in_(faecher_ids), ContextNode.content_type == "ik_kompetenz",
            ContextNode.bp_version != "").distinct())).all():
        versionen[f].add(v)
    je_fach: dict[int, list[ContextNode]] = defaultdict(list)
    for c in alle:
        je_fach[c.subject_id].append(c)
    auswahl: dict[tuple[int, int], list[ContextNode]] = {}
    geltend_je: dict[tuple[int, int], Optional[str]] = {}
    for s in stufen:
        start = parse_schuljahr_start(sj[s])
        for f, curs in je_fach.items():
            deckt = [c for c in curs if s in _stufen_von(c)]
            if not deckt:
                continue
            geltend = aktive_bp_version(s, versionen.get(f, set()), start)
            geltend_je[(f, s)] = geltend
            if (gewaehlt := _waehlen(deckt, geltend)):
                auswahl[(f, s)] = gewaehlt
    cur_stufen: dict[str, list[int]] = defaultdict(list)
    curricula: dict[str, ContextNode] = {}
    for (f, s), curs in auswahl.items():
        for c in curs:
            curricula[str(c.id)] = c
            cur_stufen[str(c.id)].append(s)

    # ── Kapitel ──────────────────────────────────────────────────────────────
    kap_zeilen = (await db.execute(
        sa.select(ContextNode, ContextEdge.to_node_id)
        .join(ContextEdge, sa.and_(ContextEdge.from_node_id == ContextNode.id, ContextEdge.relation == "part_of"))
        .where(ContextNode.content_type == "kapitel", ContextNode.status.in_(status),
               ContextEdge.to_node_id.in_([c.id for c in curricula.values()])))).all() if curricula else []
    kapitel: dict[str, dict] = {}
    for k, cid in kap_zeilen:
        c = curricula[str(cid)]
        if k.status != c.status:
            continue
        meta = k.metadata_ or {}
        reihe = meta.get("reihenfolge")
        kapitel[str(k.id)] = {
            "id": str(k.id), "titel": k.title, "fach_id": c.subject_id, "curriculum_id": str(cid),
            "status": k.status, "reihe": reihe if isinstance(reihe, int) else None,
            "std": vp._std(meta.get("std")), "kopie_von": meta.get("kopie_von"),
            "absprachen": meta.get("absprachen") or [], "lage": [],
        }
    je_cur: dict[str, list[dict]] = defaultdict(list)
    for k in kapitel.values():
        je_cur[k["curriculum_id"]].append(k)
    for liste in je_cur.values():
        liste.sort(key=lambda k: (k["reihe"] is None, k["reihe"] or 0, k["titel"]))

    # Plan- und Absprachen-Kennungen auf angezeigte Kapitel abbilden
    aus_original = {str(k["kopie_von"]): kid for kid, k in kapitel.items() if k["status"] == ENTWURF and k["kopie_von"]}

    async def abbilden(ids: set[str]) -> dict[str, str]:
        from app.planning.verlaufsplan_gruppe import nachfolger_der_kapitel

        aus = {}
        offen = set()
        for i in ids:
            if i in kapitel:
                aus[i] = i
            elif i in aus_original:
                aus[i] = aus_original[i]
            else:
                offen.add(i)
        for alt, neu in (await nachfolger_der_kapitel(db, offen)).items() if offen else []:
            if neu in kapitel:
                aus[alt] = neu
            elif neu in aus_original:
                aus[alt] = aus_original[neu]
        return aus

    # ── Jahre, Pläne, Lage ────────────────────────────────────────────────────
    jahre = {s: _jahr(sj[s], aktuelles) for s in stufen}
    plaene = list((await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == vp.TYP, ContextNode.status.in_(vp.LESBAR),
        ContextNode.subject_id.in_({f for f, _ in auswahl}), ContextNode.min_grade.in_(stufen),
        ContextNode.metadata_["schuljahr"].as_string().in_(set(sj.values())))))
        .scalars()) if auswahl else []
    plan_je: dict[tuple[int, int], ContextNode] = {}
    for p in sorted(plaene, key=lambda p: p.status != vp.BESCHLOSSEN):   # beschlossen zuerst
        if (p.metadata_ or {}).get("schuljahr") == sj.get(p.min_grade):
            plan_je.setdefault((p.subject_id, p.min_grade), p)
    roh_lagen: dict[str, list[vz.Lage]] = defaultdict(list)
    for (f, s), p in plan_je.items():
        meta = p.metadata_ or {}
        abschnitte = meta.get("abschnitte") or []
        seq = None
        if vp.planungsart(meta) == vp.SEQUENZ:
            seq = await vp.kapitel_der_sequenzen(db, {str(x) for a in abschnitte for x in a.get("sequenz_ids") or []})
        for kid, l in vz.plan_lagen(abschnitte, s, vz.PLAN if p.status == vp.BESCHLOSSEN else vz.ENTWURF,
                                    kapitel_von_sequenz=seq, wochen_im_jahr=jahre[s]["wochen"]).items():
            roh_lagen[kid].append(l)
    abb = await abbilden(set(roh_lagen))
    for alt, ls in roh_lagen.items():
        if (neu := abb.get(alt)) is not None:
            kapitel[neu]["lage"].extend(ls)
    for cid, c in curricula.items():
        st = sorted(cur_stufen[cid])
        ohne_plan = [s for s in st if (c.subject_id, s) not in plan_je]
        if not ohne_plan:
            continue
        offen = [k for k in je_cur.get(cid, []) if not k["lage"]]
        ws = ((c.metadata_ or {}).get("rahmen") or {}).get("wochenstunden") or {}
        geschaetzt = vz.schaetzen([(k["id"], k["std"]) for k in offen], ohne_plan,
                                  {s: ws.get(str(s)) for s in ohne_plan}, {s: jahre[s]["wochen"] for s in ohne_plan})
        for kid, ls in geschaetzt.items():
            kapitel[kid]["lage"].extend(ls)

    def spanne(kid: str):
        k = kapitel[kid]
        c = curricula[k["curriculum_id"]]
        return vz.als_spanne(k["lage"], (c.min_grade, c.max_grade))

    # ── Kompetenzen der Kapitel ───────────────────────────────────────────────
    ik_alias = aliased(ContextNode)
    ls_alias = aliased(ContextNode)
    e_ls, e_ref = aliased(ContextEdge), aliased(ContextEdge)
    eigene_ik: dict[str, set] = defaultdict(set)
    verweis_ik: dict[str, set] = defaultdict(set)
    ik_info: dict = {}
    if kapitel:
        for kid, ik_id, ik_fach, ik_meta in (await db.execute(
                sa.select(e_ls.to_node_id, ik_alias.id, ik_alias.subject_id, ik_alias.metadata_)
                .select_from(e_ls)
                .join(ls_alias, sa.and_(ls_alias.id == e_ls.from_node_id, ls_alias.content_type == "lernsequenz",
                                        ls_alias.status.in_(status)))
                .join(e_ref, sa.and_(e_ref.from_node_id == ls_alias.id, e_ref.relation == "references"))
                .join(ik_alias, sa.and_(ik_alias.id == e_ref.to_node_id, ik_alias.content_type == "ik_kompetenz"))
                .where(e_ls.relation == "part_of", e_ls.to_node_id.in_([uuid.UUID(k) for k in kapitel])))).all():
            k = kapitel[str(kid)]
            ik_info[ik_id] = ik_meta or {}
            (eigene_ik if ik_fach == k["fach_id"] else verweis_ik)[str(kid)].add(ik_id)
    ik_kapitel: dict = defaultdict(set)
    for kid, iks in eigene_ik.items():
        for i in iks:
            ik_kapitel[i].add(kid)

    def nr(ik_id) -> Optional[str]:
        m = ik_info.get(ik_id) or {}
        return m.get("kompetenz_nr") or m.get("nr")

    # ── Bezüge über den Bildungsplan ──────────────────────────────────────────
    paare: dict[tuple[str, str], dict] = {}

    def merke(a: str, b: str, art: str, hier: str, dort: str):
        """Ein Bezug von Kapitel a (Nummer `hier`) zu b (`dort`); das Beispiel steht aus Sicht
        des ersten Kapitels des Paars, damit beide Richtungen einer Kante dasselbe ergeben."""
        if a == b:
            return
        ka, kb = kapitel[a], kapitel[b]
        if fach_id not in (ka["fach_id"], kb["fach_id"]):
            return
        eigen = ka["fach_id"] == kb["fach_id"]
        if eigen and ka["curriculum_id"] == kb["curriculum_id"] and ka["reihe"] is not None \
                and kb["reihe"] is not None and abs(ka["reihe"] - kb["reihe"]) == 1:
            return   # benachbart (F1)
        x, y = sorted((a, b))
        beispiel = f"{hier} ↔ {dort}" if x == a else f"{dort} ↔ {hier}"
        p = paare.setdefault((x, y), {"a": x, "b": y, "art": art, "eigenes_fach": eigen, "beispiele": []})
        if art == "kompetenz":
            p["art"] = "kompetenz"
        if beispiel not in p["beispiele"] and len(p["beispiele"]) < BEISPIELE:
            p["beispiele"].append(beispiel)

    quellen = set(ik_kapitel)
    if quellen:
        kanten = (await db.execute(sa.select(ContextEdge.from_node_id, ContextEdge.to_node_id).where(
            ContextEdge.relation == "related_to",
            sa.or_(ContextEdge.from_node_id.in_(quellen), ContextEdge.to_node_id.in_(quellen))))).all()
        gerichtet = [(v, z) for v, z in kanten if v in quellen] + [(z, v) for v, z in kanten if z in quellen]
        ziele = {k.id: k for k in (await db.execute(sa.select(ContextNode).where(
            ContextNode.id.in_({z for _, z in gerichtet}),
            ContextNode.content_type.in_(("ik_kompetenz", "leitidee"))))).scalars()} if gerichtet else {}
        umgelenkt = await _umlenken(db, [z for z in ziele.values() if z.status not in _SICHTBAR])
        aufgeloest = {}
        for zid, z in ziele.items():
            aufgeloest[zid] = z if z.status in _SICHTBAR else umgelenkt.get(zid)
        bereiche = await _bereich_kompetenzen(db, {z.id for z in aufgeloest.values()
                                                   if z is not None and z.content_type == "leitidee"})
        for q, zid in gerichtet:
            z = aufgeloest.get(zid)
            if z is None:
                continue
            for a in ik_kapitel[q]:
                if z.content_type == "ik_kompetenz":
                    for b in ik_kapitel.get(z.id, ()):
                        merke(a, b, "kompetenz", nr(q) or "?", nummer(z) or "?")
                else:
                    for ik in bereiche.get(z.id, ()):
                        for b in ik_kapitel.get(ik, ()):
                            merke(a, b, "bereich", nr(q) or "?", nummer(z) or kurztitel(z.title))
    # Eigene Verweise in den Hinweisen (`#[…](ik:…)`): eine fremde Kompetenz an einer Lernsequenz
    for a, iks in verweis_ik.items():
        for ik in iks:
            for b in ik_kapitel.get(ik, ()):
                merke(a, b, "kompetenz", "Verweis", nr(ik) or "?")

    # ── Absprachen ────────────────────────────────────────────────────────────
    codes = {s.id: s.fach_code for s in (await db.execute(sa.select(Subject).where(
        Subject.id.in_(faecher_ids | {fach_id})))).scalars()}
    roh_abspr = [(kid, a) for kid, k in kapitel.items() for a in k["absprachen"] if isinstance(a, dict)]
    ziel_abb = await abbilden({str(a["kapitel_id"]) for _, a in roh_abspr if a.get("kapitel_id")})
    absprachen: dict[tuple[str, str], dict] = {}
    fach_absprachen = []
    for kid, a in roh_abspr:
        k = kapitel[kid]
        ziel = ziel_abb.get(str(a.get("kapitel_id"))) if a.get("kapitel_id") else None
        if ziel is None:
            if k["fach_id"] == fach_id or a.get("fach_code") == fach.fach_code:
                fach_absprachen.append({"kapitel": kid, "fach_code": a.get("fach_code"), "art": a.get("art"),
                                        "text": a.get("text") or "", "kapitel_titel": a.get("kapitel_titel"),
                                        "ausserhalb": bool(a.get("kapitel_id"))})
            continue
        if fach_id not in (k["fach_id"], kapitel[ziel]["fach_id"]):
            continue
        x, y = sorted((kid, ziel))
        art_x = a.get("art") if kid == x else GEGENART.get(a.get("art"), a.get("art"))
        vorhanden = absprachen.get((x, y))
        if vorhanden is not None and vorhanden["art"] == art_x:
            vorhanden["beidseitig"] = True
            vorhanden["texte"].append(a.get("text") or "")
            continue
        if vorhanden is not None:
            continue   # widersprüchliche Gegenseite: die erste bleibt
        absprachen[(x, y)] = {"a": x, "b": y, "art": art_x, "eingetragen_an": kid, "beidseitig": False,
                              "texte": [a.get("text") or ""], "id": a.get("id")}
    for p in absprachen.values():
        p["pruefung"] = pruefung_dict(p["art"], spanne(p["a"]), spanne(p["b"]))

    bezuege = [{"typ": "absprache", **p} for p in absprachen.values()]
    bezuege += [{"typ": p["art"], "a": p["a"], "b": p["b"], "eigenes_fach": p["eigenes_fach"],
                 "beispiele": p["beispiele"]} for p in paare.values()]

    # ── Spuren: vernetzte Fächer ──────────────────────────────────────────────
    zahl: dict[int, dict] = defaultdict(lambda: {"absprachen": 0, "kompetenz": 0, "bereich": 0})
    for b in bezuege:
        fa, fb = kapitel[b["a"]]["fach_id"], kapitel[b["b"]]["fach_id"]
        if fa == fb:
            continue
        ander = fb if fa == fach_id else fa
        zahl[ander]["absprachen" if b["typ"] == "absprache" else b["typ"]] += 1
    for fa in fach_absprachen:
        ander = next((f for f, c in codes.items() if c == fa["fach_code"]), None) \
            if kapitel[fa["kapitel"]]["fach_id"] == fach_id else kapitel[fa["kapitel"]]["fach_id"]
        if ander is not None and ander != fach_id:
            zahl[ander]["absprachen"] += 1
    faecher = {s.id: s for s in (await db.execute(sa.select(Subject).where(Subject.id.in_(set(zahl))))).scalars()} \
        if zahl else {}
    spuren = sorted(
        ({**_fach_dict(faecher[f]), **z, "nur_bereich": not z["absprachen"] and not z["kompetenz"]}
         for f, z in zahl.items() if f in faecher),
        key=lambda d: (-d["absprachen"], -d["kompetenz"], -d["bereich"], d["name"]))

    # ── Leitperspektiven und Leitlinien der Kapitel des Fachs ─────────────────
    leitlinien = await _leitlinien_der_kapitel(db, [k for k, v in kapitel.items() if v["fach_id"] == fach_id], status)

    # ── Antwort ───────────────────────────────────────────────────────────────
    sichtbar = {fach_id} | {d["id"] for d in spuren}
    stufen_aus = []
    for s in stufen:
        eigene_c = auswahl.get((fach_id, s), [])
        stufen_aus.append({
            "stufe": s, **jahre[s], "fassung": geltend_je.get((fach_id, s)) or next(
                ((c.metadata_ or {}).get("bp_version") for c in eigene_c), None),
            "curricula": [{"id": str(c.id), "titel": c.title, "status": c.status} for c in eigene_c],
            "plan": (lambda p: {"id": str(p.id), "status": p.status} if p else None)(plan_je.get((fach_id, s))),
        })
    return {
        **leer,
        "stufen": stufen_aus,
        "faecher": spuren,
        "kapitel": [_kapitel_dict(k) for k in sorted(kapitel.values(),
                    key=lambda k: (k["fach_id"], k["curriculum_id"], k["reihe"] or 0)) if k["fach_id"] in sichtbar],
        "bezuege": bezuege,
        "fach_absprachen": fach_absprachen,
        "leitlinien": leitlinien,
    }


def _kapitel_dict(k: dict) -> dict:
    return {"id": k["id"], "titel": k["titel"], "fach_id": k["fach_id"], "curriculum_id": k["curriculum_id"],
            "status": k["status"], "reihe": k["reihe"], "std": k["std"],
            "lage": [l.als_dict() for l in sorted(k["lage"], key=lambda l: (l.stufe, l.von_woche))]}


async def _leitlinien_der_kapitel(db: AsyncSession, kapitel_ids: list[str], status) -> dict[str, list[dict]]:
    """Je Kapitel die Leitperspektiven und Leitlinien seiner Lernsequenzen (F6): Kürzel der
    Leitperspektive bzw. Leitlinie, Titel, und welche Aspekte genannt sind."""
    if not kapitel_ids:
        return {}
    from app.context.leitlinien import verweisziele

    ls_alias, ziel = aliased(ContextNode), aliased(ContextNode)
    e_ls, e_ref = aliased(ContextEdge), aliased(ContextEdge)
    zeilen = (await db.execute(
        sa.select(e_ls.to_node_id, ziel.id, ziel.content_type)
        .select_from(e_ls)
        .join(ls_alias, sa.and_(ls_alias.id == e_ls.from_node_id, ls_alias.content_type == "lernsequenz",
                                ls_alias.status.in_(status)))
        .join(e_ref, sa.and_(e_ref.from_node_id == ls_alias.id, e_ref.relation == "references"))
        .join(ziel, sa.and_(ziel.id == e_ref.to_node_id, ziel.content_type.in_(_LP_TYPEN + _LL_TYPEN)))
        .where(e_ls.relation == "part_of", e_ls.to_node_id.in_([uuid.UUID(k) for k in kapitel_ids])))).all()
    if not zeilen:
        return {}
    vz_ = await verweisziele(db)
    eltern_ll = {a.kuerzel: l.kuerzel for l in vz_.liste for a in l.aspekte}
    titel = {l.kuerzel: l.titel for l in vz_.liste} | {e["kuerzel"]: e["titel"] for e in vz_.lp_liste}
    aus: dict[str, dict[tuple, dict]] = defaultdict(dict)
    for kid, zid, typ in zeilen:
        k = vz_.kuerzel_von.get(str(zid))
        if not k:
            continue
        if typ in _LL_TYPEN:
            art, oben = "ll", eltern_ll.get(k, k)
        else:
            art = "lp"
            oben = "LFDB" if k.startswith("LFDB") else k.partition("_")[0]
        e = aus[str(kid)].setdefault((art, oben), {"art": art, "kuerzel": oben, "titel": titel.get(oben, oben),
                                                   "aspekte": []})
        if k != oben and k not in e["aspekte"]:
            e["aspekte"].append(k)
    return {kid: sorted(v.values(), key=lambda e: (e["art"], e["kuerzel"])) for kid, v in aus.items()}
