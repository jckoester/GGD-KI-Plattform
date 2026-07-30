"""Gemeinsame Render-Fehlerklasse (Phase 17).

Von allen Renderern genutzt (Sidecar-CircuiTikZ, in-process Plot). Der Render-Service
fängt sie und liefert einen Fehler-Platzhalter-SVG statt einer gesprengten Antwort.
"""


class RenderError(Exception):
    """Rendern fehlgeschlagen (Fehler, Timeout oder ungültige Eingabe)."""
