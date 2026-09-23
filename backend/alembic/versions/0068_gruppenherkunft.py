"""Herkunft von Mitgliedschaften und mehrere Quellklassen je Unterrichtsgruppe

**Zwei Änderungen, ein Grund: Der Beitrittscode (AP4) braucht beide.**

*1. `group_source_classes` statt `groups.source_class_group_id`.* Eine Unterrichtsgruppe
konnte bisher aus **genau einer** Klasse stammen. Eine NwT-Gruppe aus 10a/10b/10c kann
ihre Herkunft damit nicht abbilden — sie erbte bestenfalls eine der drei Klassen. Die
Spalte wird durch eine 1:n-Tabelle ersetzt, nicht ergänzt: Zwei Quellen für dieselbe
Aussage laufen erfahrungsgemäß auseinander, sobald sich die Quellklassen ändern.

*2. `group_memberships.herkunft`.* Bisher war die Herkunft einer Mitgliedschaft aus
Rolle und Gruppeneigenschaften **erraten**: Der Vererbungslauf entfernte beim Abgang
`role_in_group = 'student'` in abgeleiteten Gruppen, weil das dort gleichbedeutend mit
„geerbt" war. Mit dem Beitrittscode hört das auf — dann gibt es Schüler-Mitgliedschaften,
die **nicht** geerbt sind und beim nächsten Login trotzdem bleiben müssen. Ohne diese
Spalte räumte der Vererbungslauf genau die Beitritte weg, für die es den Code gibt.

**Fünf Herkünfte, und wer sie aufräumen darf:**

| Wert | Wie sie entsteht | Wer entfernt sie automatisch |
|---|---|---|
| `sso` | Der Provider nennt die Person in der Gruppe | Immediate Mirror |
| `geerbt` | Schüler:in einer Quellklasse | Vererbungslauf beim Login |
| `code` | Selbstbeitritt per Beitrittscode (ab `0069`) | niemand |
| `eigen` | Die Lehrkraft, die die Gruppe angelegt hat | niemand |
| `manuell` | Admin über `POST /groups/{id}/members` | niemand |

Die Regel dahinter: **Ein Aufräumlauf darf nur entfernen, was er selbst hätte anlegen
können.** Alles andere ist die Entscheidung eines Menschen und fällt nicht von allein.

⚠️ **`manuell` ist beim Umsetzen dazugekommen.** ADR-003 nennt vier Herkünfte; der
Endpunkt `POST /groups/{id}/members` (admin-only, von keiner Oberfläche benutzt, verlangt
ein Pseudonym) legt aber eine fünfte Art an. Sie mit `code` zu verschmelzen wäre schädlich:
Die Rücknahme einer Code-Runde in `0069` löscht gezielt `herkunft='code'` und träfe sonst
von Hand eingetragene Mitglieder mit.

**Zum Backfill.** Die Reihenfolge ist bewusst von speziell nach allgemein; jede Zeile
bekommt genau einmal einen Wert. Was in einer Gruppe **ohne** SSO-Entsprechung sitzt und
weder Lehrkraft noch geerbt ist, war Handarbeit — deshalb `manuell` als Auffangwert und
nicht `sso`. Ein falsches `sso` wäre hier folgenlos (der Spiegel fasst nur Gruppen mit
`sso_group_id` an), aber es stünde eine Unwahrheit in der Tabelle.

Revision ID: 0068
Revises: 0067
"""
import sqlalchemy as sa
from alembic import op

revision = "0068"
down_revision = "0067"
branch_labels = None
depends_on = None

HERKUENFTE = ("sso", "geerbt", "code", "eigen", "manuell")


def upgrade() -> None:
    # ── 1. Quellklassen: 1:n statt 1:1 ───────────────────────────────────────
    op.create_table(
        "group_source_classes",
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "class_group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    # Gelesen wird fast immer „welche Gruppen speisen sich aus dieser Klasse?" —
    # der Vererbungslauf kommt von der Klasse her, nicht von der Gruppe.
    op.create_index(
        "idx_group_source_classes_class", "group_source_classes", ["class_group_id"]
    )

    op.execute(
        """
        INSERT INTO group_source_classes (group_id, class_group_id)
        SELECT id, source_class_group_id
          FROM groups
         WHERE source_class_group_id IS NOT NULL
        """
    )

    # ── 2. Herkunft der Mitgliedschaften ─────────────────────────────────────
    # Erst nullable anlegen, dann füllen, dann festziehen — eine NOT-NULL-Spalte
    # ohne Vorgabewert ließe sich auf einer befüllten Tabelle nicht hinzufügen.
    op.add_column("group_memberships", sa.Column("herkunft", sa.Text(), nullable=True))

    # a) Alles in einer Gruppe mit SSO-Entsprechung stammt aus dem Token.
    op.execute(
        """
        UPDATE group_memberships m SET herkunft = 'sso'
          FROM groups g
         WHERE g.id = m.group_id AND g.sso_group_id IS NOT NULL
        """
    )
    # b) Lehrkraft in einer Gruppe ohne SSO-Entsprechung: ihre eigene Anlage.
    op.execute(
        """
        UPDATE group_memberships m SET herkunft = 'eigen'
          FROM groups g
         WHERE g.id = m.group_id
           AND g.sso_group_id IS NULL
           AND m.herkunft IS NULL
           AND m.role_in_group = 'teacher'
        """
    )
    # c) Schüler:in in einer abgeleiteten Unterrichtsgruppe: geerbt.
    op.execute(
        """
        UPDATE group_memberships m SET herkunft = 'geerbt'
          FROM groups g
         WHERE g.id = m.group_id
           AND g.sso_group_id IS NULL
           AND g.type = 'teaching_group'
           AND m.herkunft IS NULL
           AND m.role_in_group = 'student'
           AND EXISTS (
                 SELECT 1 FROM group_source_classes q WHERE q.group_id = g.id
               )
        """
    )
    # d) Auffangwert: von Hand eingetragen.
    op.execute("UPDATE group_memberships SET herkunft = 'manuell' WHERE herkunft IS NULL")

    op.alter_column("group_memberships", "herkunft", nullable=False)
    op.create_check_constraint(
        "check_group_memberships_herkunft",
        "group_memberships",
        "herkunft IN ('sso','geerbt','code','eigen','manuell')",
    )

    # ── 3. Die alte Spalte fällt ─────────────────────────────────────────────
    op.drop_index("idx_groups_source_class_group_id", table_name="groups")
    op.drop_column("groups", "source_class_group_id")


def downgrade() -> None:
    op.add_column(
        "groups",
        sa.Column(
            "source_class_group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index(
        "idx_groups_source_class_group_id", "groups", ["source_class_group_id"]
    )
    # ⚠️ **Verlustbehaftet.** Eine Gruppe mit mehreren Quellklassen behält beim
    # Zurückrollen nur die kleinste — mehr trägt die Spalte nicht. Das ist der Preis
    # dafür, dass die Migration die alte Spalte fallen lässt statt sie mitzuführen.
    op.execute(
        """
        UPDATE groups g SET source_class_group_id = (
            SELECT MIN(q.class_group_id)
              FROM group_source_classes q
             WHERE q.group_id = g.id
        )
        """
    )
    op.drop_index("idx_group_source_classes_class", table_name="group_source_classes")
    op.drop_table("group_source_classes")

    op.drop_constraint(
        "check_group_memberships_herkunft", "group_memberships", type_="check"
    )
    op.drop_column("group_memberships", "herkunft")
