"""Funktionen des Curriculum-Assistenten (0.46, Päckchen AP Teil B, Schritt 5).

Fähigkeit `curriculum_planning`. Die Arbeit steht in `app/context/curriculum_assistent.py`;
hier nur Schema und Übergabe. Jede Funktion prüft den Zugang am Curriculum selbst
(`zugang`, dieselbe Regel wie im Editor) — der Bezug der Unterhaltung (`curriculum_node_id`)
ist eine Vorgabe, keine Erlaubnis. Geschrieben wird nur in Entwürfe (E17), jeder schreibende
Aufruf sichert vorher den Stand (Rückgängig im Editor und `undo_last_curriculum_change`).
"""
from __future__ import annotations

from uuid import UUID

from app.chat.tools import ChatTool, ToolContext, register_tool
from app.context import curriculum_assistent as ca
from app.context.curriculum_verlauf import verlauf, zuruecknehmen

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
    "Nummern (ik, ik_teilweise, pk); Begriffe mit zustand (gefunden, fehlt, mehrdeutig). "
    "Kennungen (id) und Eintragsnummern brauchst du für apply_curriculum_operations. "
    "status 'draft' = Entwurf; in andere schreibst du nicht.",
)


async def _get_bp_competences(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=False)
    if isinstance(cur, str):
        return {"error": cur}
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
        "typ": {"type": "string", "enum": ["ik", "pk"], "description": (
            "ik = inhaltsbezogene Kompetenzen (Vorgabe), pk = prozessbezogene (gelten fürs ganze Fach).")},
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
    "ungenutzt sind. Nenne Zahlen nur aus dieser Funktion.",
)


async def _get_hour_frame(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=False)
    if isinstance(cur, str):
        return {"error": cur}
    return await ca.stundenrahmen(ctx.db, cur)


_registriere(
    "get_hour_frame", _get_hour_frame,
    "Stundenbilanz: verplanbar (30 Stunden je Wochenstunde aus den Rahmenangaben, über alle "
    "Stufen des Bands), verplant (Summe der Lernsequenzen), rest. verplanbar ist null, solange "
    "Wochenstunden fehlen. Rechne nicht selbst.",
)


# ── Schreiben ────────────────────────────────────────────────────────────────


async def _apply_curriculum_operations(args: dict, ctx: ToolContext) -> dict:
    cur = await _curriculum(args, ctx, schreiben=True)
    if isinstance(cur, str):
        return {"error": cur}
    return await ca.operationen_anwenden(ctx.db, ctx.user, cur, args.get("operations"))


_registriere(
    "apply_curriculum_operations", _apply_curriculum_operations,
    "Schreibt einen Stapel Änderungen in den Entwurf — nur nach Zustimmung der Lehrkraft. Ganz "
    "oder gar nicht: Passt eine Operation nicht (etwa eine Kompetenznummer außerhalb des Bands), "
    "wird nichts geschrieben und fehler nennt, was. Vorher wird der Stand gesichert; "
    "undo_last_curriculum_change nimmt den Stapel zurück. Die Stunden eines Kapitels sind die "
    "Summe seiner Lernsequenzen.",
    {
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
            "hinweise?, material?, begriffe?, fachmethoden?, position?}: ik, ik_teilweise, pk als "
            "Listen von Nummern aus get_bp_competences; begriffe und fachmethoden als Listen von "
            "Namen\n"
            "- eintrag_aendern{lernsequenz_id, eintrag, …}: eintrag = Nummer ab 1; genannte Felder "
            "ersetzen die bisherigen, andere bleiben\n"
            "- eintrag_loeschen{lernsequenz_id, eintrag}")},
    },
    ["operations"], schreibt=True,
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
    "Hält Rahmenangaben aus dem Gespräch fest, damit spätere Sitzungen nicht neu fragen. Nur die "
    "genannten Felder ändern sich; leerer Text löscht ein Feld. Das Lehrwerk ist nur ein Name: "
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
    vorher = await verlauf(ctx.db, cur.id, ctx.user.sub)
    if not vorher["anzahl"]:
        return {"ok": False, "error": "Es gibt nichts zurückzunehmen."}
    stand = await zuruecknehmen(ctx.db, cur)
    return {"ok": True, "zurueckgenommen": {"zeit": stand["zeit"].isoformat(), "von": stand["grund"]},
            "verbleibend": vorher["anzahl"] - 1}


_registriere(
    "undo_last_curriculum_change", _undo_last_curriculum_change,
    "Nimmt die letzte Speicherung des Curriculums zurück — die eigene oder eine im Editor "
    "(von: 'assistant' oder 'editor'). Nur auf Wunsch der Lehrkraft; danach get_curriculum_draft.",
    schreibt=True,
)
