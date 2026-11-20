"""Persist finding review state and reviewer information."""

import sqlalchemy as sa
from alembic import op

revision = "0006_finding_review"
down_revision = "0005_scan_queue"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "findings",
        sa.Column(
            "review_status",
            sa.String(16),
            server_default="needs_review",
            nullable=False,
        ),
    )
    op.add_column("findings", sa.Column("reviewed_by", sa.Uuid()))
    op.add_column("findings", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.create_foreign_key(
        "fk_findings_reviewed_by", "findings", "users", ["reviewed_by"], ["id"]
    )
    op.create_check_constraint(
        "ck_findings_review_status",
        "findings",
        "review_status IN ('needs_review', 'confirmed', 'false_positive', 'follow_up')",
    )
    op.create_index("ix_findings_review_status", "findings", ["review_status"])
    op.create_index(
        "ix_audit_events_entity_type_entity_id",
        "audit_events",
        ["entity_type", "entity_id"],
    )


def downgrade():
    op.drop_index("ix_audit_events_entity_type_entity_id", table_name="audit_events")
    op.drop_index("ix_findings_review_status", table_name="findings")
    op.drop_constraint("ck_findings_review_status", "findings", type_="check")
    op.drop_constraint("fk_findings_reviewed_by", "findings", type_="foreignkey")
    for column in ("reviewed_at", "reviewed_by", "review_status"):
        op.drop_column("findings", column)
