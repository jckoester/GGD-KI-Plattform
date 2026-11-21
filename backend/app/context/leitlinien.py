"""Leitlinien der Schule (0.50, Päckchen AT).

Eine **Leitlinie** (`leitbild`) ist ein Rahmenwerk der Schule — die Nachhaltigkeitsziele,
das Weltethos, das Medienkonzept. Ihre Punkte sind **Aspekte** (`leitbild_aspekt`). Beide
pflegen nur Admins (`write_scope: school`); lesen dürfen alle, auch Schüler:innen.

Verbunden sind beide über **Kürzel**, nicht über Kanten: Die Leitlinie trägt
``metadata.kuerzel`` („SDG“), der Aspekt sein eigenes Kürzel („SDG13“) und in
``metadata.leitlinie`` das Kürzel seiner Leitlinie. Das Kürzel ist Pflicht und je Typ
eindeutig (Plan F8) — es trägt den portablen Export (`lb:SDG`, `lba:SDG13`) und die
Auflösung im Curriculum-Assistenten. Ein Titel kann sich ändern, das Kürzel nicht.

Warum keine `part_of`-Kante zwischen Aspekt und Leitlinie: Der Baum entstünde dann erst
aus einer Kantenabfrage je Leitlinie, das Formular der Sammlung kann keine Kante setzen,
und die Zuordnung stünde an zwei Orten. Das Kürzel steht ohnehin am Aspekt.
"""
from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ContextNode

LEITLINIE = "leitbild"
ASPEKT = "leitbild_aspekt"
LEITLINIEN_TYPEN: tuple[str, ...] = (LEITLINIE, ASPEKT)

#: Status, in denen ein Kürzel belegt ist. Ein archivierter Knoten hält sein Kürzel —
#: Curricula verweisen weiter auf ihn, und ein Export muss ihn eindeutig benennen.
_BELEGT = ("active", "archived")


def kuerzel_normalisieren(wert: str | None) -> str:
    """Kürzel vergleichbar machen: ohne Ränder und Leerzeichen, in Großbuchstaben.

    „SDG 13“, „sdg13“ und „SDG13“ meinen dasselbe — so tippen es Menschen und Modelle.
    """
    return "".join(str(wert or "").split()).upper()


async def pruefe_leitlinie(
    db: AsyncSession,
    content_type: str | None,
    metadata: dict | None,
    node_id: UUID | None = None,
    vorher: dict | None = None,
) -> dict | None:
    """Kürzel prüfen und vereinheitlicht zurückgeben. Wirft ``ValueError``.

    - Das Kürzel ist Pflicht und je Typ eindeutig (ohne den Knoten selbst).
    - Ein Aspekt nennt eine vorhandene Leitlinie.
    - Eine Leitlinie behält ihr Kürzel, solange Aspekte es nennen (``vorher``: die
      Metadaten vor der Änderung) — sonst hingen sie lautlos an nichts.

    Andere Typen bleiben unberührt (Rückgabe: die Metadaten, wie sie kamen).
    """
    if content_type not in LEITLINIEN_TYPEN:
        return metadata
    meta = dict(metadata or {})
    kuerzel = kuerzel_normalisieren(meta.get("kuerzel"))
    if not kuerzel:
        raise ValueError("Das Kürzel fehlt — es ist für Leitlinien und ihre Aspekte Pflicht.")
    meta["kuerzel"] = kuerzel

    belegt = await db.execute(
        sa.select(ContextNode.id, ContextNode.title).where(
            ContextNode.content_type == content_type,
            ContextNode.status.in_(_BELEGT),
            ContextNode.id != node_id if node_id else sa.true(),
            sa.func.upper(sa.func.replace(ContextNode.metadata_["kuerzel"].astext, " ", "")) == kuerzel,
        )
    )
    if (zeile := belegt.first()) is not None:
        raise ValueError(f"Das Kürzel „{kuerzel}“ trägt schon „{zeile.title}“.")

    alt = kuerzel_normalisieren((vorher or {}).get("kuerzel"))
    if content_type == LEITLINIE and alt and alt != kuerzel:
        haengen = (await db.execute(
            sa.select(sa.func.count()).select_from(ContextNode).where(
                ContextNode.content_type == ASPEKT,
                ContextNode.status.in_(_BELEGT),
                sa.func.upper(sa.func.replace(ContextNode.metadata_["leitlinie"].astext, " ", "")) == alt,
            )
        )).scalar_one()
        if haengen:
            raise ValueError(f"Das Kürzel „{alt}“ nennen {haengen} Aspekte — es bleibt, solange es sie gibt.")

    if content_type == ASPEKT:
        leitlinie = kuerzel_normalisieren(meta.get("leitlinie"))
        if not leitlinie:
            raise ValueError("Zu welcher Leitlinie gehört der Aspekt? Ihr Kürzel fehlt.")
        if await leitlinie_zum_kuerzel(db, leitlinie) is None:
            vorhanden = ", ".join(l.kuerzel for l in await alle_leitlinien(db)) or "noch keine"
            raise ValueError(f"Eine Leitlinie „{leitlinie}“ gibt es nicht. Vorhanden: {vorhanden}.")
        meta["leitlinie"] = leitlinie
    return meta


