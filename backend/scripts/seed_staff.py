"""Create or promote one admin account and one partner account.

Set these environment variables before running. Passwords are read only
when the email is not already registered. Existing accounts keep their
password and are assigned the staff role.

    NIVA_ADMIN_EMAIL
    NIVA_ADMIN_PASSWORD
    NIVA_PARTNER_EMAIL
    NIVA_PARTNER_PASSWORD

Run from the backend directory:

    python -m scripts.seed_staff

The project ``.env`` is loaded first, so ``DATABASE_URL`` is available
when the script is started from the command line.
"""

from dotenv import load_dotenv

load_dotenv()

import asyncio
import os
import sys

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.session import get_engine
from app.services.admin_service import StaffPasswordRequiredError, seed_staff_accounts


def _required_email(name: str) -> str:
    """Return a staff email from the environment, or stop the script."""
    value = os.environ.get(name, "").strip()
    if value == "":
        print(f"{name} is required.", file=sys.stderr)
        raise SystemExit(1)
    return value


async def _seed() -> None:
    """Open one session, seed both staff accounts, and commit."""
    admin_email = _required_email("NIVA_ADMIN_EMAIL")
    partner_email = _required_email("NIVA_PARTNER_EMAIL")
    admin_password = os.environ.get("NIVA_ADMIN_PASSWORD")
    partner_password = os.environ.get("NIVA_PARTNER_PASSWORD")
    engine = get_engine()
    factory = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    try:
        async with factory() as session:
            try:
                admin, partner = await seed_staff_accounts(
                    session,
                    admin_email=admin_email,
                    admin_password=admin_password,
                    partner_email=partner_email,
                    partner_password=partner_password,
                )
            except StaffPasswordRequiredError:
                print(
                    "A password is required when that email is not already registered.",
                    file=sys.stderr,
                )
                raise SystemExit(1) from None
            await session.commit()
            print(f"admin {admin.email} id={admin.id}")
            print(f"partner {partner.email} id={partner.id}")
    finally:
        await engine.dispose()


def main() -> None:
    """Run the staff seed from the command line."""
    asyncio.run(_seed())


if __name__ == "__main__":
    main()
