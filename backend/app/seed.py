"""Create the test account: `python -m app.seed`. Idempotent."""

import sys

from app import schemas
from app.db import get_sessionmaker
from app.errors import USERNAME_TAKEN, ApiError
from app.services import accounts

USERNAME = "NYUgrader"
PASSWORD = "Courant2026!"


def main() -> None:
    body = schemas.RegisterBody(
        username=USERNAME, password=PASSWORD, first_name="NYU", last_name="Grader"
    )
    with get_sessionmaker()() as db:
        try:
            accounts.register(db, body)
        except ApiError as err:
            if err is USERNAME_TAKEN:
                print(f"Test account {USERNAME} already exists; left unchanged.")
                return
            raise
    print(f"Created test account {USERNAME} (password {PASSWORD}).")


if __name__ == "__main__":
    sys.exit(main())
