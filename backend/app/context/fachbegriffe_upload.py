"""Aus hochgeladenen Dateien ein Bündel machen — mit Grenzen (Paket 10, AP3).

`app/context/fachbegriffe_import.py` nimmt ein Bündel `Pfad → Bytes` entgegen und kennt
kein Dateisystem. Das Admin-Skript baut es aus einem Ordner; **hier** entsteht es aus
dem, was durch ein Formular kommt: einzelne `.md`/`.svg` oder ein Zip.

⚠️ **Der Unterschied zum Ordner ist nicht die Herkunft, sondern das Vertrauen.** Ein
Ordner gehört dem Admin, der das Skript startet. Ein Upload gehört irgendeiner
Lehrkraft — und was sie schickt, kann groß sein, viel sein, aus dem Bündel
herauszeigen oder ein SVG mit Skript enthalten. Diese Schicht ist der Riegel dafür;
`importiere()` bleibt davon frei.

**Was durchkommt:** `.md` auf oberster Ebene und `.svg`. Alles andere wird
übergangen — aus einem Zip mit Meldung (ein Ordner enthält nun mal `.DS_Store` und
`.tex`-Quellen), bei einer einzeln gewählten Datei als Fehler: Wer sie ausdrücklich
auswählt, meint sie.

**Nachsicht beim Zuschnitt, Strenge beim Inhalt.** Ein im Finder gepackter Ordner
trägt seinen Namen als erste Ebene mit; diese Ebene wird abgeschnitten, sonst fände
der Import keine einzige Knotendatei. Umgekehrt wird kein Pfad „zurechtgebogen": Ein
Eintrag mit `..` oder absolutem Pfad ist kein Zuschnitt-Problem, sondern ein Versuch.
"""
from __future__ import annotations

import io
import posixpath
import zipfile
from dataclasses import dataclass
from typing import Sequence

from app.config import settings
from app.context.svg_pruefung import pruefe_svg

#: Der Unterordner, unter dem das Vault-Format seine Abbildungen führt.
ABB = "_Abb"


@dataclass(frozen=True)
class Grenzen:
    """Obergrenzen eines Uploads.

    ⚠️ **Ohne Vorgabewerte, mit Absicht.** Wie groß ein Bündel sein darf, ist eine
    Einstellung des Servers und keine Eigenschaft dieses Moduls — sie steht in
    `app/config.py` (aus `.env` überschreibbar) und im Gespann damit in
    `NGINX_MAX_BODY_SIZE`. Stünde hier eine Zahl, gäbe es zwei Wahrheiten, und die
    hier gewänne stillschweigend.

    Als Objekt, damit Tests kleine Grenzen einsetzen können, ohne die Umgebung
    anzufassen.
    """

    dateien: int
    gesamt_bytes: int
    einzeln_bytes: int


def aus_konfiguration() -> Grenzen:
    """Die geltenden Grenzen — bei jedem Lauf frisch aus den Einstellungen gelesen."""
    return Grenzen(
        dateien=settings.fachbegriffe_import_max_files,
        gesamt_bytes=settings.fachbegriffe_import_max_bytes,
        einzeln_bytes=settings.fachbegriffe_import_max_file_bytes,
    )


class BuendelFehler(Exception):
    """Der Upload ist als Ganzes nicht verwertbar. `status` wird zum HTTP-Status.

    Abgegrenzt von einer Warnung: Eine Warnung betrifft **eine** Datei und lässt den
    Rest laufen (das ist der Sinn des Berichts). Ein `BuendelFehler` heißt, dass
    weiterzumachen falsch wäre — zu groß, zu viel, kaputtes Zip, ein Pfad, der aus
    dem Bündel herauszeigt.
    """

    def __init__(self, status: int, text: str) -> None:
        super().__init__(text)
        self.status = status
        self.text = text


def _endung(pfad: str) -> str:
    return posixpath.splitext(pfad)[1].lower()


def _ist_gefaehrlicher_pfad(pfad: str) -> bool:
    """Zeigt der Eintrag aus dem Bündel heraus?

    Geprüft wird auf dem **rohen** Namen, vor jeder Normalisierung: `..` und absolute
    Pfade sind hier kein Sonderfall, den man zurechtrücken könnte, sondern der Grund
    zum Abbrechen. Rückwärtsschrägstriche zählen mit — die Zip-Spezifikation verlangt
    `/`, wer `\\` schickt, will an einem Prüfer vorbei.
    """
    if pfad.startswith("/") or pfad.startswith("\\") or "\\" in pfad:
        return True
    if ":" in pfad.split("/", 1)[0]:          # `C:\…`, `\\server\…`
        return True
    return any(teil == ".." for teil in pfad.split("/"))


