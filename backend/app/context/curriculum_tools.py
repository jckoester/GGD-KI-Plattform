"""Funktionen des Curriculum-Assistenten (0.46, Päckchen AP Teil B, Schritt 5).

Fähigkeit `curriculum_planning`. Die Arbeit steht in `app/context/curriculum_assistent.py`;
hier nur Schema und Übergabe. Jede Funktion prüft den Zugang am Curriculum selbst
(`zugang`, dieselbe Regel wie im Editor) — der Bezug der Unterhaltung (`curriculum_node_id`)
ist eine Vorgabe, keine Erlaubnis. Geschrieben wird nur in Entwürfe (E17), jeder schreibende
Aufruf sichert vorher den Stand (Rückgängig im Editor und `undo_last_curriculum_change`).

`preview_curriculum_operations` ist die Vorschau zu `apply_curriculum_operations`: eine eigene
Funktion (`writes=False`), kein Schalter am Schreiben — ein vergessener Schalter schriebe ohne
Zustimmung, eine vergessene Vorschau schadet nicht. Bis zur Messung am 16.11.2026 hieß sie
`check_curriculum_operations`; „prüfen“ las das Modell als Schritt, der eine Zustimmung braucht.
"""
from __future__ import annotations

from uuid import UUID

from app.chat.tools import ChatTool, ToolContext, register_tool
from app.context import curriculum_assistent as ca
from app.context.curriculum_verlauf import gegenstand, juengster, stand_kennung, verlauf, zuruecknehmen

GRUPPE = frozenset({"curriculum_planning"})

_KENNUNG = {
    "curriculum_id": {
        "type": "string",
        "description": "Nur nötig, wenn die Unterhaltung kein Bezugscurriculum hat.",
    },
}


async def _curriculum(args: dict, ctx: ToolContext, *, schreiben: bool):
    roh = args.get("curriculum_id") or ctx.curriculum_node_id
    if not roh:
        return "curriculum_id erforderlich — die Unterhaltung hat kein Bezugscurriculum."
    try:
        cid = UUID(str(roh))
    except ValueError:
        return f"Ungültige curriculum_id „{roh}“."
    return await ca.zugang(ctx.db, ctx.user, cid, schreiben=schreiben)


def _schema(name: str, beschreibung: str, eigenschaften: dict | None = None, pflicht: list | None = None) -> dict:
    return {"type": "function", "function": {
        "name": name, "description": beschreibung,
        "parameters": {"type": "object", "properties": {**_KENNUNG, **(eigenschaften or {})},
                       "required": pflicht or []}}}


def _registriere(name: str, handler, beschreibung: str, eigenschaften=None, pflicht=None, *, schreibt=False):
    register_tool(ChatTool(name=name, groups=GRUPPE, writes=schreibt,
                           definition=_schema(name, beschreibung, eigenschaften, pflicht), handler=handler))


# ── Lesen ────────────────────────────────────────────────────────────────────


async def _get_curriculum_draft(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=False)
    if isinstance(cur, str):
        return {"error": cur}
    return await ca.entwurf_lesen(ctx.db, ctx.user, cur)


_registriere(
    "get_curriculum_draft", _get_curriculum_draft,
    "Das Curriculum mit Rahmenangaben, Kapiteln, Lernsequenzen und Einträgen. Kompetenzen als "
    "Nummern (ik, ik_teilweise, pk); Begriffe mit zustand (gefunden, fehlt, mehrdeutig — dann "
    "fassungen: die wählbaren; gewählt wird im Editor). "
    "Kennungen (id) und Eintragsnummern brauchst du für apply_curriculum_operations. "
    "status 'draft' = Entwurf; in andere schreibst du nicht. leitperspektiven und "
    "leitlinien_der_schule (falls vorhanden) nennen die Kürzel, auf die Einträge verweisen können; "
    "die Aspekte der Leitperspektiven liefert get_bp_competences mit typ='lp'.",
)


async def _get_bp_competences(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=False)
    if isinstance(cur, str):
        return {"error": cur}
    if args.get("typ") == "lp":  # Leitperspektiven mit Aspekten (0.50, AT)
        return await ca.leitperspektiven_lesen(ctx.db, args.get("bereich"))
    typ = "pk" if args.get("typ") == "pk" else "ik"
    return await ca.kompetenzen_lesen(ctx.db, cur, args.get("bereich"), typ)


