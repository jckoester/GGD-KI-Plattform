"""Absprachen zwischen Fächern am Kapitel eines Curriculums (0.63, Päckchen AY Teil 2).

Eine Fachschaft hält am **eigenen** Kapitel fest, was sie mit einer anderen Fachschaft vereinbart
hat (F1). Gespeichert als `metadata.absprachen` am Kapitel-Knoten:

    [{"id": "…", "fach_code": "PH", "kapitel_id": "…" | None, "kapitel_titel": "Dichte" | None,
      "art": "vorher", "text": "…"}]

- `fach_code` ist Pflicht, das Kapitel des anderen Fachs freiwillig (F2). `kapitel_titel` ist der
  Stand beim Speichern — er bleibt lesbar, wenn das Ziel verschwindet, und trägt Absprachen aus
  einer YAML, deren Kapitel sich nicht auflösen ließ.
- `art` (F3): `vorher` (das andere Kapitel liegt vor diesem), `gleichzeitig`, `nachher`,
  `abgestimmt` (inhaltlich, ohne Zeit). Eine zeitliche Art braucht ein Kapitel.
- Keine Zustimmung der anderen Seite (F4); sie sieht die Absprache über die Rückwärtssuche und
  kann eine Gegenabsprache anlegen (`GEGENART`).

Hier: Prüfen und Bereinigen (rein) und die Prüfung der Ziele gegen die Datenbank.
"""
from __future__ import annotations

import uuid
from typing import Any

ARTEN: tuple[str, ...] = ("vorher", "gleichzeitig", "nachher", "abgestimmt")
ZEITLICH = frozenset({"vorher", "gleichzeitig", "nachher"})
#: Die Art aus Sicht der anderen Fachschaft („Mathematik vorher“ ↔ „Physik nachher“).
GEGENART = {"vorher": "nachher", "nachher": "vorher", "gleichzeitig": "gleichzeitig", "abgestimmt": "abgestimmt"}

MAX_JE_KAPITEL = 20
MAX_TEXT = 1_000
MAX_TITEL = 200


def _uuid_text(wert: Any, wo: str) -> str:
    try:
        return str(uuid.UUID(str(wert)))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"{wo}: keine gültige Kennung.") from None


def normalisieren(liste: Any, eigenes_fach: str | None = None) -> list[dict]:
    """Prüft und bereinigt die Absprachen eines Kapitels (Kopie). `ValueError` mit der Stelle
    („Absprache 2: …“) bei unbrauchbaren Werten. Fehlt eine `id`, bekommt die Absprache eine."""
    if liste is None:
        return []
    if not isinstance(liste, list):
        raise ValueError("Die Absprachen müssen eine Liste sein.")
    if len(liste) > MAX_JE_KAPITEL:
        raise ValueError(f"Höchstens {MAX_JE_KAPITEL} Absprachen je Kapitel.")
    eigen = (eigenes_fach or "").strip().upper()
    aus, ids, gesehen = [], set(), set()
    for i, roh in enumerate(liste, 1):
        wo = f"Absprache {i}"
        if not isinstance(roh, dict):
            raise ValueError(f"{wo}: muss ein Objekt sein.")
        fach = roh.get("fach_code")
        if not isinstance(fach, str) or not fach.strip():
            raise ValueError(f"{wo}: Das andere Fach fehlt.")
        fach = fach.strip().upper()
        if eigen and fach == eigen:
            raise ValueError(f"{wo}: Eine Absprache gilt einem anderen Fach, nicht dem eigenen.")
        art = roh.get("art")
        if art not in ARTEN:
            raise ValueError(f"{wo}: Art „{art}“ gibt es nicht ({', '.join(ARTEN)}).")
        text = roh.get("text")
        if text is not None and not isinstance(text, str):
            raise ValueError(f"{wo}: Der Text muss Text sein.")
        text = (text or "").strip()
        if len(text) > MAX_TEXT:
            raise ValueError(f"{wo}: Der Text ist zu lang ({len(text)} Zeichen, höchstens {MAX_TEXT}).")
        kid = roh.get("kapitel_id")
        kid = _uuid_text(kid, wo) if kid not in (None, "") else None
        titel = roh.get("kapitel_titel")
        if titel is not None and not isinstance(titel, str):
            raise ValueError(f"{wo}: Der Kapiteltitel muss Text sein.")
        titel = (titel or "").strip()[:MAX_TITEL] or None
        if art in ZEITLICH and not (kid or titel):
            raise ValueError(f"{wo}: „{art}“ braucht ein Kapitel des anderen Fachs.")
        if art == "abgestimmt" and not text:
            raise ValueError(f"{wo}: Was abgestimmt ist, steht im Text — er fehlt.")
        schluessel = (fach, kid or titel, art)
        if schluessel in gesehen:
            raise ValueError(f"{wo}: Dieselbe Absprache steht schon da.")
        gesehen.add(schluessel)
        aid = roh.get("id")
        aid = _uuid_text(aid, wo) if aid not in (None, "") else str(uuid.uuid4())
        if aid in ids:
            aid = str(uuid.uuid4())
        ids.add(aid)
        aus.append({"id": aid, "fach_code": fach, "kapitel_id": kid, "kapitel_titel": titel,
                    "art": art, "text": text})
    return aus


