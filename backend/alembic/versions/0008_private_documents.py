"""Allow an immutable, managed document as a scan source."""

from alembic import op
import sqlalchemy as sa

revision = "0008_private_documents"
down_revision = "0007_organisation_ownership"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("scan_sources", "configured_path", nullable=True)
    for name, kind in (
        ("upload_state", sa.String(12)),
        ("storage_namespace", sa.String(64)),
        ("extension", sa.String(5)),
        ("size_bytes", sa.BigInteger()),
        ("content_digest", sa.String(64)),
        ("expires_at", sa.DateTime(timezone=True)),
    ):
        op.add_column("scan_sources", sa.Column(name, kind, nullable=True))
    op.create_check_constraint(
        "ck_scan_source_storage",
        "scan_sources",
        "(configured_path IS NOT NULL AND upload_state IS NULL AND storage_namespace IS NULL AND extension IS NULL AND size_bytes IS NULL AND content_digest IS NULL AND expires_at IS NULL) OR "
        "(configured_path IS NULL AND upload_state IS NOT NULL AND upload_state IN ('pending','ready','deleting','deleted') AND storage_namespace IS NOT NULL AND extension IS NOT NULL AND size_bytes IS NOT NULL AND size_bytes > 0 AND expires_at IS NOT NULL AND (upload_state = 'ready' OR NOT enabled) AND (upload_state <> 'ready' OR content_digest IS NOT NULL))",
    )
    op.create_index(
        "ix_scan_source_retention",
        "scan_sources",
        ["storage_namespace", "upload_state", "expires_at"],
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text(
            "SELECT EXISTS (SELECT FROM scan_sources WHERE configured_path IS NULL)"
        )
    ):
        raise RuntimeError(
            "Managed source history requires the private-document schema."
        )
    op.drop_index("ix_scan_source_retention", table_name="scan_sources")
    op.drop_constraint("ck_scan_source_storage", "scan_sources")
    for name in (
        "upload_state",
        "storage_namespace",
        "extension",
        "size_bytes",
        "content_digest",
        "expires_at",
    ):
        op.drop_column("scan_sources", name)
    op.alter_column("scan_sources", "configured_path", nullable=False)