_registriere(
    "get_bp_competences", _get_bp_competences,
    "Kompetenzen des Bildungsplans für Fach, Fassung und Band des Curriculums. Ohne bereich: "
    "Übersicht — Bereiche mit Anzahl und Nummern, ohne Texte. Mit bereich: die Kompetenzen "
    "mit Nummer und Text. Nur Nummern aus dieser Funktion sind gültig; erfinde keine.",
    {
        "bereich": {"type": "string", "description": (
            "Name eines Bereichs aus der Übersicht (ein Teil genügt), ein Nummernpräfix wie "
            "'3.2.1' oder 'alle'. Ein Kapitel bedient oft Kompetenzen aus mehreren Bereichen.")},
        "typ": {"type": "string", "enum": ["ik", "pk", "lp"], "description": (
            "ik = inhaltsbezogene Kompetenzen (Vorgabe), pk = prozessbezogene (gelten fürs ganze Fach), "
            "lp = Leitperspektiven mit ihren Aspekten (Kürzel wie BNE_03; bereich = Kürzel wie 'BNE').")},
    },
)


async def _get_curriculum_coverage(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=False)
    if isinstance(cur, str):
        return {"error": cur}
    return await ca.abdeckung_kompakt(ctx.db, cur)


_registriere(
    "get_curriculum_coverage", _get_curriculum_coverage,
    "Abdeckung des Bands: wie viele IK verknüpft, nur teilweise oder gar nicht; welche fehlen "
    "(mit in_anderem_curriculum, wenn ein anderes Curriculum des Bands sie abdeckt); welche PK "
    "ungenutzt sind; leitlinien: welche Aspekte der Leitlinien der Schule vorkommen. Nenne "
    "Zahlen nur aus dieser Funktion.",
)


async def _get_hour_frame(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=False)
    if isinstance(cur, str):
        return {"error": cur}
    return await ca.stundenrahmen(ctx.db, cur)


_registriere(
    "get_hour_frame", _get_hour_frame,
    "Stundenbilanz des gespeicherten Stands: verplanbar (30 Stunden je Wochenstunde aus den "
    "Rahmenangaben, über alle Stufen des Bands), verplant (Summe der Lernsequenzen), rest. "
    "verplanbar ist null, solange Wochenstunden fehlen. Dieselben Zahlen stehen auch in den "
    "Antworten von preview_curriculum_operations und apply_curriculum_operations. Rechne nicht selbst.",
)


# ── Schreiben ────────────────────────────────────────────────────────────────


#: Beschreibung der Operationen — gemeinsam für Vorschau und Schreiben.
OPERATIONEN = {
    "operations": {"type": "array", "items": {"type": "object"}, "description": (
        "Operationen, je mit 'op'. position zählt ab 1, ohne Angabe ans Ende. Mit ref "
        "(frei gewählt, z. B. 'k1') kann eine spätere Operation desselben Stapels ein eben "
        "angelegtes Kapitel oder eine Lernsequenz statt der id nennen.\n"
        "- kapitel_anlegen{titel, einleitung?, position?, ref?}\n"
        "- kapitel_aendern{kapitel_id, titel?, einleitung?, position?}\n"
        "- kapitel_loeschen{kapitel_id}: mit allen Lernsequenzen\n"
        "- lernsequenz_anlegen{kapitel_id, titel, std?, position?, ref?}\n"
        "- lernsequenz_aendern{lernsequenz_id, titel?, std?, kapitel_id?, position?}: "
        "kapitel_id verschiebt in ein anderes Kapitel\n"
        "- lernsequenz_loeschen{lernsequenz_id}\n"
        "- eintrag_anlegen{lernsequenz_id, ik?, ik_teilweise?, pk?, konkretisierung?, "
        "hinweise?, material?, begriffe?, fachmethoden?, leitperspektiven?, leitlinien?, position?}: "
        "ik, ik_teilweise, pk als Listen von Nummern aus get_bp_competences; begriffe und "
        "fachmethoden als Listen von Namen; leitperspektiven (BNE oder Aspekt BNE_03) und "
        "leitlinien als Listen von Kürzeln\n"
        "- eintrag_aendern{lernsequenz_id, eintrag, …}: eintrag = Nummer ab 1; genannte Felder "
        "ersetzen die bisherigen, andere bleiben\n"
        "- eintrag_loeschen{lernsequenz_id, eintrag}")},
}

_ANTWORT = (
    "Antwort: gliederung (Kapitel mit Lernsequenzen und Stunden; die Stunden eines Kapitels sind "
    "die Summe seiner Lernsequenzen), verplant, verplanbar, rest (null, solange Wochenstunden "
    "fehlen — dann fehlende_stufen) und geloescht (Kapitel, Lernsequenzen, Einträge, die der "
    "Stapel entfernt; fehlt, wenn nichts gelöscht wird).")


