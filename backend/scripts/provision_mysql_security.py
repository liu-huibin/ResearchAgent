"""Provision a least-privilege ResearchMate MySQL account without printing secrets."""

from __future__ import annotations

import argparse
import asyncio
import os
import re
import secrets
import ssl
import sys
from pathlib import Path

import aiomysql
from dotenv import dotenv_values


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.file_permissions import harden_private_path  # noqa: E402

IDENTIFIER = re.compile(r"^[A-Za-z0-9_]+$")


def _passwords(args: argparse.Namespace) -> tuple[str, str, Path, bool]:
    admin_password = os.environ.get("MYSQL_ADMIN_PASSWORD", "")
    if not admin_password and args.use_backend_env_admin:
        admin_password = str(
            dotenv_values(BACKEND_DIR / ".env").get("MYSQL_PASSWORD") or ""
        )

    password_path = Path(args.password_file)
    if not password_path.is_absolute():
        password_path = BACKEND_DIR / password_path
    app_password = os.environ.get("RESEARCHMATE_DB_PASSWORD", "")
    if not app_password and password_path.is_file():
        app_password = password_path.read_text(encoding="utf-8").strip()

    created = False
    if not app_password and args.generate_password:
        app_password = secrets.token_urlsafe(48)
        password_path.parent.mkdir(parents=True, exist_ok=True)
        password_path.write_text(app_password + "\n", encoding="utf-8")
        created = True
        if not harden_private_path(password_path.parent) or not harden_private_path(
            password_path
        ):
            password_path.unlink(missing_ok=True)
            raise SystemExit("Could not restrict generated password file permissions.")

    if not admin_password or not app_password:
        raise SystemExit(
            "Provide admin/app credentials through environment variables or secure-file options."
        )
    if len(app_password) < 24:
        raise SystemExit("The application password must contain at least 24 characters.")
    return admin_password, app_password, password_path, created


async def provision(args: argparse.Namespace) -> None:
    for value in (args.database, args.app_user):
        if not IDENTIFIER.fullmatch(value):
            raise SystemExit(
                "Database and account names may contain only letters, digits, and underscore."
            )
    admin_password, app_password, password_path, created = _passwords(args)
    context = (
        ssl.create_default_context(cafile=args.ssl_ca or None)
        if args.require_tls
        else None
    )
    try:
        connection = await aiomysql.connect(
            host=args.host,
            port=args.port,
            user=args.admin_user,
            password=admin_password,
            ssl=context,
            autocommit=True,
        )
        try:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    f"CREATE USER IF NOT EXISTS `{args.app_user}`@`localhost` IDENTIFIED BY %s",
                    (app_password,),
                )
                await cursor.execute(
                    f"ALTER USER `{args.app_user}`@`localhost` IDENTIFIED BY %s",
                    (app_password,),
                )
                await cursor.execute(
                    f"GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, "
                    f"REFERENCES ON `{args.database}`.* TO `{args.app_user}`@`localhost`"
                )
        finally:
            connection.close()
    except Exception:
        if created:
            password_path.unlink(missing_ok=True)
        raise
    print("Least-privilege MySQL account provisioned; no passwords were printed.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=3306)
    parser.add_argument("--admin-user", default="root")
    parser.add_argument("--app-user", default="researchmate_app")
    parser.add_argument("--database", default="research_mate")
    parser.add_argument("--require-tls", action="store_true")
    parser.add_argument("--ssl-ca", default="")
    parser.add_argument("--password-file", default=".secrets/mysql_app_password")
    parser.add_argument("--generate-password", action="store_true")
    parser.add_argument("--use-backend-env-admin", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if not args.apply:
        print("Dry run only. Re-run with --apply after reviewing MYSQL_SECURITY.md.")
        return 0
    asyncio.run(provision(args))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