async def _zum_kuerzel(db: AsyncSession, typ: str, kuerzel: str) -> ContextNode | None:
    gesucht = kuerzel_normalisieren(kuerzel)
    if not gesucht:
        return None
    ergebnis = await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type == typ,
            ContextNode.status.in_(_BELEGT),
            sa.func.upper(sa.func.replace(ContextNode.metadata_["kuerzel"].astext, " ", "")) == gesucht,
        ).order_by(ContextNode.status != "active")
    )
    return ergebnis.scalars().first()


async def leitlinie_zum_kuerzel(db: AsyncSession, kuerzel: str) -> ContextNode | None:
    return await _zum_kuerzel(db, LEITLINIE, kuerzel)


async def aspekt_zum_kuerzel(db: AsyncSession, kuerzel: str) -> ContextNode | None:
    return await _zum_kuerzel(db, ASPEKT, kuerzel)


@dataclass
class Aspekt:
    id: UUID
    kuerzel: str
    titel: str


@dataclass
class Leitlinie:
    id: UUID
    kuerzel: str
    titel: str
    aspekte: list[Aspekt]


async def alle_leitlinien(db: AsyncSession) -> list[Leitlinie]:
    """Alle aktiven Leitlinien mit ihren aktiven Aspekten, nach Kürzel geordnet.

    Leitlinien sind `read_scope: school` — für alle Angemeldeten lesbar. Eine Prüfung je
    Person braucht es deshalb nicht.
    """
    zeilen = (await db.execute(
        sa.select(ContextNode).where(
            ContextNode.content_type.in_(LEITLINIEN_TYPEN),
            ContextNode.status == "active",
        )
    )).scalars().all()
    leitlinien = {
        kuerzel_normalisieren((n.metadata_ or {}).get("kuerzel")): Leitlinie(
            n.id, kuerzel_normalisieren((n.metadata_ or {}).get("kuerzel")), n.title, [])
        for n in zeilen if n.content_type == LEITLINIE
    }
    for n in zeilen:
        if n.content_type != ASPEKT:
            continue
        meta = n.metadata_ or {}
        ziel = leitlinien.get(kuerzel_normalisieren(meta.get("leitlinie")))
        if ziel is not None:
            ziel.aspekte.append(Aspekt(n.id, kuerzel_normalisieren(meta.get("kuerzel")), n.title))
    for l in leitlinien.values():
        l.aspekte.sort(key=lambda a: _natuerlich(a.kuerzel))
    return sorted(leitlinien.values(), key=lambda l: l.kuerzel)


def _natuerlich(kuerzel: str) -> list:
    """„SDG2“ vor „SDG13“."""
    import re

    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", kuerzel)]