async def _konversation(ctx: ToolContext):
    from app.db.models import Conversation

    return await ctx.db.get(Conversation, ctx.conversation_id) if ctx.conversation_id else None


async def _preview_curriculum_operations(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=True)
    if isinstance(cur, str):
        return {"error": cur}
    antwort = await ca.operationen_pruefen(ctx.db, cur, args.get("operations"))
    # Den geprüften Stapel merken: Nach der Zustimmung (nächste Nachricht) kennt das Modell ihn
    # nicht mehr — Funktionsantworten bleiben nicht im Verlauf (Messung 16.11.2026).
    if antwort.get("ok") and (k := await _konversation(ctx)) is not None:
        k.curriculum_vorschlag = {"curriculum_id": str(cur.id), "operations": args["operations"],
                                  "stand": await stand_kennung(ctx.db, cur.id)}
        await ctx.db.flush()
        antwort["vorschlag_gemerkt"] = True
    return antwort


_registriere(
    "preview_curriculum_operations", _preview_curriculum_operations,
    "Vorschau eines Stapels, ohne zu schreiben: abgewiesene Operationen (fehler) und die Stunden, "
    "wie sie nach dem Stapel wären. Vor jedem Vorschlag an die Lehrkraft aufrufen, ohne zu fragen — "
    "die Vorschau braucht keine Zustimmung. Eine Vorschau ohne fehler wird als Vorschlag gemerkt "
    "(vorschlag_gemerkt): Nach "
    "Zustimmung schreibt ihn apply_curriculum_operations ohne operations. Neue Kapitel und "
    "Lernsequenzen haben hier noch keine id (null). " + _ANTWORT,
    OPERATIONEN, ["operations"],
)


async def _apply_curriculum_operations(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=True)
    if isinstance(cur, str):
        return {"error": cur}
    k = await _konversation(ctx)
    ops = args.get("operations")
    if not ops:
        vorschlag = (k.curriculum_vorschlag if k is not None else None) or {}
        if vorschlag.get("curriculum_id") != str(cur.id):
            return {"ok": False, "fehler": [
                "Kein Vorschlag aus einer Vorschau für dieses Curriculum — erst preview_curriculum_operations, "
                "den Vorschlag der Lehrkraft zeigen, nach Zustimmung schreiben."]}
        if vorschlag.get("stand") != await stand_kennung(ctx.db, cur.id):
            k.curriculum_vorschlag = None
            await ctx.db.flush()
            return {"ok": False, "fehler": [
                "Das Curriculum hat sich seit der Vorschau geändert (im Editor, von einer anderen Person "
                "oder durch einen anderen Schritt). Nichts geschrieben. Lies es neu, mach eine neue "
                "Vorschau und zeig den Vorschlag der Lehrkraft."]}
        ops = vorschlag["operations"]
    antwort = await ca.operationen_anwenden(ctx.db, ctx.user, cur, ops)
    if antwort.get("ok") and k is not None:
        k.curriculum_vorschlag = None
        await ctx.db.flush()
    return antwort


_registriere(
    "apply_curriculum_operations", _apply_curriculum_operations,
    "Schreibt Änderungen in den Entwurf — nur nach Zustimmung der Lehrkraft. **Ohne operations** "
    "schreibt es genau den Vorschlag der letzten Vorschau dieser Unterhaltung "
    "(preview_curriculum_operations) — der Normalfall nach „ja“. Hat sich das Curriculum seit der "
    "Vorschau geändert, wird nichts geschrieben: neu lesen, neue Vorschau, neu zeigen. Mit operations: "
    "dieser Stapel (vorher ebenfalls Vorschau). Ganz oder gar nicht: Passt eine Operation nicht, wird "
    "nichts geschrieben und fehler nennt, was. Vorher wird der Stand gesichert; "
    "undo_last_curriculum_change nimmt den Stapel zurück. " + _ANTWORT
    + " Dazu neue_kennungen für die refs.",
    OPERATIONEN, [], schreibt=True,
)


async def _set_curriculum_frame(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=True)
    if isinstance(cur, str):
        return {"error": cur}
    angaben = {k: args[k] for k in ("wochenstunden", "lehrwerk", "beschluesse", "schwerpunkte", "absprachen")
               if k in args}
    if not angaben:
        return {"ok": False, "fehler": ["Keine Angabe übergeben."]}
    return await ca.rahmen_setzen(ctx.db, ctx.user, cur, angaben)


