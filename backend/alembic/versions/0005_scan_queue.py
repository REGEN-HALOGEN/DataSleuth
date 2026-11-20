"""Persist scan leases, cancellations, and retry state."""

import sqlalchemy as sa
from alembic import op

revision = "0005_scan_queue"
down_revision = "0004_scan_findings"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "scan_jobs",
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column("scan_jobs", sa.Column("lease_token", sa.Uuid()))
    op.add_column("scan_jobs", sa.Column("lease_until", sa.DateTime(timezone=True)))
    op.add_column(
        "scan_jobs",
        sa.Column(
            "cancel_requested", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column(
        "scan_jobs",
        sa.Column(
            "inventory_ready", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
    )
    op.add_column("scan_jobs", sa.Column("fingerprint_key_version", sa.Integer()))
    op.create_index("ix_scan_jobs_status", "scan_jobs", ["status"])


def downgrade():
    op.drop_index("ix_scan_jobs_status", table_name="scan_jobs")
    for column in (
        "fingerprint_key_version",
        "inventory_ready",
        "cancel_requested",
        "lease_until",
        "lease_token",
        "attempts",
    ):
        op.drop_column("scan_jobs", column)