# ── Verweise im Hinweise-Feld für den Curriculum-Assistenten (0.50, AT Schritt 10/11) ────
#
# Im Editor setzt die Lehrkraft Verweise als Token (`@[Label](lb:<uuid>)`). Das Modell kennt
# keine UUIDs; es nennt Kürzel in eigenen Feldern (`leitlinien`, `leitperspektiven`), und der
# Server macht daraus die Token. Beim Lesen umgekehrt: Die Token verschwinden aus `hinweise`
# und stehen als Kürzel in denselben Feldern — so sieht das Modell, was es schreiben kann.
#
# Leitperspektiven als Ganzes (`lp:`, Kürzel „BNE“) und ihre Aspekte (`lpa:`, Kennung „BNE_03“
# aus der `bp_id`, dieselbe wie im YAML-Export). Im Curriculum ist der Verweis auf den einzelnen
# Aspekt der Regelfall (Jan, 21.11.2026). Die Aspekte holt das Modell auf Abruf
# (`get_bp_competences` mit `typ='lp'`), nicht mit jedem Lesen des Curriculums.

import re as _re

_TOKEN = _re.compile(r"\s*@\[([^\]]*)\]\((lba|lb|lpa|lp):([0-9a-f-]{36})\)")
_LP_ASPEKT = _re.compile(r"^([A-ZÄÖÜ]+)[\s_\-.:]*0*(\d+)$")


@dataclass
class Verweisziele:
    """Wohin ein Kürzel zeigt und wie ein Token zurück zum Kürzel kommt."""

    #: KÜRZEL → (Art, node_id, Label) — Art `lb`/`lba`
    leitlinien: dict[str, tuple[str, UUID, str]]
    #: KÜRZEL → (Art, node_id, Label) — Art `lp` („BNE“) oder `lpa` („BNE_03“)
    leitperspektiven: dict[str, tuple[str, UUID, str]]
    #: Leitperspektiven mit ihren Aspekten, für `get_bp_competences` mit `typ='lp'`
    lp_liste: list[dict]
    #: node_id (str) → Kürzel, für beide
    kuerzel_von: dict[str, str]
    #: Titel (casefold) → Kürzel, für Namen statt Kürzel
    titel_index: dict[str, str]
    #: für die Übersicht des Assistenten
    liste: list[Leitlinie]


async def verweisziele(db: AsyncSession) -> Verweisziele:
    from app.context.service import leitperspektive_code

    liste = await alle_leitlinien(db)
    ll: dict[str, tuple[str, UUID, str]] = {}
    for l in liste:
        ll[l.kuerzel] = ("lb", l.id, l.titel)
        for a in l.aspekte:
            ll[a.kuerzel] = ("lba", a.id, f"{a.kuerzel}: {a.titel}")
    lp: dict[str, tuple[str, UUID, str]] = {}
    lp_liste: dict[str, dict] = {}
    titel: dict[str, str] = {}
    knoten = (await db.execute(sa.select(ContextNode).where(
        ContextNode.content_type.in_(("leitperspektive", "leitperspektive_aspekt")),
        ContextNode.status == "active"))).scalars().all()
    for n in knoten:
        if n.content_type == "leitperspektive" and (code := leitperspektive_code(n.metadata_)):
            lp[code] = ("lp", n.id, n.title)
            titel[code] = n.title
            lp_liste[code] = {"kuerzel": code, "titel": n.title, "aspekte": []}
    for n in knoten:
        meta = n.metadata_ or {}
        bp_id = str(meta.get("bp_id") or "").upper()
        if n.content_type != "leitperspektive_aspekt" or not bp_id:
            continue
        code, _, _ = bp_id.partition("_")
        # Beschriftung wie im Editor (`HinweisEditor.svelte`): „BNE 3: <Titel, gekürzt auf 80>“
        nr = meta.get("aspekt_nr")
        kurz = n.title if len(n.title) <= 80 else n.title[:79] + "…"
        lp[bp_id] = ("lpa", n.id, f"{code} {nr}: {kurz}" if nr is not None else f"{code}: {kurz}")
        titel[bp_id] = n.title
        if code in lp_liste:
            lp_liste[code]["aspekte"].append({"kuerzel": bp_id, "titel": n.title})
    for eintrag in lp_liste.values():
        eintrag["aspekte"].sort(key=lambda a: _natuerlich(a["kuerzel"]))
    kuerzel_von = {str(v[1]): k for k, v in ll.items()} | {str(v[1]): k for k, v in lp.items()}
    titel_index = {v[2].split(": ", 1)[-1].casefold(): k for k, v in ll.items()}
    titel_index |= {t.casefold(): k for k, t in titel.items()}
    return Verweisziele(ll, lp, sorted(lp_liste.values(), key=lambda e: e["kuerzel"]),
                        kuerzel_von, titel_index, liste)


