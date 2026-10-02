import asyncio
import logging
from datetime import date
from pathlib import Path
from typing import Literal, Optional

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_any_role
from app.auth.jwt import JwtPayload
from app.budget.exchange import get_current_rate
from app.budget.forecast import Hochrechnung, hochrechnen, verlauf
from app.budget.schulwochen import anzahl_unterrichtswochen, unterrichtswochen, wochen_bis
from app.budget.tiers import (
    _load_budget_tiers,
    _stufe,
    einheiten_je_euro,
    invalidate_budget_tiers_cache,
)
from app.budget.zuschlag import buche_auf
from app.config import settings
from app.core.paths import aufloesen
from app.db.models import Group, GroupMembership, PseudonymAudit
from app.db.session import get_db
from app.planning.calendar import load_school_year
from app.litellm.client import LiteLLMClient
from app.litellm.teams import STUDENT_TEAM_PREFIX, TEACHER_TEAM_ID, VALID_GRADES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budgets", tags=["admin-budgets"])


# Pydantic-Modelle
class GradeInfo(BaseModel):
    key: str  # "jahrgang-5"..."jahrgang-12" | "lehrkraefte"
    label: str  # "Jahrgang 5"..."Jahrgang 12" | "Lehrkräfte"
    grade: Optional[int]  # None für Lehrkräfte
    max_budget_eur: float  # Betrag je **Unterrichtswoche**
    user_count: int  # Nutzer in pseudonym_audit


class HochrechnungInfo(BaseModel):
    """Läuft die Schule auf ihre Jahreszusage zu — und wie belastbar ist die Aussage?"""

    verbraucht_eur: float
    wochen_vergangen: int
    wochen_gesamt: int
    erwartet_eur: Optional[float]
    zugeteilt_eur: Optional[float]
    #: False in den ersten Wochen: Dann verdoppelt eine einzelne Projektwoche die Zahl.
    belastbar: bool


class VerlaufInfo(BaseModel):
    """Eine Kalenderwoche des Schuljahres: kumulierte Zusage und kumulierter Verbrauch."""

    montag: date
    soll_eur: float
    ist_eur: Optional[float]  # None = Woche hat noch nicht begonnen
    unterricht: bool


class BudgetGradesResponse(BaseModel):
    grades: list[GradeInfo]  # aufsteigend nach grade, Lehrkräfte am Ende
    eur_usd_rate: float
    # Zahl, mit der ein Wochenbetrag zur Jahressumme wird (aus school_year.yaml).
    # `None`, wenn die Datei fehlt oder unlesbar ist — die Oberfläche lässt die
    # Jahressumme dann weg, statt eine erfundene Zahl zu zeigen.
    unterrichtswochen: Optional[int]
    hochrechnung: Optional[HochrechnungInfo]
    #: Ist gegen Soll je Kalenderwoche (0.12, AP2). Leer, wenn sich der Verlauf nicht
    #: ermitteln lässt — die Seite bleibt dann ohne Diagramm benutzbar.
    verlauf: list[VerlaufInfo] = []


class GradeUpdate(BaseModel):
    key: str
    max_budget_eur: float


class BudgetGradesUpdateRequest(BaseModel):
    grades: list[GradeUpdate]


class BudgetGradesUpdateResult(BaseModel):
    ok: bool
    updated_users: int


