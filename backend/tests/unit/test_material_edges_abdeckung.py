"""Wächter: Jede Stelle, die `metadata["phasen"]` schreibt, zieht die Kanten nach.

**Warum es diesen Test gibt.** Die Ableitung der Materialkanten ist eine Regel mit
mehreren Aufrufern — genau die Bauart, an der in AP4 die `valid_until`-Vorbelegung
gescheitert ist: Sie war gebaut, hatte aber an fünf Anlegestellen keinen Eingang,
und **null von 19 134 Knoten** trugen ein Ablaufdatum. Aufgefallen ist das erst
Wochen später bei einer Messung.

Hier kann dasselbe passieren: Wer künftig eine Stelle ergänzt, die Phasen schreibt,
und `synchronisiere_materialkanten` vergisst, hinterlässt Kanten, die einen
Materialeinsatz behaupten, den es nicht mehr gibt — oder einen verschweigen, den es
gibt. Nichts schlägt fehl, nichts meldet sich; „Eingesetzt in" (AP7) zeigt schlicht
Falsches.

Der Test ist grob: Er prüft je **Datei**, nicht je Funktion. Das ist Absicht — eine
genauere Prüfung müsste den Kontrollfluss verstehen und wäre selbst eine
Fehlerquelle. Wer eine Datei ausnimmt, trägt sie unten mit Begründung ein.
"""
import re
from pathlib import Path

PLANNING = Path(__file__).resolve().parents[2] / "app" / "planning"

#: Schreibt Phasen, braucht aber keinen Abgleich — mit Begründung.
_AUSGENOMMEN = {
    # Setzt ausschließlich `phase["status"]` je Phase (Nachbereitung). Das Material
    # der Phasen bleibt unangetastet, ein Abgleich wäre immer ein No-op.
    "review_service.py": "ändert nur den Phasen-Status, nie das Material",
    # Enthält die Ableitung selbst — die Treffer stehen dort in den erzeugten
    # Kanten-Metadaten (`{"via": …, "phasen": …}`), nicht in einer Stunde.
    "material_edges.py": "ist die Ableitung selbst und schreibt keine Stundenphasen",
}

#: Zuweisungen an die Phasenliste — `meta["phasen"] = …`, `metadata_={"phasen": …}`.
_SCHREIBT_PHASEN = re.compile(r"""\[["']phasen["']\]\s*=|["']phasen["']\s*:""")


def _dateien_die_phasen_schreiben() -> dict[str, list[int]]:
    treffer: dict[str, list[int]] = {}
    for pfad in sorted(PLANNING.glob("*.py")):
        zeilen = pfad.read_text(encoding="utf-8").splitlines()
        nummern = [
            i for i, z in enumerate(zeilen, 1)
            if _SCHREIBT_PHASEN.search(z) and not z.lstrip().startswith("#")
        ]
        if nummern:
            treffer[pfad.name] = nummern
    return treffer


def test_jede_schreibstelle_zieht_die_kanten_nach():
    fehlend = []
    for name, zeilen in _dateien_die_phasen_schreiben().items():
        if name in _AUSGENOMMEN:
            continue
        quelle = (PLANNING / name).read_text(encoding="utf-8")
        if "synchronisiere_materialkanten" not in quelle:
            fehlend.append(f"{name} (Zeilen {zeilen})")

    assert not fehlend, (
        "Diese Dateien schreiben metadata['phasen'], rufen aber "
        "synchronisiere_materialkanten nicht auf:\n  "
        + "\n  ".join(fehlend)
        + "\n\nEntweder den Aufruf ergänzen (vor dem commit) oder die Datei in "
        "_AUSGENOMMEN eintragen — mit Begründung, warum das Material dort nicht "
        "berührt wird."
    )


#: Schreibstellen, die Phasen **neu hereinnehmen** und deshalb Kennungen vergeben
#: müssen. `operations.py` und `snapshots.py` fehlen bewusst: Sie schieben
#: vorhandene Phasen um bzw. spielen einen früheren Stand zurück — beide arbeiten
#: mit Phasen, die ihre Kennung schon haben, und eine neue zu vergeben zerschnitte
#: genau die Verweise, um die es geht.
_NIMMT_PHASEN_HEREIN = {"router.py", "assistant_tools.py"}


def test_eingangsstellen_vergeben_kennungen():
    """Wer Phasen von außen entgegennimmt, sorgt für stabile `id`s.

    Ohne sie laufen `phasen_status`, die Phasen-Übertragung und die Phasenangabe
    an den Materialkanten still ins Leere — nichts schlägt fehl, es wird nur
    ungenau. Der Planungsassistent hatte genau diese Lücke: Er schreibt Roh-Dicts
    aus den Werkzeug-Argumenten und geht nicht durch `LessonPhaseItem`.
    """
    fehlend = [
        name
        for name in sorted(_NIMMT_PHASEN_HEREIN)
        if "sichere_phasen_kennungen" not in (PLANNING / name).read_text(encoding="utf-8")
    ]
    assert not fehlend, (
        "Diese Eingangsstellen vergeben keine Phasen-Kennungen: "
        + ", ".join(fehlend)
    )


def test_der_waechter_findet_die_bekannten_schreibstellen():
    """Gegenprobe: Ein Muster, das nichts mehr findet, wäre ein stiller Totalausfall.

    Ohne diese Zusicherung würde eine kaputte Regex den Test oben dauerhaft grün
    machen — die unangenehmste Sorte Fehlalarm, weil sie wie Sicherheit aussieht.
    """
    gefunden = _dateien_die_phasen_schreiben()
    for erwartet in ("router.py", "operations.py", "assistant_tools.py", "snapshots.py"):
        assert erwartet in gefunden, f"{erwartet} nicht erkannt — Muster prüfen"


def test_ausnahmen_sind_begruendet():
    for name, grund in _AUSGENOMMEN.items():
        assert (PLANNING / name).exists(), f"{name} gibt es nicht mehr — Eintrag entfernen"
        assert len(grund) > 20, f"{name}: Begründung zu dünn"
