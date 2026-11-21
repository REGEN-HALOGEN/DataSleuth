"""Manage organisations and existing users' memberships from a trusted local console."""

import argparse
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from app.core.auth import normalize_username
from app.core.config import database_url, deployment_mode
from app.core.logging import configure_logging
from app.db.session import create_database
from app.models.auth import User
from app.models.organisation import Membership, Organisation


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("name")
    grant = commands.add_parser(
        "grant", help="Set an existing user's role in one organisation"
    )
    revoke = commands.add_parser("revoke")
    for cmd in (grant, revoke):
        cmd.add_argument("organisation_id", type=UUID)
        cmd.add_argument("username")
    grant.add_argument("role", choices=("admin", "analyst", "viewer"))
    args = parser.parse_args()
    configure_logging("INFO")
    engine, sessions = create_database(
        database_url(), hosted=deployment_mode() == "hosted"
    )
    try:
        with sessions.begin() as db:
            if args.action == "create":
                name = args.name.strip()
                if not 1 <= len(name) <= 128:
                    parser.error("Supply an organisation name of 1–128 characters.")
                organisation = Organisation(name=name)
                db.add(organisation)
                db.flush()
                result = f"Created organisation {organisation.id}"
            else:
                user = db.scalar(
                    select(User)
                    .where(User.username == normalize_username(args.username))
                    .with_for_update()
                )
                if user is None or db.get(Organisation, args.organisation_id) is None:
                    parser.error("Unknown user or organisation.")
                membership = db.get(
                    Membership, (args.organisation_id, user.id), with_for_update=True
                )
                if args.action == "grant":
                    if membership is None:
                        db.add(
                            Membership(
                                organisation_id=args.organisation_id,
                                user_id=user.id,
                                role=args.role,
                            )
                        )
                    else:
                        membership.role = args.role
                elif membership is not None:
                    db.delete(membership)
                result = "Membership updated."
    except (SQLAlchemyError, ValueError):
        raise SystemExit(
            "Organisation operation failed. Check the input and database configuration."
        ) from None
    finally:
        engine.dispose()
    print(result)


if __name__ == "__main__":
    main()
