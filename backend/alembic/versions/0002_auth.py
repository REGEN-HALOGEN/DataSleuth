"""Add users and browser sessions."""

import sqlalchemy as sa
from alembic import op

revision = "0002_auth"
down_revision = "0001_baseline"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("username", sa.String(64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "role IN ('admin', 'analyst', 'viewer')", name="ck_users_role"
        ),
    )
    op.create_table(
        "browser_sessions",
        sa.Column("token_digest", sa.String(64), primary_key=True),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_browser_sessions_user_id", "browser_sessions", ["user_id"])
    op.create_index(
        "ix_browser_sessions_expires_at", "browser_sessions", ["expires_at"]
    )


def downgrade():
    op.drop_table("browser_sessions")
    op.drop_table("users")
