"""Tenant ownership shared by the API and scanner."""

from uuid import UUID, uuid4
from sqlalchemy import CheckConstraint, ForeignKey, ForeignKeyConstraint, String, select
from sqlalchemy.orm import Mapped, mapped_column
from app.models.auth import Base, User

LOCAL_ORGANISATION = UUID("00000000-0000-4000-8000-000000000001")


class Organisation(Base):
    __tablename__ = "organisations"
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(128))


class Membership(Base):
    __tablename__ = "organisation_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('admin','analyst','viewer')", name="ck_membership_role"
        ),
    )
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id"), primary_key=True
    )
    user_id: Mapped[UUID] = mapped_column(ForeignKey("users.id"), primary_key=True)
    role: Mapped[str] = mapped_column(String(16))


class Owned:
    organisation_id: Mapped[UUID] = mapped_column(
        ForeignKey("organisations.id"), index=True
    )


def owned_parent(column: str, table: str):
    return ForeignKeyConstraint(
        ["organisation_id", column], [f"{table}.organisation_id", f"{table}.id"]
    )


def owned_row(db, model, row_id, organisation_id, *, lock=False):
    query = select(model).where(
        model.id == row_id, model.organisation_id == organisation_id
    )
    return db.scalar(query.with_for_update() if lock else query)


def operator_membership(db, user_id, organisation_id):
    return db.scalar(
        select(Membership)
        .join(User, User.id == Membership.user_id)
        .where(
            User.active.is_(True),
            Membership.user_id == user_id,
            Membership.organisation_id == organisation_id,
            Membership.role.in_(("admin", "analyst")),
        )
        .with_for_update(read=True)
    )