async def ziele_pruefen(db, absprachen: list[dict]) -> list[dict]:
    """Prüft die Ziele bereinigter Absprachen gegen die Datenbank und setzt `kapitel_titel` auf
    den aktuellen Titel (Kopie). `ValueError`, wenn das Fach unbekannt ist oder das Kapitel kein
    veröffentlichtes oder Entwurfs-Kapitel dieses Fachs ist."""
    import sqlalchemy as sa

    from app.context.curriculum_entwurf import LESBARE_STATUS
    from app.db.models import ContextNode, Subject

    if not absprachen:
        return []
    faecher = {a["fach_code"] for a in absprachen}
    fach_ids = dict((await db.execute(
        sa.select(Subject.fach_code, Subject.id).where(Subject.fach_code.in_(faecher)))).all())
    kids = [uuid.UUID(a["kapitel_id"]) for a in absprachen if a.get("kapitel_id")]
    kapitel = {str(n.id): n for n in (await db.execute(
        sa.select(ContextNode).where(ContextNode.id.in_(kids)))).scalars()} if kids else {}
    aus = []
    for i, a in enumerate(absprachen, 1):
        wo = f"Absprache {i}"
        if a["fach_code"] not in fach_ids:
            raise ValueError(f"{wo}: Ein Fach „{a['fach_code']}“ gibt es hier nicht.")
        a = dict(a)
        if a.get("kapitel_id"):
            k = kapitel.get(a["kapitel_id"])
            if (k is None or k.content_type != "kapitel" or k.status not in LESBARE_STATUS
                    or k.subject_id != fach_ids[a["fach_code"]]):
                raise ValueError(f"{wo}: Das Kapitel gehört nicht zu einem Curriculum von „{a['fach_code']}“.")
            a["kapitel_titel"] = (k.title or "")[:MAX_TITEL] or a.get("kapitel_titel")
        aus.append(a)
    return aus


# ── Lesen in beide Richtungen (Schritt 2) ────────────────────────────────────

_OFFEN = ("global", "school", "subject")


def _fach(s) -> dict:
    return {"fach_code": s.fach_code, "fach": s.name, "fach_slug": s.slug, "icon": s.icon, "color": s.color}


def _stufen(cur) -> dict:
    return {"min_grade": cur.min_grade, "max_grade": cur.max_grade}


def _ueberschneiden(a, b) -> bool:
    if None in (a.min_grade, a.max_grade, b.min_grade, b.max_grade):
        return True
    return a.min_grade <= b.max_grade and b.min_grade <= a.max_grade


async def _kapitel_des_curriculums(db, curriculum) -> list:
    import sqlalchemy as sa

    from app.db.models import ContextEdge, ContextNode

    return list((await db.execute(
        sa.select(ContextNode).join(ContextEdge, sa.and_(ContextEdge.from_node_id == ContextNode.id,
                                                         ContextEdge.relation == "part_of"))
        .where(ContextEdge.to_node_id == curriculum.id, ContextNode.content_type == "kapitel",
               ContextNode.status == curriculum.status)
        .order_by(ContextNode.metadata_["reihenfolge"].as_integer(), ContextNode.title))).scalars())


async def _curricula_der_kapitel(db, kapitel_ids) -> dict:
    """Kapitel-Kennung → Curriculum-Knoten (über `part_of`)."""
    import sqlalchemy as sa

    from app.db.models import ContextEdge, ContextNode

    if not kapitel_ids:
        return {}
    zeilen = (await db.execute(
        sa.select(ContextEdge.from_node_id, ContextNode)
        .join(ContextNode, ContextNode.id == ContextEdge.to_node_id)
        .where(ContextEdge.from_node_id.in_(list(kapitel_ids)), ContextEdge.relation == "part_of",
               ContextNode.content_type == "curriculum"))).all()
    return {str(k): c for k, c in zeilen}


