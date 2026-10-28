"""Operator commands.

    python -m app.cli users list
    python -m app.cli users add <username> [--password P]   # random password if omitted
    python -m app.cli users passwd <username> [--password P]
    python -m app.cli users remove <username>
"""

import argparse
import asyncio
import logging
import sys

from app.db import dispose_engine
from app.main import _run_migrations
from app.services.auth import AuthStore, generate_password


async def _run(args: argparse.Namespace) -> int:
    store = AuthStore()
    try:
        if args.command == "list":
            for u in await store.list_users():
                print(f"{u['username']}\t{u['created_at']:%Y-%m-%d %H:%M}")
            return 0
        if args.command == "remove":
            if not await store.delete_user(args.username):
                print(f"Пользователь {args.username!r} не найден", file=sys.stderr)
                return 1
            print(f"Удалён {args.username}")
            return 0

        password = args.password or generate_password()
        if args.command == "add":
            if not await store.create_user(args.username, password):
                print(f"Пользователь {args.username!r} уже существует", file=sys.stderr)
                return 1
        elif not await store.set_password(args.username, password):
            print(f"Пользователь {args.username!r} не найден", file=sys.stderr)
            return 1
        print(f"логин:  {args.username}\nпароль: {password}")
        return 0
    finally:
        await dispose_engine()


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    groups = parser.add_subparsers(dest="group", required=True)
    users = groups.add_parser("users", help="управление пользователями веб-интерфейса")
    sub = users.add_subparsers(dest="command", required=True)
    sub.add_parser("list")
    for name in ("add", "passwd"):
        p = sub.add_parser(name)
        p.add_argument("username")
        p.add_argument("--password", help="по умолчанию генерируется случайный")
    sub.add_parser("remove").add_argument("username")
    args = parser.parse_args()

    logging.getLogger("alembic").setLevel(logging.WARNING)
    _run_migrations()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