def _ohne_wurzelverzeichnis(namen: Sequence[str]) -> dict[str, str]:
    """Roher Zip-Name → Pfad im Bündel; eine gemeinsame erste Ebene fällt weg.

    Im Finder oder Explorer packt man einen **Ordner**, nicht seinen Inhalt — im Zip
    steht dann `Fachbegriffe Ch Pilot/Oxidation.md`. Ohne diesen Schritt läge keine
    einzige Knotendatei auf oberster Ebene und der Import meldete ein leeres Bündel.
    Abgeschnitten wird nur, was **alle** Einträge teilen, und nur, wenn oben noch keine
    Knotendatei liegt. ⚠️ `_Abb` ist dabei ausgenommen: Ein Archiv, das nur Abbildungen
    enthält, hätte sonst seine eigene Ordnerebene verloren.
    """
    if any("/" not in n and _endung(n) == ".md" for n in namen):
        return {n: n for n in namen}
    # `None` steht für „liegt schon oben" — taucht es auf, teilen nicht alle Einträge
    # dieselbe erste Ebene, und es gibt nichts abzuschneiden.
    wurzeln = {n.split("/", 1)[0] if "/" in n else None for n in namen}
    if len(wurzeln) != 1:
        return {n: n for n in namen}
    wurzel = next(iter(wurzeln))
    if wurzel is None or wurzel == ABB:
        return {n: n for n in namen}
    return {n: n[len(wurzel) + 1:] for n in namen}


def _pruefe_svg_oder_warne(pfad: str, inhalt: bytes, warnungen: list[str]) -> bool:
    try:
        text = inhalt.decode("utf-8")
    except UnicodeDecodeError:
        warnungen.append(f"{pfad}: Abbildung abgelehnt — keine UTF-8-Kodierung")
        return False
    if grund := pruefe_svg(text):
        warnungen.append(f"{pfad}: Abbildung abgelehnt — {grund}")
        return False
    return True


#: Bit 11 der Allzweck-Flags: Der Name im Archiv ist UTF-8 (APPNOTE 4.4.4).
_UTF8_KENNZEICHEN = 0x800


def eintragsname(eintrag: zipfile.ZipInfo) -> str:
    """Der Name eines Zip-Eintrags, wie er gemeint war.

    ⚠️ **Ohne UTF-8-Kennzeichen liest `zipfile` den Namen als CP437** — die Kodierung
    von MS-DOS, die die Zip-Spezifikation als Vorgabe nennt. Viele Packer (auch der von
    macOS) schreiben aber UTF-8, **ohne** das Kennzeichen zu setzen. Aus einem zerlegten
    „ü" (`u` + U+0308) wurde so `u╠ê`, aus `Hückel-Regel` die Kennung `ch-hu-ckel-regel`
    — und der nächste Import mit richtig gelesenen Namen legte einen zweiten Knoten an
    (gefunden 06.10.2026: 15 Knoten auf Dev, 17 auf Prod).

    Deshalb: Lässt sich der Name als UTF-8 lesen, ist er das; sonst bleibt es bei CP437.
    Ein echter CP437-Name mit Umlaut (`Ü` = 0x9A) ist kein gültiges UTF-8 und fällt
    durch. Zerlegte Umlaute bringt danach `lies_buendel` auf NFC.
    """
    if eintrag.flag_bits & _UTF8_KENNZEICHEN:
        return eintrag.filename
    try:
        return eintrag.filename.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return eintrag.filename


def _aus_zip(
    dateiname: str, roh: bytes, grenzen: Grenzen, warnungen: list[str]
) -> dict[str, bytes]:
    try:
        archiv = zipfile.ZipFile(io.BytesIO(roh))
    except zipfile.BadZipFile:
        raise BuendelFehler(400, f"{dateiname}: kein lesbares Zip-Archiv.")

    eintraege = [
        z for z in archiv.infolist()
        if not z.is_dir() and not eintragsname(z).startswith("__MACOSX/")
    ]
    for z in eintraege:
        if _ist_gefaehrlicher_pfad(eintragsname(z)):
            raise BuendelFehler(
                400,
                f"{dateiname}: Der Eintrag „{eintragsname(z)}“ zeigt aus dem Archiv heraus.",
            )
    if len(eintraege) > grenzen.dateien:
        raise BuendelFehler(
            413,
            f"{dateiname}: {len(eintraege)} Einträge — höchstens {grenzen.dateien}.",
        )
    # ⚠️ **Die Kopfangabe, bevor ein Byte entpackt wird.** `file_size` steht im
    # Verzeichnis des Archivs und kostet nichts — damit fliegt eine Zip-Bombe raus,
    # ohne sie anzufassen. Eine **kleiner** gelogene Angabe fängt `zipfile` selbst ab
    # (es liest bis `file_size` und prüft dann die CRC-Summe); der Deckel beim Lesen
    # unten ist der Gurt dazu, falls es das einmal nicht tut.
    entpackt = sum(z.file_size for z in eintraege)
    if entpackt > grenzen.gesamt_bytes:
        raise BuendelFehler(
            413,
            f"{dateiname}: entpackt {entpackt // (1024 * 1024)} MB — höchstens "
            f"{grenzen.gesamt_bytes // (1024 * 1024)} MB.",
        )

    pfade = _ohne_wurzelverzeichnis([eintragsname(z) for z in eintraege])
    buendel: dict[str, bytes] = {}
    for z in eintraege:
        pfad = pfade[eintragsname(z)]
        endung = _endung(pfad)
        if endung not in (".md", ".svg"):
            warnungen.append(f"{pfad}: übergangen — nur .md und .svg werden gelesen")
            continue
        if endung == ".md" and "/" in pfad:
            warnungen.append(
                f"{pfad}: übergangen — Knotendateien müssen oben im Bündel liegen"
            )
            continue
        try:
            with archiv.open(z) as f:
                inhalt = f.read(grenzen.einzeln_bytes + 1)
        except (RuntimeError, zipfile.BadZipFile) as fehler:
            raise BuendelFehler(400, f"{dateiname}: {pfad} nicht lesbar ({fehler}).")
        if len(inhalt) > grenzen.einzeln_bytes:
            raise BuendelFehler(
                413,
                f"{pfad}: größer als {grenzen.einzeln_bytes // (1024 * 1024)} MB.",
            )
        if endung == ".svg" and not _pruefe_svg_oder_warne(pfad, inhalt, warnungen):
            continue
        buendel[pfad] = inhalt
    return buendel