async def _vorgaenger(db, kapitel) -> dict[str, str]:
    """Kennungen früherer Fassungen der eigenen Kapitel (über `kopie_von`, rückwärts) → eigenes
    Kapitel. Eine Absprache, die auf ein Kapitel vor dem Ersatz zeigt, gilt dem Nachfolger."""
    import sqlalchemy as sa

    from app.db.models import ContextNode

    aus = {str(k.id): str(k.id) for k in kapitel}
    offen = {(k.metadata_ or {}).get("kopie_von"): str(k.id) for k in kapitel if (k.metadata_ or {}).get("kopie_von")}
    for _ in range(5):
        offen = {alt: eigen for alt, eigen in offen.items() if alt and alt not in aus}
        if not offen:
            break
        aus.update(offen)
        try:
            ids = [uuid.UUID(a) for a in offen]
        except ValueError:
            break
        zeilen = (await db.execute(sa.select(ContextNode.id, ContextNode.metadata_["kopie_von"].astext)
                                   .where(ContextNode.id.in_(ids)))).all()
        offen = {weiter: offen[str(kid)] for kid, weiter in zeilen if weiter}
    return aus


async def absprachen_des_curriculums(db, curriculum, user) -> dict:
    """Die Absprachen eines Curriculums in beide Richtungen (F4, F6). Das Lesen des Curriculums
    selbst prüft der Aufrufer.

    Antwort: `kapitel` — je eigenes Kapitel `eigene` (am Kapitel gespeichert, das Ziel auf den
    aktuellen Nachfolger aufgelöst) und `von_aussen` (Absprachen anderer Fächer, die auf dieses
    Kapitel oder eine frühere Fassung zeigen) — und `fach`: Absprachen anderer Fächer an das Fach
    ohne Kapitel, aus Curricula mit überschneidenden Stufen. Je Absprache `beidseitig`, wenn die
    Gegenseite die passende Gegenabsprache hat. Entwürfe zählen nur für Lehrkräfte (`status`).
    """
    import sqlalchemy as sa

    from app.auth.vorschau import eigenes_zaehlt
    from app.context.curriculum_entwurf import ENTWURF, darf_entwurf_lesen
    from app.db.models import ContextNode, Subject
    from app.planning.verlaufsplan_gruppe import nachfolger_der_kapitel

    status_lesbar = ("active", ENTWURF) if darf_entwurf_lesen(user) else ("active",)

    def lesbar(cur) -> bool:
        return (cur is not None and cur.status in status_lesbar
                and (cur.read_scope in _OFFEN or (eigenes_zaehlt(user.sub) and cur.owner_pseudonym == user.sub)))

    faecher = {s.id: s for s in (await db.execute(sa.select(Subject))).scalars()}
    je_code = {s.fach_code: s for s in faecher.values() if s.fach_code}
    eigenes_fach = faecher.get(curriculum.subject_id)
    eigene_kapitel = await _kapitel_des_curriculums(db, curriculum)
    alias = await _vorgaenger(db, eigene_kapitel)

    # Eigene: Ziele auflösen
    ziel_ids = {a["kapitel_id"] for k in eigene_kapitel for a in (k.metadata_ or {}).get("absprachen") or []
                if a.get("kapitel_id")}
    ziele = {str(n.id): n for n in (await db.execute(sa.select(ContextNode).where(
        ContextNode.id.in_([uuid.UUID(i) for i in ziel_ids])))).scalars()} if ziel_ids else {}
    nachfolger = await nachfolger_der_kapitel(db, {i for i, n in ziele.items() if n.status == "archived"})
    if nachfolger:
        ziele.update({str(n.id): n for n in (await db.execute(sa.select(ContextNode).where(
            ContextNode.id.in_([uuid.UUID(i) for i in nachfolger.values()])))).scalars()})
    ziel_cur = await _curricula_der_kapitel(db, [ziele[i].id for i in ziele])

    # Von außen: Kapitel anderer Fächer mit Absprachen
    kandidaten = list((await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type == "kapitel", ContextNode.status.in_(status_lesbar),
        ContextNode.subject_id != curriculum.subject_id,
        ContextNode.metadata_.has_key("absprachen")))).scalars())
    quell_cur = await _curricula_der_kapitel(db, [k.id for k in kandidaten])

    kapitel_aus = {str(k.id): {"eigene": [], "von_aussen": []} for k in eigene_kapitel}
    fach_aus: list[dict] = []
    gesehen: dict[str, tuple] = {}   # Absprache-Kennung → (Rang, Eintrag); veröffentlicht vor Entwurf
    for k in kandidaten:
        cur = quell_cur.get(str(k.id))
        if not lesbar(cur) or cur.status != k.status:
            continue
        quelle_fach = faecher.get(k.subject_id)
        for a in (k.metadata_ or {}).get("absprachen") or []:
            eigen = alias.get(a.get("kapitel_id") or "")
            an_fach = (not a.get("kapitel_id") and eigenes_fach is not None
                       and a.get("fach_code") == eigenes_fach.fach_code and _ueberschneiden(cur, curriculum))
            if not eigen and not an_fach:
                continue
            eintrag = {
                "id": a.get("id"), "art": a.get("art"), "art_hier": GEGENART.get(a.get("art"), a.get("art")),
                "text": a.get("text") or "", **(_fach(quelle_fach) if quelle_fach else {}),
                "quelle": {"kapitel_id": str(k.id), "kapitel": k.title, "curriculum_id": str(cur.id),
                           "curriculum": cur.title, "status": cur.status, **_stufen(cur)},
                "beidseitig": False, "_eigen": eigen,
            }
            rang = 0 if cur.status == "active" else 1
            if a.get("id") in gesehen and gesehen[a["id"]][0] <= rang:
                continue
            gesehen[a.get("id") or str(uuid.uuid4())] = (rang, eintrag)
    for _, eintrag in gesehen.values():
        eigen = eintrag.pop("_eigen")
        (kapitel_aus[eigen]["von_aussen"] if eigen else fach_aus).append(eintrag)

    for k in eigene_kapitel:
        for a in (k.metadata_ or {}).get("absprachen") or []:
            kid = a.get("kapitel_id")
            ziel = ziele.get(nachfolger.get(kid, kid)) if kid else None
            zcur = ziel_cur.get(str(ziel.id)) if ziel is not None else None
            zfach = je_code.get(a.get("fach_code"))
            eintrag = {
                "id": a.get("id"), "art": a.get("art"), "text": a.get("text") or "",
                **(_fach(zfach) if zfach else {"fach_code": a.get("fach_code"), "fach": a.get("fach_code")}),
                "kapitel_titel": a.get("kapitel_titel"),
                "ziel": ({"kapitel_id": str(ziel.id), "kapitel": ziel.title, "curriculum_id": str(zcur.id),
                          "curriculum": zcur.title, "status": zcur.status, **_stufen(zcur)}
                         if ziel is not None and ziel.status in status_lesbar and lesbar(zcur) else None),
                "beidseitig": False,
            }
            # Beidseitig: Die Gegenseite hat am Ziel eine Absprache mit der Gegenart auf dieses Kapitel.
            for g in kapitel_aus[str(k.id)]["von_aussen"]:
                if (eintrag["ziel"] and g["quelle"]["kapitel_id"] == eintrag["ziel"]["kapitel_id"]
                        and g["art_hier"] == a.get("art")):
                    eintrag["beidseitig"] = g["beidseitig"] = True
                    # Steht drüben ein anderer Text, liest man ihn an der eigenen Absprache mit —
                    # die Anzeige zeigt eine beidseitige Absprache nur einmal.
                    if (g.get("text") or "") and g["text"] != eintrag["text"]:
                        eintrag["text_gegenseite"] = g["text"]
            kapitel_aus[str(k.id)]["eigene"].append(eintrag)

    def ordnung(e):
        q = e["quelle"]
        return (e.get("fach") or "", q["min_grade"] or 0, q["curriculum"], q["kapitel"])
    for v in kapitel_aus.values():
        v["von_aussen"].sort(key=ordnung)
    fach_aus.sort(key=ordnung)
    return {"kapitel": kapitel_aus, "fach": fach_aus}