_registriere(
    "set_curriculum_frame", _set_curriculum_frame,
    "Hält Rahmenangaben aus dem Gespräch fest, damit spätere Sitzungen nicht neu fragen. Die "
    "Antwort der Lehrkraft auf deine Rahmenfrage gilt als Zustimmung — halte sie gleich fest. Nur "
    "die genannten Felder ändern sich; leerer Text löscht ein Feld. Das Lehrwerk ist nur ein Name: "
    "Seinen Inhalt kennst du nicht — plane nicht danach, ohne dass die Lehrkraft Kapitel und "
    "Reihenfolge nennt.",
    {
        "wochenstunden": {"type": "object", "description": (
            "Wochenstunden je Klassenstufe, etwa {\"7\": 2, \"8\": 2}; halbe Stunden als 1.5.")},
        "lehrwerk": {"type": "string"},
        "beschluesse": {"type": "string", "description": "Beschlüsse der Fachschaft (Lektüren, Pflichtversuche, Exkursionen)."},
        "schwerpunkte": {"type": "string", "description": "Wofür die Fachschaft die freie Zeit nutzt."},
        "absprachen": {"type": "string", "description": "Leistungsnachweise, Methoden-, Medien-, Präventionskonzept."},
    },
    schreibt=True,
)


async def _undo_last_curriculum_change(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=True)
    if isinstance(cur, str):
        return {"error": cur}
    stand = await juengster(ctx.db, cur.id)
    if stand is None:
        return {"ok": False, "error": "Es gibt nichts zurückzunehmen."}
    was = await gegenstand(ctx.db, cur, stand)
    eigen = stand.reason == "assistant" and stand.created_by == ctx.user.sub
    if not eigen and not args.get("auch_fremde"):
        return {"ok": False, "bestaetigung_noetig": True,
                "letzte_aenderung": {"von": stand.reason, "von_mir": stand.created_by == ctx.user.sub,
                                     "zeit": stand.created_at.isoformat(), "gegenstand": was},
                "hinweis": "Die letzte Änderung stammt nicht von dir (Editor oder andere Person). Nichts zurückgenommen. "
                           "Sag der Lehrkraft, von wem und von wann sie ist; nur nach ausdrücklicher "
                           "Bestätigung mit auch_fremde=true zurücknehmen."}
    anzahl = (await verlauf(ctx.db, cur.id, ctx.user.sub))["anzahl"]
    zurueck = await zuruecknehmen(ctx.db, cur)
    return {"ok": True,
            "zurueckgenommen": {"zeit": zurueck["zeit"].isoformat(), "von": zurueck["grund"], "gegenstand": was},
            "verbleibend": anzahl - 1}


_registriere(
    "undo_last_curriculum_change", _undo_last_curriculum_change,
    "Nimmt die letzte Speicherung des Curriculums zurück — nur auf Wunsch der Lehrkraft. Stammt "
    "sie von dir für diese Lehrkraft, sofort. Sonst (im Editor oder von einer anderen Person) "
    "nimmt die Funktion nichts zurück und antwortet mit bestaetigung_noetig und letzte_aenderung "
    "(von: 'editor' oder 'assistant', von_mir, zeit); erst nach ausdrücklicher Bestätigung mit "
    "auch_fremde=true. gegenstand nennt, was zurückgenommen wird: 'rahmen' (Rahmenangaben), "
    "'inhalte' (Kapitel, Lernsequenzen, Einträge) — sag es der Lehrkraft. Danach get_curriculum_draft.",
    {"auch_fremde": {"type": "boolean", "description": (
        "true nimmt auch eine Änderung aus dem Editor oder von einer anderen Person zurück — nur "
        "nach ausdrücklicher Bestätigung der Lehrkraft.")}},
    schreibt=True,
)


# ── Einstieg: finden, wählen, anlegen (0.46, Schritt 6, E18) ──────────────────


async def _bezug_uebernehmen(ctx: ToolContext, cur) -> None:
    """Gilt sofort für die folgenden Aufrufe dieser Anfrage (der Router übernimmt
    `ctx.curriculum_node_id`) und bleibt an der Unterhaltung."""
    from app.context.curriculum_bezug import bezug_setzen

    await bezug_setzen(ctx.db, ctx.conversation_id, ctx.user, cur.id)
    ctx.curriculum_node_id = cur.id
    ctx.stunde_node_id = None


async def _finde_curriculum(args: dict, ctx: ToolContext) -> dict:
    from app.context.curriculum_bezug import curricula_finden

    return await curricula_finden(ctx.db, ctx.user, args.get("fach"), args.get("jahrgangsstufe"))


