"""Read-only verification of the active ResearchMate MySQL security boundary."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402


async def verify() -> dict:
    engine = create_async_engine(
        settings.database_url,
        connect_args=settings.database_connect_args,
        poolclass=NullPool,
    )
    try:
        async with engine.connect() as connection:
            identity = (
                await connection.execute(
                    text(
                        "SELECT CURRENT_USER(), @@bind_address, "
                        "@@require_secure_transport"
                    )
                )
            ).one()
            cipher = (
                await connection.execute(text("SHOW STATUS LIKE 'Ssl_cipher'"))
            ).one()
            grants = [
                str(row[0])
                for row in (
                    await connection.execute(text("SHOW GRANTS FOR CURRENT_USER"))
                ).all()
            ]
            counts = (
                await connection.execute(
                    text(
                        "SELECT "
                        "(SELECT COUNT(*) FROM sessions), "
                        "(SELECT COUNT(*) FROM messages), "
                        "(SELECT COUNT(*) FROM documents WHERE type='knowledge')"
                    )
                )
            ).one()
    finally:
        await engine.dispose()

    current_user, bind_address, require_transport = identity
    cipher_value = str(cipher[1] or "")
    excessive = any(
        "ALL PRIVILEGES" in grant.upper() or "GRANT OPTION" in grant.upper()
        for grant in grants
    )
    success = (
        str(current_user).startswith(f"{settings.mysql_user}@")
        and str(bind_address) in {"127.0.0.1", "::1", "localhost"}
        and bool(require_transport)
        and bool(cipher_value)
        and not excessive
    )
    return {
        "success": success,
        "current_user": str(current_user),
        "bind_address": str(bind_address),
        "require_secure_transport": bool(require_transport),
        "tls_cipher_negotiated": bool(cipher_value),
        "grant_statements": len(grants),
        "excessive_global_privileges": excessive,
        "credentials_printed": False,
        "row_counts": {
            "sessions": int(counts[0]),
            "messages": int(counts[1]),
            "knowledge_documents": int(counts[2]),
        },
    }


def main() -> int:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    result = asyncio.run(verify())
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