@router.get("/grades", response_model=BudgetGradesResponse)
async def get_budget_grades(
    _: JwtPayload = Depends(require_any_role(["budget", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BudgetGradesResponse:
    """
    Gibt die Budget-Einstellungen pro Jahrgang/Rolle zurück.
    Enthält auch die Nutzerzahlen aus der pseudonym_audit-Tabelle.
    """
    # YAML laden
    config = _load_budget_tiers()

    # Nutzeranzahl aus pseudonym_audit
    result = await db.execute(
        text("SELECT role, grade, COUNT(*)::int FROM pseudonym_audit GROUP BY role, grade")
    )
    counts = {(row[0], row[1]): row[2] for row in result.fetchall()}

    # GradeInfo-Liste bauen
    rows = []
    for g in sorted(VALID_GRADES):
        rows.append(GradeInfo(
            key=f"{STUDENT_TEAM_PREFIX}{g}",
            label=f"Jahrgang {g}",
            grade=g,
            max_budget_eur=_stufe(config.get("grades", {}).get(g, {})) or 0.0,
            user_count=counts.get(("student", g), 0),
        ))

    teacher_count = sum(v for (role, _), v in counts.items() if role == "teacher")
    rows.append(GradeInfo(
        key=TEACHER_TEAM_ID,
        label="Lehrkräfte",
        grade=None,
        max_budget_eur=_stufe(config.get("roles", {}).get("teacher", {})) or 0.0,
        user_count=teacher_count,
    ))

    # EUR/USD-Kurs
    eur_usd_rate = await get_current_rate(db)

    wochen: Optional[int] = None
    try:
        wochen = anzahl_unterrichtswochen()
    except Exception:
        # Fehlende oder kaputte school_year.yaml darf die Budget-Seite nicht
        # unbenutzbar machen — die Oberfläche lässt die Jahressumme dann weg.
        logger.exception("Unterrichtswochen nicht ermittelbar")

    hochrechnung, verlauf_punkte = await _hochrechnung(db, rows, wochen, eur_usd_rate)
    return BudgetGradesResponse(
        grades=rows, eur_usd_rate=eur_usd_rate, unterrichtswochen=wochen,
        hochrechnung=hochrechnung, verlauf=verlauf_punkte,
    )


async def _wochenverbrauch(db: AsyncSession, beginn: date, eur_usd: float) -> dict[date, float]:
    """Verbrauch je Kalenderwoche (Montag, Ortszeit) seit Schuljahresbeginn, in Euro.

    ⚠️ **Die einzige Quelle für den Verbrauch auf dieser Seite.** Die Hochrechnung
    summiert genau diese Wochen, der Verlauf kumuliert sie — der letzte Punkt der
    Ist-Linie ist damit die Zahl „bisher verbraucht", per Konstruktion und nicht, weil
    zwei Abfragen zufällig übereinstimmen.
    """
    zeilen = (await db.execute(
        text(
            "SELECT (DATE_TRUNC('week', m.created_at AT TIME ZONE 'Europe/Berlin'))::date "
            "AS montag, COALESCE(SUM(m.cost_usd), 0)::float AS summe "
            "FROM messages m WHERE m.cost_usd IS NOT NULL AND m.created_at >= :beginn "
            "GROUP BY 1"
        ),
        {"beginn": beginn},
    )).all()
    return {z.montag: z.summe / eur_usd for z in zeilen}


async def _hochrechnung(
    db: AsyncSession, rows: list[GradeInfo], wochen: Optional[int], eur_usd: float
) -> tuple[Optional[HochrechnungInfo], list[VerlaufInfo]]:
    """Bisheriger Verbrauch im laufenden Schuljahr, hochgerechnet aufs ganze Jahr.

    Der Verbrauch kommt aus der **eigenen** Datenbank (`messages.cost_usd`), nicht vom
    Proxy: Dort wäre er nur je Nutzer abrufbar, und 800 Einzelabfragen für eine
    Übersichtsseite verbieten sich.

    ⚠️ Die Spalte heißt historisch `cost_usd`, führt aber die Einheit der LiteLLM-Preise —
    im Euro-Betrieb also Euro (siehe `LITELLM_PRICE_CURRENCY`). Deshalb wird hier **nicht**
    umgerechnet: `get_current_rate` liefert dann 1,0, und eine zweite Division wäre falsch.
    """
    if not wochen:
        return None, []
    try:
        cfg = load_school_year()
        heute = date.today()
        vergangen = len(wochen_bis(heute, cfg))
        je_woche = await _wochenverbrauch(db, cfg.beginn, eur_usd)
        verbraucht = sum(je_woche.values())
        wochensumme = sum(r.max_budget_eur * r.user_count for r in rows)
        zugeteilt = wochensumme * wochen
        h: Hochrechnung = hochrechnen(
            verbraucht_eur=verbraucht,
            wochen_vergangen=vergangen,
            wochen_gesamt=wochen,
            zugeteilt_eur=zugeteilt or None,
        )
        punkte = verlauf(
            beginn=cfg.beginn,
            ende=cfg.ende,
            unterrichts_montage={w.montag for w in unterrichtswochen(cfg)},
            wochensumme_eur=wochensumme,
            ist_je_woche=je_woche,
            heute=heute,
        )
        return HochrechnungInfo(**h.__dict__), [VerlaufInfo(**p.__dict__) for p in punkte]
    except Exception:
        # Die Budget-Seite muss ohne die Hochrechnung benutzbar bleiben — sie ist
        # Zusatzinformation, nicht ihr Zweck.
        logger.exception("Hochrechnung nicht ermittelbar")
        return None, []


@router.post("/grades", response_model=BudgetGradesUpdateResult)
async def update_budget_grades(
    body: BudgetGradesUpdateRequest,
    _: JwtPayload = Depends(require_any_role(["budget", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> BudgetGradesUpdateResult:
    """
    Aktualisiert die budgets pro Jahrgang/Rolle.
    
    - Validiert, dass alle max_budget_eur > 0 sind
    - Validiert, dass alle Keys bekannt sind (jahrgang-5...jahrgang-12 oder lehrkraefte)
    - Schreibt die YAML atomar (tmp + replace)
    - Invalidiert den Cache
    - Aktualisiert alle betroffenen LiteLLM-User-Budgets parallel
    """
    # 1. Validieren: max_budget_eur > 0 für alle Einträge
    for update in body.grades:
        if update.max_budget_eur <= 0:
            raise HTTPException(
                status_code=422,
                detail=f"max_budget_eur muss > 0 sein, erhalten: {update.max_budget_eur} für {update.key}"
            )

    # 2. Bekannte Keys bestimmen
    valid_keys = {f"{STUDENT_TEAM_PREFIX}{g}" for g in VALID_GRADES} | {TEACHER_TEAM_ID}
    unknown = {u.key for u in body.grades} - valid_keys
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unbekannte Keys: {sorted(unknown)}"
        )

    # 3. YAML lesen (aktueller Stand)
    config_path = aufloesen(settings.budget_tiers_path)
    with open(config_path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # 4. YAML-Struktur aktualisieren
    def _eintrag(key: str) -> dict:
        if key == TEACHER_TEAM_ID:
            return raw.setdefault("roles", {}).setdefault("teacher", {})
        grade = int(key[len(STUDENT_TEAM_PREFIX):])
        return raw.setdefault("grades", {}).setdefault(grade, {})

    for update in body.grades:
        eintrag = _eintrag(update.key)
        eintrag["wochenbudget_eur"] = update.max_budget_eur
        # Reste des Monatsmodells mit ausräumen, falls die Datei noch welche trägt.
        eintrag.pop("max_budget_eur", None)
        eintrag.pop("budget_duration", None)

    # 5. Atomar schreiben
    tmp = config_path.with_suffix(".yaml.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        yaml.dump(raw, f, allow_unicode=True, default_flow_style=False)
    tmp.replace(config_path)

    # 6. Cache invalidieren
    invalidate_budget_tiers_cache()

    # 7. Betroffene Nutzer ermitteln (geänderte Keys)
    changed_keys = {u.key for u in body.grades}
    tasks = []  # [(pseudonym, new_eur)]
    
    for update in body.grades:
        if update.key == TEACHER_TEAM_ID:
            result = await db.execute(
                text("SELECT pseudonym FROM pseudonym_audit WHERE role = 'teacher'")
            )

        else:
            grade = int(update.key[len(STUDENT_TEAM_PREFIX):])
            result = await db.execute(
                text("SELECT pseudonym FROM pseudonym_audit WHERE role = 'student' AND grade = :g"),
                {"g": grade}
            )


        for row in result.fetchall():
            tasks.append((row[0], update.max_budget_eur))

    # 8. LiteLLM-Budgets parallel aktualisieren
    eur_usd = await get_current_rate(db)
    sem = asyncio.Semaphore(10)
    success = 0

    async def update_one(pseudonym: str, eur: float) -> None:
        nonlocal success
        async with sem:
            usd = round(eur * eur_usd, 2)
            client = LiteLLMClient()
            try:
                await client.update_user_budget(pseudonym, usd)
                success += 1
                logger.info("Budget-Update erfolgreich für %s: %.2f USD", pseudonym, usd)
            except Exception:
                logger.exception("Budget-Update fehlgeschlagen für %s", pseudonym)
            finally:
                await client.close()

    try:
        await asyncio.gather(*[update_one(p, e) for p, e in tasks])
    except Exception:
        logger.exception("Fehler beim parallelen Budget-Update")

    logger.info("Budget-Update abgeschlossen: %d/%d Nutzer erfolgreich aktualisiert", success, len(tasks))

    return BudgetGradesUpdateResult(ok=True, updated_users=success)


# ── Zuschläge von Hand (0.12, Paket 2, AP1) ───────────────────────────────────
#
# Einzelne Person oder Gruppe, je Mitglied ein Betrag (F1), endet mit dem Schuljahr (F2),
# vergeben von allen, die Budget verwalten (F3). Die Rechnung dahinter steht in
# `app/budget/accrual.py`, der Ablauf in `app/budget/zuschlag.py`.
#
# **Kein fest eingebauter Höchstbetrag.** Gegen einen Tippfehler (5,00 → 500) schützt der
# Probelauf: Er nennt Anzahl und Summe, **bevor** gebucht wird — „28 × 5 € = 140 €" ist
# eine andere Entscheidung als „5 €". Eine feste Grenze im Code wäre eine Schulentscheidung,
# die jemand anderes getroffen hat.

Mitgliederwahl = Literal["alle", "schueler", "lehrkraefte"]


class ZuschlagAnfrage(BaseModel):
    betrag_eur: float = Field(gt=0, description="Je Person, nicht für die ganze Gruppe.")
    grund: str = Field(min_length=3, max_length=500)
    pseudonym: Optional[str] = None
    gruppe_id: Optional[int] = None
    #: Nur bei Gruppen. ⚠️ Eine Unterrichtsgruppe hat auch Lehrkräfte als Mitglieder —
    #: „alle" träfe bei „Klasse 7b" die Lehrkraft mit.
    mitglieder: Mitgliederwahl = "alle"
    #: Nur zählen und rechnen, nichts buchen.
    probelauf: bool = False

    @model_validator(mode="after")
    def _genau_ein_ziel(self) -> "ZuschlagAnfrage":
        if (self.pseudonym is None) == (self.gruppe_id is None):
            raise ValueError("Genau eines angeben: pseudonym oder gruppe_id.")
        return self


class ZuschlagVorschau(BaseModel):
    anzahl: int
    schueler: int
    lehrkraefte: int
    #: Mitglieder ohne Rolle in der Gruppe — werden bei „schueler"/„lehrkraefte" nicht
    #: getroffen, bei „alle" schon.
    ohne_rolle: int
    betrag_eur: float
    summe_eur: float
    einheiten_je_person: int
    gruppenname: Optional[str] = None


class ZuschlagErgebnis(BaseModel):
    gebucht: int
    fehlgeschlagen: list[str]
    unbegrenzt: list[str]


#: So viele Zeichen zeigt das Profil als **Kennung**. 12 Hex-Zeichen sind 48 Bit — bei
#: einigen hundert Konten ist ein Zusammenfall praktisch ausgeschlossen, und falls doch,
#: meldet die Auflösung ihn, statt zu raten.
KENNUNG_LAENGE = 12


async def _person_zur_kennung(db: AsyncSession, eingabe: str) -> PseudonymAudit:
    """Volles Pseudonym oder Kennung (die ersten 12 Zeichen) → das Konto.

    **Warum eine Kennung.** Der Server kennt keine Namen — das ist das
    Pseudonymisierungsprinzip, und es bleibt unberührt. Wer einer Lehrkraft etwas
    aufbuchen will, braucht deshalb deren Mitwirkung: Sie liest ihre Kennung im Profil ab
    und nennt sie. Den Namen erfährt dabei nur der Mensch, nie der Server.

    Leerzeichen und Großschreibung werden ignoriert — das Profil zeigt die Kennung in
    Vierergruppen („a3f9 c2b8 1e04"), damit sie sich vorlesen lässt.
    """
    kennung = "".join(eingabe.split()).lower()
    if len(kennung) < KENNUNG_LAENGE or any(z not in "0123456789abcdef" for z in kennung):
        raise HTTPException(
            422, detail=f"Eine Kennung hat {KENNUNG_LAENGE} Zeichen aus 0–9 und a–f."
        )
    treffer = (await db.execute(
        select(PseudonymAudit)
        .where(PseudonymAudit.pseudonym.startswith(kennung))
        .limit(2)
    )).scalars().all()
    if not treffer:
        # Früh und deutlich: Sonst schlüge erst der Proxy fehl, und die Meldung spräche
        # von einer Störung statt von einem Tippfehler.
        raise HTTPException(404, detail="Diese Kennung ist nicht bekannt.")
    if len(treffer) > 1:
        raise HTTPException(
            409, detail="Diese Kennung ist nicht eindeutig — bitte mehr Zeichen angeben."
        )
    return treffer[0]


async def _ziele(db: AsyncSession, anfrage: ZuschlagAnfrage) -> tuple[list[tuple[str, Optional[str]]], Optional[str]]:
    """(Pseudonym, Rolle in der Gruppe) je Ziel — plus Gruppenname für die Vorschau."""
    if anfrage.pseudonym is not None:
        bekannt = await _person_zur_kennung(db, anfrage.pseudonym)
        return [(bekannt.pseudonym, bekannt.role)], None

    gruppe = await db.get(Group, anfrage.gruppe_id)
    if gruppe is None:
        raise HTTPException(404, detail="Gruppe nicht gefunden.")
    zeilen = (await db.execute(
        select(GroupMembership.pseudonym, GroupMembership.role_in_group)
        .where(GroupMembership.group_id == anfrage.gruppe_id)
    )).all()
    filter_rolle = {"schueler": "student", "lehrkraefte": "teacher"}.get(anfrage.mitglieder)
    if filter_rolle is not None:
        zeilen = [z for z in zeilen if z.role_in_group == filter_rolle]
    return [(z.pseudonym, z.role_in_group) for z in zeilen], gruppe.anzeigename


@router.post("/grants", response_model=ZuschlagVorschau | ZuschlagErgebnis)
async def zuschlag_buchen(
    anfrage: ZuschlagAnfrage,
    db: AsyncSession = Depends(get_db),
    current_user: JwtPayload = Depends(require_any_role(["budget", "admin"])),
):
    ziele, gruppenname = await _ziele(db, anfrage)
    if not ziele:
        raise HTTPException(422, detail="Die Auswahl trifft niemanden.")

    if anfrage.probelauf:
        rollen = [r for _, r in ziele]
        return ZuschlagVorschau(
            anzahl=len(ziele),
            schueler=rollen.count("student"),
            lehrkraefte=rollen.count("teacher"),
            ohne_rolle=sum(1 for r in rollen if r not in ("student", "teacher")),
            betrag_eur=anfrage.betrag_eur,
            summe_eur=round(anfrage.betrag_eur * len(ziele), 2),
            einheiten_je_person=round(anfrage.betrag_eur * einheiten_je_euro()),
            gruppenname=gruppenname,
        )

    kurs = await get_current_rate(db)
    ergebnis = await buche_auf(
        db,
        pseudonyme=[p for p, _ in ziele],
        betrag_usd=round(anfrage.betrag_eur * kurs, 6),
        grund=anfrage.grund,
        erstellt_von=current_user.sub,
        schuljahr=load_school_year().schuljahr,
        quelle_gruppe_id=anfrage.gruppe_id,
    )
    logger.info(
        "Zuschlag: %d gebucht, %d fehlgeschlagen, %d unbegrenzt (gruppe=%s, betrag_eur=%.2f)",
        len(ergebnis.gebucht), len(ergebnis.fehlgeschlagen), len(ergebnis.unbegrenzt),
        anfrage.gruppe_id, anfrage.betrag_eur,
    )
    return ZuschlagErgebnis(
        gebucht=len(ergebnis.gebucht),
        fehlgeschlagen=ergebnis.fehlgeschlagen,
        unbegrenzt=ergebnis.unbegrenzt,
    )


class ZuschlagGruppe(BaseModel):
    id: int
    name: str
    typ: str
    schueler: int
    lehrkraefte: int


@router.get("/grants/gruppen", response_model=list[ZuschlagGruppe])
async def zuschlag_gruppen(
    db: AsyncSession = Depends(get_db),
    _: JwtPayload = Depends(require_any_role(["budget", "admin"])),
) -> list[ZuschlagGruppe]:
    """Die Gruppen, auf die sich aufbuchen lässt — **nur**, was die Auswahl braucht.

    ⚠️ Bewusst nicht die Admin-Gruppenliste (`/admin/groups`) für die Budget-Rolle
    geöffnet: Die führt mehr, als zum Aufbuchen nötig ist. Hier stehen Name, Art und die
    Zahl der Mitglieder je Rolle — keine Pseudonyme.
    """
    zahlen = (
        select(
            GroupMembership.group_id,
            func.count().filter(GroupMembership.role_in_group == "student").label("s"),
            func.count().filter(GroupMembership.role_in_group == "teacher").label("l"),
        )
        .group_by(GroupMembership.group_id)
        .subquery()
    )
    zeilen = (await db.execute(
        select(Group, zahlen.c.s, zahlen.c.l)
        .join(zahlen, zahlen.c.group_id == Group.id)
        .order_by(Group.type, Group.name)
    )).all()
    return [
        ZuschlagGruppe(id=g.id, name=g.anzeigename, typ=g.type,
                       schueler=s or 0, lehrkraefte=l or 0)
        for g, s, l in zeilen
    ]
