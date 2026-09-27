"""`group_join_codes` — Selbstbeitritt zu einer Unterrichtsgruppe

**Wofür.** Wo die Vererbung nicht trägt — Kursstufe ohne Klassenanker, Teilgruppen aus
mehreren Klassen, Nachzügler in Klassenkursen —, gibt es sonst **keinen** Weg, wie
Schüler:innen in eine Gruppe kommen. Manuelle Mitgliederpflege scheidet aus: Die
Plattform zeigt keine Klarnamen, eine Mitgliederliste aus Pseudonymen wäre nicht
bedienbar (ADR-003 Teil 1 und Teil 3).

**Der Code gehört der Gruppe, nicht einer Person.** Er enthält kein Personenmerkmal und
erlaubt keinen Rückschluss auf die Person, die ihn einlöst. Entsprechend wird er auch
nicht personenbezogen gelöscht: Er verfällt über `gueltig_bis` und stirbt mit der Gruppe.
Nur `erstellt_von` ist ein Pseudonym und fällt unter die 90-Tage-Frist — dann wird die
Spalte genullt, der Code selbst bleibt.

**Zwei Spalten an `group_memberships`, und warum sie nötig sind.** Die Tabelle trug bisher
nur `(group_id, pseudonym, role_in_group, herkunft)` — **keinen Zeitstempel**. Ohne den
ist die Rücknahme von Fehlbeitritten nicht baubar (Entscheidung Jan, F1): „alle Beitritte
zu diesem Code" braucht `join_code_id`, „die Beitritte vom 24.09." braucht
`beigetreten_am`. Beide bleiben `NULL` für alles, was nicht per Code entstanden ist.

⚠️ **Warum die Rücknahme mengenweise arbeitet und nicht je Person.** Ohne Namen ist eine
Einzelauswahl nicht sicher bedienbar: Wer die falsche Zeile trifft, entfernt eine
berechtigte Person und merkt es nicht. Die Lehrkraft wählt deshalb eine **Code-Runde**
oder einen **Tag** daraus — bei drei Tagen Gültigkeit deckt eine Runde faktisch eine
Unterrichtsstunde ab.

**Der Code ist kurz und vorlesbar.** Das Alphabet lässt `O/0/I/1/L` weg: Ein an die Tafel
geschriebener Code muss ankommen, und `I` gegen `1` zu verwechseln ist kein Randfall.
Gegen Raten schützt nicht die Länge allein, sondern die kurze Lebensdauer (3 Tage) und
die Drossel auf dem Einlöse-Pfad.

Revision ID: 0070
Revises: 0069
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0070"
down_revision = "0069"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_join_codes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("code", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "erstellt_am",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        # Pseudonym der ausgebenden Lehrkraft. Nullable, weil es unter die
        # 90-Tage-Löschung fällt — der Code gehört der Gruppe und bleibt.
        #
        # ⚠️ **Der Name endet auf `_pseudonym`, und das ist kein Geschmack.**
        # `test_pseudonym_deletion_coverage` findet pseudonym-führende Tabellen an
        # genau diesem Namensmuster. Hieße die Spalte `erstellt_von`, fiele die
        # Tabelle durch den Wächter — und niemand bemerkte, dass die Kontolöschung
        # sie nicht anfasst.
        sa.Column("erstellt_von_pseudonym", sa.Text(), nullable=True),
        sa.Column("gueltig_bis", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("widerrufen_am", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Der Einlöse-Pfad sucht über den Code; die Gruppenansicht über die Gruppe.
    op.create_index("idx_group_join_codes_group", "group_join_codes", ["group_id"])

    op.add_column(
        "group_memberships",
        sa.Column("beigetreten_am", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        "group_memberships",
        sa.Column(
            "join_code_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("group_join_codes.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    # Die Rücknahme fragt „welche Mitgliedschaften stammen aus diesem Code?"
    op.create_index(
        "idx_group_memberships_join_code", "group_memberships", ["join_code_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_group_memberships_join_code", table_name="group_memberships")
    op.drop_column("group_memberships", "join_code_id")
    op.drop_column("group_memberships", "beigetreten_am")
    op.drop_index("idx_group_join_codes_group", table_name="group_join_codes")
    op.drop_table("group_join_codes")