def baue_buendel(
    hochgeladen: Sequence[tuple[str, bytes]], *, grenzen: Grenzen | None = None
) -> tuple[dict[str, bytes], list[str]]:
    """Hochgeladene Dateien → (Bündel, Warnungen für den Bericht).

    ``hochgeladen`` ist eine Folge von (Dateiname, Inhalt). Eine `.zip` wird entpackt,
    `.md` und `.svg` wandern direkt hinein — eine einzeln hochgeladene Abbildung unter
    ``_Abb/``, weil das Frontmatter sie dort erwartet. (Findet der Import sie unter dem
    Pfad nicht, sucht er zusätzlich nach dem bloßen Dateinamen.)
    """
    grenzen = grenzen or aus_konfiguration()
    warnungen: list[str] = []
    buendel: dict[str, bytes] = {}

    for name, inhalt in hochgeladen:
        name = posixpath.basename(name.replace("\\", "/")).strip()
        if not name:
            raise BuendelFehler(400, "Eine hochgeladene Datei hat keinen Namen.")
        endung = _endung(name)
        # ⚠️ Für ein Archiv gilt die **Gesamtgrenze**, nicht die Einzelgrenze: Ein Zip
        # ist die Sammlung, keine einzelne Datei. Mit der Einzelgrenze gemessen wäre
        # eine vollständige Fachschaftssammlung abgelehnt worden, obwohl jede Datei
        # darin winzig ist.
        deckel = grenzen.gesamt_bytes if endung == ".zip" else grenzen.einzeln_bytes
        if len(inhalt) > deckel:
            raise BuendelFehler(
                413, f"{name}: größer als {deckel // (1024 * 1024)} MB."
            )
        if endung == ".zip":
            buendel |= _aus_zip(name, inhalt, grenzen, warnungen)
        elif endung == ".md":
            buendel[name] = inhalt
        elif endung == ".svg":
            if _pruefe_svg_oder_warne(name, inhalt, warnungen):
                buendel[f"{ABB}/{name}"] = inhalt
        else:
            # Anders als im Zip ein Fehler: Wer eine Datei einzeln auswählt, meint sie.
            raise BuendelFehler(
                415, f"{name}: nur .md, .svg und .zip werden angenommen."
            )

    if len(buendel) > grenzen.dateien:
        raise BuendelFehler(
            413, f"{len(buendel)} Dateien — höchstens {grenzen.dateien}."
        )
    gesamt = sum(len(i) for i in buendel.values())
    if gesamt > grenzen.gesamt_bytes:
        raise BuendelFehler(
            413,
            f"Zusammen {gesamt // (1024 * 1024)} MB — höchstens "
            f"{grenzen.gesamt_bytes // (1024 * 1024)} MB.",
        )
    if not buendel:
        # ⚠️ **Mit Begründung.** Alles, was hier übergangen wurde, steht in `warnungen`
        # — und die gehen mit dem Bündel verloren, wenn es keins gibt. „Keine
        # verwertbare Datei" allein ließe jemanden ratlos vor einem Archiv stehen, in
        # dem seine Dateien sichtbar drin sind (etwa alle eine Ebene zu tief).
        raise BuendelFehler(
            422,
            "Keine verwertbare Datei dabei."
            + ("  " + " · ".join(warnungen[:5]) if warnungen else ""),
        )
    return buendel, warnungen
