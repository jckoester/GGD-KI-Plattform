"""Typgebundene Prüfung einzelner `metadata`-Felder beim Anlegen und Ändern von Knoten.

**Was hier steht und was nicht.** `metadata` ist bewusst ein freies JSON-Feld — der
Kontextspeicher soll neue Felder aufnehmen können, ohne dass jedes eine Migration
braucht. Geprüft wird deshalb nur, was eine **Bedeutung für die Anwendung** trägt und
falsch nicht auffiele:

- `begriff.ab_klasse` — die Klassenstufe, ab der eine Definition gemeint ist. Steht dort
  ein String oder eine 99, sortiert und filtert die Sammlung (AP5) still falsch.
- `strukturierung.form` — `gliederung` oder `mindmap`. Der Wert entscheidet, als was der
  Knoten dargestellt wird; ein Tippfehler macht ihn zu keinem von beidem.

Alles Übrige bleibt ungeprüft. Das ist Absicht: Eine Prüfung, die jedes Feld kennt,
müsste bei jedem neuen Feld nachgezogen werden, und niemand würde daran denken.

⚠️ **Das hier ist die schlanke Fassung.** Ein generisches Schema je Typ ist offen und
gehört zu AP5, wo der Sammlungs-Editor sein Formular ohnehin aus einer Feldbeschreibung
baut — zwei Schema-Orte nebeneinander wären der schlechtere Zustand. Zu dem Zeitpunkt ist
auch zu entscheiden, ob `validate_unterrichtsstunde_metadata` (der einzige weitere
Validator, aufgerufen nur vom Planner-Router) darin aufgeht.
"""
from __future__ import annotations

# Untergrenze 1, Obergrenze 13: Grundschule bis Kursstufe. Bewusst weit — welche Stufen
# eine Schule führt, steht in `subjects.yaml`/`school_year.yaml` und ist nicht Sache
# eines Fachbegriffs.
_MIN_KLASSE = 1
_MAX_KLASSE = 13

_STRUKTURIERUNG_FORMEN = ("gliederung", "mindmap")


def validate_node_metadata(content_type: str | None, metadata: dict | None) -> None:
    """Wirft ``ValueError`` bei einem unbrauchbaren Wert. Fehlende Felder sind erlaubt.

    ``metadata`` darf ``None`` sein; geprüft wird nur, was tatsächlich dasteht.
    """
    if not metadata or content_type is None:
        return

    if content_type == "begriff" and "ab_klasse" in metadata:
        wert = metadata["ab_klasse"]
        if wert is not None:
            # `bool` ist in Python ein `int` — `True` würde sonst als Klasse 1 durchgehen.
            if isinstance(wert, bool) or not isinstance(wert, int):
                raise ValueError(
                    f"metadata.ab_klasse muss eine ganze Zahl sein (war: {wert!r})"
                )
            if not _MIN_KLASSE <= wert <= _MAX_KLASSE:
                raise ValueError(
                    f"metadata.ab_klasse muss zwischen {_MIN_KLASSE} und {_MAX_KLASSE} "
                    f"liegen (war: {wert})"
                )

    if content_type == "strukturierung" and "form" in metadata:
        wert = metadata["form"]
        if wert not in _STRUKTURIERUNG_FORMEN:
            raise ValueError(
                f"metadata.form muss {' oder '.join(_STRUKTURIERUNG_FORMEN)} sein "
                f"(war: {wert!r})"
            )