register_tool(ChatTool(
    name="finde_curriculum", groups=GRUPPE, writes=False, handler=_finde_curriculum,
    definition={"type": "function", "function": {
        "name": "finde_curriculum",
        "description": (
            "Sucht Curricula der Fächer, in denen die Lehrkraft Curricula bearbeiten darf — wenn die "
            "Unterhaltung noch kein Bezugscurriculum hat. Liefert Curricula (Entwurf oder veröffentlicht, "
            "mit offener_entwurf_id) und je Fach die Bildungsplan-Fassungen, für die sich ein neues "
            "anlegen lässt. Passt eines → waehle_curriculum; keines → nach Zustimmung lege_curriculum_an."),
        "parameters": {"type": "object", "properties": {
            "fach": {"type": "string", "description": "Fachname oder Kürzel; ein Teil genügt."},
            "jahrgangsstufe": {"type": "string", "description": "Stufe oder Band, etwa '7' oder '7/8'."},
        }, "required": []},
    }},
))


async def _waehle_curriculum(args: dict, ctx: ToolContext) -> dict:
    from app.context.curriculum_bezug import curriculum_waehlen

    try:
        cid = UUID(str(args.get("curriculum_id") or ""))
    except ValueError:
        return {"error": "Ungültige curriculum_id"}
    cur, antwort = await curriculum_waehlen(ctx.db, ctx.user, cid, bool(args.get("als_entwurf_kopieren")))
    if cur is None:
        return antwort
    await _bezug_uebernehmen(ctx, cur)
    return {**await ca.entwurf_lesen(ctx.db, ctx.user, cur), **antwort, "bezug_gesetzt": True}


register_tool(ChatTool(
    name="waehle_curriculum", groups=GRUPPE, writes=True, handler=_waehle_curriculum,
    definition={"type": "function", "function": {
        "name": "waehle_curriculum",
        "description": (
            "Macht ein Curriculum aus finde_curriculum zum Bezugscurriculum dieser Unterhaltung und "
            "liefert es wie get_curriculum_draft — danach nicht noch einmal get_curriculum_draft. Gibt es zu einem veröffentlichten einen offenen "
            "Entwurf, wird der gewählt. Ein veröffentlichtes ohne Entwurf ist nur zu lesen; "
            "als_entwurf_kopieren=true legt einen Entwurf als Kopie an — frage die Lehrkraft vorher."),
        "parameters": {"type": "object", "properties": {
            "curriculum_id": {"type": "string", "description": "curriculum_id aus finde_curriculum"},
            "als_entwurf_kopieren": {"type": "boolean", "description": "Nur nach Zustimmung."},
        }, "required": ["curriculum_id"]},
    }},
))


async def _lege_curriculum_an(args: dict, ctx: ToolContext) -> dict:
    from app.context.curriculum_bezug import curriculum_neu

    cur, antwort = await curriculum_neu(ctx.db, ctx.user, args.get("fach") or "", args.get("jahrgangsstufe") or "",
                                        args.get("bp_version") or None, args.get("band") or None)
    if cur is None:
        return antwort
    await _bezug_uebernehmen(ctx, cur)
    return {**await ca.entwurf_lesen(ctx.db, ctx.user, cur), **antwort, "bezug_gesetzt": True}


register_tool(ChatTool(
    name="lege_curriculum_an", groups=GRUPPE, writes=True, handler=_lege_curriculum_an,
    definition={"type": "function", "function": {
        "name": "lege_curriculum_an",
        "description": (
            "Legt ein leeres Curriculum als Entwurf an, macht es zum Bezugscurriculum und liefert es "
            "wie get_curriculum_draft (danach nicht noch einmal get_curriculum_draft) — nur nach "
            "Zustimmung der Lehrkraft und nur, wenn finde_curriculum für Fach, Band und Fassung keines "
            "gefunden hat. Gibt es keinen Bildungsplan der Fassung, wird nichts angelegt."),
        "parameters": {"type": "object", "properties": {
            "fach": {"type": "string", "description": "Fachname oder Kürzel"},
            "jahrgangsstufe": {"type": "string", "description": "Stufe oder Band, etwa '7' oder '7/8'"},
            "bp_version": {"type": "string", "description": (
                "Fassung aus finde_curriculum (faecher[].fassungen); nötig, wenn es mehrere gibt.")},
            "band": {"type": "string", "description": (
                "Band des Bildungsplans, nur wenn die Antwort mehrere nennt (Oberstufe: Basis- oder "
                "Leistungsfach) — wörtlich aus baender, nach Rückfrage bei der Lehrkraft.")},
        }, "required": ["fach", "jahrgangsstufe"]},
    }},
))
