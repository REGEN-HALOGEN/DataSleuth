"""Backfill single-installation ownership in one PostgreSQL transaction."""

import sqlalchemy as sa
from alembic import op

revision = "0007_organisation_ownership"
down_revision = "0006_finding_review"
branch_labels = None
depends_on = None
LOCAL = "00000000-0000-4000-8000-000000000001"
OWNED = (
    "scan_sources",
    "scan_jobs",
    "scanned_files",
    "data_fingerprints",
    "findings",
    "audit_events",
)


def upgrade():
    op.create_table(
        "organisations",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
    )
    op.execute(f"INSERT INTO organisations VALUES ('{LOCAL}', 'Local organisation')")
    op.create_table(
        "organisation_memberships",
        sa.Column(
            "organisation_id",
            sa.Uuid,
            sa.ForeignKey("organisations.id"),
            primary_key=True,
        ),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint(
            "role IN ('admin','analyst','viewer')", name="ck_membership_role"
        ),
    )
    op.execute(
        f"INSERT INTO organisation_memberships SELECT '{LOCAL}', id, role FROM users"
    )
    op.drop_column("users", "role")
    for table in (*OWNED, "browser_sessions"):
        op.add_column(
            table,
            sa.Column(
                "organisation_id",
                sa.Uuid,
                nullable=False,
                server_default=sa.text(f"'{LOCAL}'"),
            ),
        )
        op.alter_column(table, "organisation_id", server_default=None)
        op.create_index(f"ix_{table}_organisation_id", table, ["organisation_id"])
        if table in OWNED:
            op.create_foreign_key(
                None, table, "organisations", ["organisation_id"], ["id"]
            )
    op.create_foreign_key(
        None,
        "browser_sessions",
        "organisation_memberships",
        ["organisation_id", "user_id"],
        ["organisation_id", "user_id"],
        ondelete="CASCADE",
    )
    for table in ("scan_sources", "scan_jobs", "scanned_files", "data_fingerprints"):
        op.create_unique_constraint(None, table, ["organisation_id", "id"])
    for table, column, parent in (
        ("scan_jobs", "source_id", "scan_sources"),
        ("scanned_files", "scan_job_id", "scan_jobs"),
        ("findings", "scanned_file_id", "scanned_files"),
        ("findings", "fingerprint_id", "data_fingerprints"),
    ):
        op.create_foreign_key(
            None, table, parent, ["organisation_id", column], ["organisation_id", "id"]
        )
    op.drop_constraint("scan_sources_configured_path_key", "scan_sources")
    op.create_unique_constraint(
        None, "scan_sources", ["organisation_id", "configured_path"]
    )
    # Interrupted scans retain the scheme already used for committed files.
    for table, column in (
        ("scan_jobs", "fingerprint_scheme"),
        ("data_fingerprints", "scheme"),
    ):
        op.add_column(
            table, sa.Column(column, sa.Integer, nullable=False, server_default="1")
        )
        op.alter_column(table, column, server_default=None)
    op.drop_constraint(
        "data_fingerprints_category_key_version_digest_key", "data_fingerprints"
    )
    op.create_unique_constraint(
        None,
        "data_fingerprints",
        ["organisation_id", "scheme", "category", "key_version", "digest"],
    )


def downgrade():
    raise RuntimeError(
        "Restore the pre-upgrade backup to return to a single-organisation schema."
    )
