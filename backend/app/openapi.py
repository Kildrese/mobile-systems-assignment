"""Write the OpenAPI document to `openapi/openapi.json`, or with `--check`,
fail if the committed file is out of date. Needs no database or server:

    uv run python -m app.openapi [--check]
"""

import argparse
import json
import os
import sys
from pathlib import Path

RELATIVE = "openapi/openapi.json"
OUTPUT = Path(__file__).resolve().parents[2] / RELATIVE


def render() -> str:
    # Building the app reads the settings, which require DATABASE_URL. Nothing
    # connects to it here, so any value will do.
    os.environ.setdefault("DATABASE_URL", "postgresql://unused")
    from app.main import app

    return json.dumps(app.openapi(), indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="fail if the file is out of date")
    args = parser.parse_args()

    document = render()
    if args.check:
        current = OUTPUT.read_text() if OUTPUT.exists() else None
        if current != document:
            print(
                f"{RELATIVE} is out of date. Regenerate it with "
                "`uv run python -m app.openapi` in backend/ and commit the result.",
                file=sys.stderr,
            )
            return 1
        print(f"{RELATIVE} is up to date.")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(document)
    print(f"Wrote {RELATIVE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