# ── Speichern (Schritt 3) ────────────────────────────────────────────────────

async def pruefe_absprachen(db, content_type: str | None, metadata: dict | None, subject_id: int | None) -> dict | None:
    """Beim Anlegen und Ändern eines Knotens: Absprachen eines Kapitels prüfen und bereinigt
    zurückgeben (Kopie). Wirft `ValueError`. Andere Typen und Kapitel ohne `absprachen` bleiben
    unberührt; eine leere Liste fällt weg."""
    import sqlalchemy as sa

    from app.db.models import Subject

    if content_type != "kapitel" or not metadata or "absprachen" not in metadata:
        return metadata
    eigen = (await db.execute(sa.select(Subject.fach_code).where(Subject.id == subject_id))).scalar_one_or_none() \
        if subject_id is not None else None
    liste = await ziele_pruefen(db, normalisieren(metadata.get("absprachen"), eigen))
    meta = {k: v for k, v in metadata.items() if k != "absprachen"}
    if liste:
        meta["absprachen"] = liste
    return meta


# ── YAML (Schritt 5) ─────────────────────────────────────────────────────────
#
# Im YAML steht ein Ziel über **Fach und Kapiteltitel**, nicht über Kennungen — die Datei soll in
# einer anderen Instanz und aus einem KI-Programm heraus funktionieren:
#
#     absprachen:
#       - {fach_code: PH, kapitel: Dichte, jahrgangsstufe: "7/8", art: vorher, text: …}
#
# `kapitel` und `jahrgangsstufe` sind freiwillig; `jahrgangsstufe` hilft nur beim Auflösen, wenn
# derselbe Kapiteltitel in mehreren Curricula des Fachs vorkommt.

