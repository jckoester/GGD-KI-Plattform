"""Gewöhnliche Chats wieder ohne Vorschau-Kontext (0.29.1)

Revision ID: 0100
Revises: 0099
Create Date: 2026-11-03

In 0.29.0 schrieb der Chat für einen gewöhnlichen Chat den JSON-Wert `null` in
`conversations.preview_context` statt SQL-`NULL`. Die Listen („Letzte Chats“, Verlauf, Fächer)
und der Löschlauf fragen `IS NULL`; für sie war jeder neue Chat ein Vorschau-Chat — er fehlte in
den Listen und wäre nach 30 statt 93 Tagen gelöscht worden. Diese Migration setzt den JSON-Wert
auf `NULL` zurück; das Modell schreibt seither `NULL` (`JSONB(none_as_null=True)`).

**Rücknahme:** `downgrade` ändert nichts — welcher Chat vorher JSON-`null` trug, ist nicht
festgehalten, und es zurückzuschreiben wäre der Fehler selbst.
"""
from alembic import op

revision = "0100"
down_revision = "0099"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE conversations SET preview_context = NULL "
               "WHERE jsonb_typeof(preview_context) = 'null'")


def downgrade() -> None:
    pass
