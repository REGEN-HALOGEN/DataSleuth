"""Provision local accounts interactively after applying migrations."""

import argparse
from getpass import GetPassWarning, getpass
import logging
import warnings

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.core.auth import normalize_username, password_hasher
from app.core.config import load_config
from app.core.logging import configure_logging
from app.db.session import create_database
from app.models.auth import BrowserSession, User


def check_admin() -> None:
    configure_logging("INFO")
    try:
        engine, sessions = create_database(load_config()["DATABASE_URL"])
        try:
            with sessions() as db:
                admin_id = db.scalar(
                    select(User.id)
                    .where(User.role == "admin", User.active.is_(True))
                    .limit(1)
                )
        finally:
            engine.dispose()
    except Exception:
        logging.getLogger("datasleuth").error("account_operation_failed")
        raise SystemExit(
            "Could not check for an administrator. Check the database and migrations."
        ) from None
    if admin_id is None:
        raise SystemExit(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username", nargs="?")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check-admin", action="store_true")
    mode.add_argument("--bootstrap-admin", action="store_true")
    mode.add_argument("--reset-admin-password", action="store_true")
    mode.add_argument("--role", choices=("admin", "analyst", "viewer"))
    args = parser.parse_args()
    if args.check_admin:
        if args.username:
            parser.error("--check-admin cannot be combined with account arguments")
        check_admin()
        return
    if not args.username:
        parser.error("username is required")
    role = "admin" if args.bootstrap_admin else args.role
    password_minimum = 10 if args.bootstrap_admin or args.reset_admin_password else 15
    try:
        username = normalize_username(args.username)
    except ValueError as error:
        parser.error(str(error))

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            password = getpass(f"Password ({password_minimum}–256 characters): ")
            confirmation = getpass("Confirm password: ")
    except (GetPassWarning, EOFError):
        raise SystemExit("A terminal with hidden password input is required.") from None
    if not password_minimum <= len(password) <= 256 or password != confirmation:
        raise SystemExit(
            f"Passwords must match and contain {password_minimum}–256 characters."
        )

    configure_logging("INFO")
    try:
        engine, sessions = create_database(load_config()["DATABASE_URL"])
        try:
            with sessions.begin() as db:
                if args.reset_admin_password:
                    user = db.scalar(
                        select(User)
                        .where(
                            User.username == username,
                            User.role == "admin",
                            User.active.is_(True),
                        )
                        .with_for_update()
                    )
                    if user is None:
                        raise SystemExit(
                            "No active administrator with that username was found."
                        )
                    user.password_hash = password_hasher.hash(password)
                    db.execute(
                        delete(BrowserSession).where(BrowserSession.user_id == user.id)
                    )
                else:
                    db.add(
                        User(
                            username=username,
                            role=role,
                            password_hash=password_hasher.hash(password),
                        )
                    )
        finally:
            engine.dispose()
    except IntegrityError:
        raise SystemExit(
            "The account could not be created. Check whether it already exists."
        ) from None
    except Exception:
        logging.getLogger("datasleuth").error("account_operation_failed")
        raise SystemExit(
            "Account operation failed. Check database configuration and migrations."
        ) from None
    print(
        "Administrator password reset. Existing sessions revoked."
        if args.reset_admin_password
        else "Account created."
    )


if __name__ == "__main__":
    main()
