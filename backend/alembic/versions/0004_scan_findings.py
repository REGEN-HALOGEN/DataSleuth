"""Add scan jobs, file metadata, masked findings, and versioned fingerprints."""

import sqlalchemy as sa
from alembic import op

revision = "0004_scan_findings"
down_revision = "0003_scan_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "scan_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id", sa.Uuid(), sa.ForeignKey("scan_sources.id"), nullable=False
        ),
        sa.Column("created_by", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("files_discovered", sa.Integer(), nullable=False),
        sa.Column("files_processed", sa.Integer(), nullable=False),
        sa.Column("files_skipped", sa.Integer(), nullable=False),
        sa.Column("files_failed", sa.Integer(), nullable=False),
        sa.Column("findings_created", sa.Integer(), nullable=False),
        sa.Column("inventory_limited", sa.Boolean(), nullable=False),
        sa.Column("error_summary", sa.String(40)),
    )
    op.create_index("ix_scan_jobs_source_id", "scan_jobs", ["source_id"])

    op.create_table(
        "scanned_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scan_job_id", sa.Uuid(), sa.ForeignKey("scan_jobs.id"), nullable=False
        ),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("parse_status", sa.String(32), nullable=False),
        sa.UniqueConstraint("scan_job_id", "relative_path"),
    )
    op.create_index("ix_scanned_files_scan_job_id", "scanned_files", ["scan_job_id"])

    op.create_table(
        "data_fingerprints",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("key_version", sa.Integer(), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("category", "key_version", "digest"),
    )

    op.create_table(
        "findings",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "scanned_file_id",
            sa.Uuid(),
            sa.ForeignKey("scanned_files.id"),
            nullable=False,
        ),
        sa.Column(
            "fingerprint_id",
            sa.Uuid(),
            sa.ForeignKey("data_fingerprints.id"),
            nullable=False,
        ),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("detector_version", sa.Integer(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("location", sa.Integer(), nullable=False),
        sa.Column("masked_evidence", sa.String(32), nullable=False),
    )
    op.create_index("ix_findings_scanned_file_id", "findings", ["scanned_file_id"])
    op.create_index("ix_findings_fingerprint_id", "findings", ["fingerprint_id"])


def downgrade():
    op.drop_table("findings")
    op.drop_table("data_fingerprints")
    op.drop_table("scanned_files")
    op.drop_table("scan_jobs")