def tokens_trennen(text: str | None) -> tuple[str, list[str], list[str]]:
    """Hinweise ohne `lb`/`lba`/`lp`/`lpa`-Token — und die Token, getrennt nach Leitlinien und LP."""
    lb, lp = [], []
    for m in _TOKEN.finditer(text or ""):
        (lp if m.group(2) in ("lp", "lpa") else lb).append(m.group(0).strip())
    return _TOKEN.sub("", text or "").strip(), lb, lp


def tokens_zusammen(text: str, tokens: list[str]) -> str:
    return " ".join(t for t in [text.strip(), *tokens] if t)


def _uuid_im_token(token: str) -> str:
    return token.rsplit(":", 1)[-1].rstrip(")")


def kuerzel_der_tokens(tokens: list[str], ziele: Verweisziele) -> list[str]:
    """Kürzel zu Token; ein Token ohne bekanntes Ziel (archiviert, fremd) erscheint als „?“."""
    return [ziele.kuerzel_von.get(_uuid_im_token(t), "?") for t in tokens]


def leitlinien_tokens(namen, ziele: Verweisziele) -> list[str]:
    """Kürzel oder Titel → Token. Wirft ``ValueError`` mit den möglichen Kürzeln."""
    if not isinstance(namen, list):
        raise ValueError("leitlinien muss eine Liste von Kürzeln sein")
    aus = []
    for name in namen:
        k = kuerzel_normalisieren(name)
        k = k if k in ziele.leitlinien else ziele.titel_index.get(str(name).strip().casefold(), k)
        if k not in ziele.leitlinien:
            moeglich = ", ".join(ziele.leitlinien) or "keine — die Schule hat keine Leitlinien hinterlegt"
            raise ValueError(f"Leitlinie „{name}“ gibt es nicht. Möglich: {moeglich}")
        art, nid, label = ziele.leitlinien[k]
        token = f"@[{label}]({art}:{nid})"
        if token not in aus:
            aus.append(token)
    return aus


def lp_kuerzel_normalisieren(name) -> str:
    """„BNE“, „(L) BNE“ → „BNE“; „BNE 3“, „bne3“, „BNE_3“, „BNE-03“ → „BNE_03“."""
    from app.context.service import normalize_lp_code

    k = normalize_lp_code(str(name))
    if m := _LP_ASPEKT.match(k):
        return f"{m.group(1)}_{int(m.group(2)):02d}"
    return k


def leitperspektiven_tokens(namen, ziele: Verweisziele) -> list[str]:
    """Kürzel einer Leitperspektive („BNE“) oder eines Aspekts („BNE_03“), auch Titel → Token.
    Wirft ``ValueError``."""
    if not isinstance(namen, list):
        raise ValueError("leitperspektiven muss eine Liste von Kürzeln sein")
    aus = []
    for name in namen:
        k = lp_kuerzel_normalisieren(name)
        k = k if k in ziele.leitperspektiven else ziele.titel_index.get(str(name).strip().casefold(), k)
        if k not in ziele.leitperspektiven:
            koepfe = ", ".join(e["kuerzel"] for e in ziele.lp_liste)
            raise ValueError(f"Leitperspektive „{name}“ gibt es nicht. Möglich: {koepfe} oder ein Aspekt "
                             "wie BNE_03 (get_bp_competences mit typ='lp')")
        art, nid, label = ziele.leitperspektiven[k]
        token = f"@[{label}]({art}:{nid})"
        if token not in aus:
            aus.append(token)
    return aus
