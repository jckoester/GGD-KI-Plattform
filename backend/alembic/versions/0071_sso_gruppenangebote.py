"""`sso_group_offers` — neue SSO-Unterrichtsgruppen werden angeboten, nicht angelegt

**Der Befund.** Bis hierher legte der Login-Sync für jede unbekannte `unterricht.*`-Gruppe
eine neue Unterrichtsgruppe an — es sei denn, eine Heuristik über `(Lehrkraft, Fach)` fand
eine vorhandene zum Adoptieren. Beides ging schief:

* Die Heuristik endete auf `scalar_one_or_none()`. Eine Lehrkraft mit *Chemie 9c* **und**
  *Chemie 9d* traf zwei Zeilen → `MultipleResultsFound` → der Login endete mit 500.
  Und `(Lehrkraft, Fach)` ist nicht bloß unscharf, sondern **falsch**: Zwei Gruppen im
  selben Fach sind der Normalfall — getrennter Unterricht, eigene Termine, eigene
  Ausfälle, je ein eigener Stundenplan-Eintrag.
* Wo die Heuristik nicht griff (Kursstufe ohne Quellklasse), entstand eine **Dublette**
  neben der bereits vorhandenen Gruppe.

**Die Entscheidung** (Jan, 23.09.2026): **Es wird nichts mehr geraten.** Findet der Sync zu
einer `unterricht.*`-Gruppe keine Gruppe mit dieser `sso_group_id`, legt er nichts an,
sondern hinterlegt ein **Angebot**. Die Lehrkraft entscheidet: zuordnen, neu anlegen oder
ignorieren.

*Warum das die richtige Richtung ist:* Aus den SSO-Daten lässt sich die Identität nicht
bestimmen — `ParsedGroup` trägt keine Klassennamen, nur einen Namen als Freitext, und
`„NwT 9a"` gegen `unterricht.9a.nwt` ist nur *meistens* dasselbe. Eine falsche
Verschmelzung schiebt zwei Jahrespläne ineinander und ist aus Nutzersicht nicht rückgängig
zu machen.

**Je Lehrkraft eine Zeile, nicht je SSO-Gruppe.** Sonst verstecken sich Angebote
gegenseitig: Ignoriert eine Kollegin, wäre die Frage für alle weg. Die Eindeutigkeit liegt
deshalb auf `(sso_group_id, pseudonym)`.

⚠️ **Die Spalte heißt `pseudonym`, und das ist kein Geschmack.**
`test_pseudonym_deletion_coverage` findet pseudonym-führende Tabellen an diesem
Namensmuster. Ein Angebot ohne Empfängerin ist nichts — es wird bei der Kontolöschung
**gelöscht**, nicht genullt.

**Nur Unterrichtsgruppen.** Klassen, Fachschaften, Lehrkräfte- und Arbeitsgruppen entstehen
weiterhin automatisch: Die Vererbung hängt an den Klassen, und eine Fachschaft ist keine
Entscheidung, die jemand treffen müsste.

Revision ID: 0071
Revises: 0070
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0071"
down_revision = "0070"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "sso_group_offers",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("sso_group_id", sa.Text(), nullable=False),
        sa.Column("pseudonym", sa.Text(), nullable=False),
        # Anzeigename, wie der Provider ihn liefert — die Lehrkraft erkennt die Gruppe
        # daran wieder, nicht an der rohen ID.
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "gesehen_am",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Gesetzt heißt: Die Lehrkraft hat abgelehnt. Die Zeile bleibt stehen, damit die
        # Frage beim nächsten Login nicht wiederkehrt — sonst wäre sie eine Dauerfrage.
        sa.Column("ignoriert_am", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("sso_group_id", "pseudonym", name="uq_sso_group_offers"),
    )
    # Gelesen wird fast immer „welche Angebote hat diese Person?"
    op.create_index("idx_sso_group_offers_pseudonym", "sso_group_offers", ["pseudonym"])


def downgrade() -> None:
    op.drop_index("idx_sso_group_offers_pseudonym", table_name="sso_group_offers")
    op.drop_table("sso_group_offers")
