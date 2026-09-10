"""Mailversand — schmal, abschaltbar, einspeisbar.

Die Plattform verschickt sehr wenig Post: Benachrichtigungen zu Krisenfällen und
deren Erinnerungen, ein paar Nachrichten am Tag im schlimmsten Fall. Dafür gibt es
`smtplib` aus der Standardbibliothek.

**Warum nicht `aiosmtplib`.** Jede Abhängigkeit trägt hier eine Obergrenze und einen
neu zu erzeugenden Lockfile mit Hashes (Sicherheits-Audit #17). Der eine Vorteil —
nicht zu blockieren — zählt an dieser Stelle nicht: Versendet wird ohnehin aus einer
Hintergrundaufgabe, und `asyncio.to_thread` hält den Ereignisschleifen-Thread frei.

**Standardmäßig aus.** Ohne `SMTP_HOST` wird nichts versendet, sondern geloggt. Eine
Entwicklungsumgebung braucht damit keine Konfiguration, und ein im Produktivsystem
vergessener Wert fällt im Log auf, statt eine Krise unbemerkt verschwinden zu lassen.
"""
from app.mail.sender import (
    MailNichtKonfiguriert,
    Versandergebnis,
    ist_konfiguriert,
    pruefe_beim_start,
    sende,
)

__all__ = [
    "MailNichtKonfiguriert",
    "Versandergebnis",
    "ist_konfiguriert",
    "pruefe_beim_start",
    "sende",
]