YAML_FELDER = frozenset({"fach_code", "kapitel", "jahrgangsstufe", "art", "text"})


def aus_yaml(liste: Any, eigenes_fach: str | None = None) -> tuple[list[dict], list[str]]:
    """Absprachen eines Kapitels aus dem YAML prüfen (rein). Rückgabe: Einträge
    `{fach_code, kapitel_titel, jahrgangsstufe, art, text}` und Warnungen (unbekannte Felder).
    `ValueError` mit Stelle wie bei `normalisieren`."""
    if liste is None:
        return [], []
    if not isinstance(liste, list):
        raise ValueError("Die Absprachen müssen eine Liste sein.")
    warnungen, roh = [], []
    for i, a in enumerate(liste, 1):
        if not isinstance(a, dict):
            raise ValueError(f"Absprache {i}: muss ein Objekt sein.")
        if fremd := sorted(set(map(str, a)) - YAML_FELDER):
            warnungen.append(f"Absprache {i}: unbekannte Felder ({', '.join(fremd)}) übergangen.")
        stufe = a.get("jahrgangsstufe")
        if stufe is not None and not isinstance(stufe, (str, int)):
            raise ValueError(f"Absprache {i}: jahrgangsstufe muss Text sein.")
        roh.append({"fach_code": a.get("fach_code"), "kapitel_titel": a.get("kapitel"), "art": a.get("art"),
                    "text": a.get("text"), "_stufe": str(stufe).strip() if stufe not in (None, "") else None})
    geprueft = normalisieren([{k: v for k, v in r.items() if k != "_stufe"} for r in roh], eigenes_fach)
    for g, r in zip(geprueft, roh):
        g.pop("id", None)
        g.pop("kapitel_id", None)
        g["jahrgangsstufe"] = r["_stufe"]
    return geprueft, warnungen


