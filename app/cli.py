"""
Operator commands that are deliberately not reachable over HTTP.

Usage::

    python -m app.cli wipe --yes

Running them needs shell access to the server, a far stronger proof of
authority than an API key, which can leak.
"""

import argparse
import asyncio

from app.core.broker import create_redis
from app.core.config import settings
from app.db.session import AsyncSessionLocal
from app.main import create_store
from app.services.job_service import clear_all_data

EXIT_OK = 0
EXIT_NOT_CONFIRMED = 1


def build_parser() -> argparse.ArgumentParser:
    """
    Describe the command line: one sub-command per operator task.

    :return: Configured parser.
    :rtype: argparse.ArgumentParser
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.cli",
        description="AtomField operator commands.",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    wipe = commands.add_parser(
        "wipe",
        help="Delete every user's jobs, files and queued work.",
    )
    wipe.add_argument(
        "--yes",
        action="store_true",
        help="Confirm. Without it, nothing is deleted.",
    )
    return parser


async def wipe_everything() -> dict:
    """
    Delete all jobs, workspace files and queued work for every user.

    API keys are kept, so users can still sign in afterwards.

    :return: Summary returned by the service layer.
    :rtype: dict
    """
    redis = create_redis()
    try:
        async with AsyncSessionLocal() as session:
            return await clear_all_data(
                db=session, store=create_store(), redis_queue=redis
            )
    finally:
        await redis.aclose()


def main(argv: list[str] | None = None) -> int:
    """
    Run one operator command.

    :param argv: Arguments; None reads them from the command line.
    :type argv: list[str] | None
    :return: Process exit code.
    :rtype: int
    """
    options = build_parser().parse_args(argv)
    target = f"database {settings.POSTGRES_DB!r} on {settings.POSTGRES_HOST}"
    if not options.yes:
        print(f"Would wipe {target}. Re-run with --yes to confirm.")
        return EXIT_NOT_CONFIRMED
    print(f"Wiping {target} ...")
    print(asyncio.run(wipe_everything())["message"])
    return EXIT_OK


if __name__ == "__main__":
    raise SystemExit(main())