async def aus_yaml_aufloesen(db, liste: list[dict], eigene_stufe: str | None = None) -> tuple[list[dict], list[str]]:
    """Ziele aus dem YAML über Fach und Kapiteltitel auf Kapitel abbilden. Eindeutig → Kennung;
    sonst bleibt die Absprache mit dem Titel stehen (Warnung). Ein unbekanntes Fach fällt weg
    (Warnung). Bevorzugt veröffentlichte Kapitel, dann die angegebene oder die eigene Stufe."""
    import sqlalchemy as sa

    from app.context.curriculum_entwurf import LESBARE_STATUS
    from app.db.models import ContextNode, Subject

    if not liste:
        return [], []
    codes = {a["fach_code"] for a in liste}
    faecher = dict((await db.execute(sa.select(Subject.fach_code, Subject.id).where(Subject.fach_code.in_(codes)))).all())
    aus, warnungen = [], []
    for i, a in enumerate(liste, 1):
        wo = f"Absprache {i}"
        if a["fach_code"] not in faecher:
            warnungen.append(f"{wo}: Ein Fach „{a['fach_code']}“ gibt es hier nicht — übergangen.")
            continue
        eintrag = {k: a[k] for k in ("fach_code", "kapitel_titel", "art", "text")}
        eintrag["kapitel_id"] = None
        if a.get("kapitel_titel"):
            treffer = list((await db.execute(sa.select(ContextNode).where(
                ContextNode.content_type == "kapitel", ContextNode.status.in_(LESBARE_STATUS),
                ContextNode.subject_id == faecher[a["fach_code"]],
                sa.func.lower(sa.func.trim(ContextNode.title)) == a["kapitel_titel"].strip().lower()))).scalars())
            if len(treffer) > 1:
                cur = await _curricula_der_kapitel(db, [k.id for k in treffer])
                stufe = a.get("jahrgangsstufe") or eigene_stufe

                def stufe_von(k, cur=cur):
                    c = cur.get(str(k.id))
                    return (c.metadata_ or {}).get("jahrgangsstufe") if c is not None else None

                for passt in (lambda k: k.status == "active", lambda k: stufe is not None and stufe_von(k) == stufe):
                    enger = [k for k in treffer if passt(k)]
                    if enger:
                        treffer = enger
                    if len(treffer) == 1:
                        break
            if len(treffer) == 1:
                eintrag["kapitel_id"] = str(treffer[0].id)
                eintrag["kapitel_titel"] = treffer[0].title
            else:
                warnungen.append(f"{wo}: Kapitel „{a['kapitel_titel']}“ in {a['fach_code']} "
                                 f"{'nicht eindeutig' if treffer else 'nicht gefunden'} — die Absprache bleibt ohne Verknüpfung.")
        aus.append(eintrag)
    return normalisieren(aus), warnungen


async def fuer_yaml(db, liste: list[dict] | None) -> list[dict]:
    """Absprachen eines Kapitels für den YAML-Export: Fach, aktueller Kapiteltitel und Stufe des
    Ziels (sonst der gespeicherte Titel), Art, Text — ohne Kennungen."""
    import sqlalchemy as sa

    from app.db.models import ContextNode

    if not liste:
        return []
    ids = [uuid.UUID(a["kapitel_id"]) for a in liste if a.get("kapitel_id")]
    knoten = {str(n.id): n for n in (await db.execute(sa.select(ContextNode).where(ContextNode.id.in_(ids)))).scalars()} if ids else {}
    cur = await _curricula_der_kapitel(db, list(knoten)) if knoten else {}
    aus = []
    for a in liste:
        k = knoten.get(a.get("kapitel_id") or "")
        titel = k.title if k is not None else a.get("kapitel_titel")
        stufe = (cur[str(k.id)].metadata_ or {}).get("jahrgangsstufe") if k is not None and str(k.id) in cur else None
        aus.append({"fach_code": a["fach_code"], **({"kapitel": titel} if titel else {}),
                    **({"jahrgangsstufe": stufe} if stufe else {}), "art": a["art"],
                    **({"text": a["text"]} if a.get("text") else {})})
    return aus


#: Die Art als Satzteil, wie in der Oberfläche (`lib/absprachen.js`, `ART_SATZ`).
ART_SATZ = {"vorher": "kommt vorher", "gleichzeitig": "läuft gleichzeitig", "nachher": "kommt danach",
            "abgestimmt": "abgestimmt"}


async def export_zeilen(db, tree: dict) -> dict[str, list[str]]:
    """Je Kapitel die eigenen Absprachen als Zeilen für PDF und DOCX (kompakt, F7):
    „Physik · Dichte — kommt vorher: Bruchrechnung zuerst“. Absprachen von außen stehen nicht im
    Export — sie gehören der anderen Fachschaft und hängen am Leserecht."""
    import sqlalchemy as sa

    from app.db.models import Subject

    alle = [a for kap in tree.get("kapitel", []) for a in (kap.get("metadata") or {}).get("absprachen") or []]
    if not alle:
        return {}
    namen = dict((await db.execute(sa.select(Subject.fach_code, Subject.name).where(
        Subject.fach_code.in_({a["fach_code"] for a in alle})))).all())
    aus = {}
    for kap in tree.get("kapitel", []):
        zeilen = []
        for a in (kap.get("metadata") or {}).get("absprachen") or []:
            ziel = a.get("kapitel_titel") or "ganzes Fach"
            zeile = f"{namen.get(a['fach_code'], a['fach_code'])} · {ziel} — {ART_SATZ.get(a['art'], a['art'])}"
            zeilen.append(f"{zeile}: {a['text']}" if a.get("text") else zeile)
        if zeilen:
            aus[str(kap["id"])] = zeilen
    return aus
