#!/usr/bin/env python3
"""
Development memory reset — wipes Pinecone vectors and Postgres session data.

NEVER run against production. Prompts for confirmation before any destructive
action. Requires DATABASE_URL, REDIS_URL, PINECONE_API_KEY, PINECONE_INDEX in
environment (or a .env file at the repo root).

Usage:
    python scripts/reset_memory.py [--yes] [--skip-pinecone] [--skip-postgres]
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Load .env from repo root if present
_REPO_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _REPO_ROOT / ".env"
if _ENV_FILE.exists():
    for line in _ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


async def _reset_postgres(database_url: str) -> None:
    import asyncpg  # type: ignore[import]

    url = str(database_url).replace("postgresql+asyncpg://", "postgresql://")
    conn = await asyncpg.connect(url)
    try:
        await conn.execute("TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE")
        await conn.execute("TRUNCATE TABLE sessions CASCADE")
        print("  Postgres: truncated sessions + audit_log")
    finally:
        await conn.close()


def _reset_pinecone(api_key: str, index_name: str) -> None:
    from pinecone import Pinecone  # type: ignore[import]

    pc = Pinecone(api_key=api_key)
    index = pc.Index(index_name)
    stats = index.describe_index_stats()
    namespaces = list((stats.get("namespaces") or {}).keys())
    if not namespaces:
        print("  Pinecone: no namespaces found (already empty)")
        return
    for ns in namespaces:
        index.delete(delete_all=True, namespace=ns)
        print(f"  Pinecone: deleted all vectors in namespace '{ns}'")


async def _main(yes: bool, skip_pinecone: bool, skip_postgres: bool) -> int:
    print("\n⚠️  Project Nexus — Development Memory Reset")
    print("=" * 50)
    print("This will permanently delete:")
    if not skip_postgres:
        print("  • All rows in sessions and audit_log (Postgres)")
    if not skip_pinecone:
        print("  • All vectors in every namespace (Pinecone)")
    print()

    if not yes:
        answer = input("Type 'yes' to continue: ").strip().lower()
        if answer != "yes":
            print("Aborted.")
            return 0

    errors: list[str] = []

    if not skip_postgres:
        database_url = os.environ.get("DATABASE_URL", "")
        if not database_url:
            errors.append("DATABASE_URL not set — skipping Postgres reset")
            print(f"  WARNING: {errors[-1]}")
        else:
            try:
                await _reset_postgres(database_url)
            except Exception as exc:
                errors.append(f"Postgres reset failed: {exc}")
                print(f"  ERROR: {errors[-1]}")

    if not skip_pinecone:
        api_key = os.environ.get("PINECONE_API_KEY", "")
        index_name = os.environ.get("PINECONE_INDEX", "nexus-memory")
        if not api_key:
            errors.append("PINECONE_API_KEY not set — skipping Pinecone reset")
            print(f"  WARNING: {errors[-1]}")
        else:
            try:
                _reset_pinecone(api_key, index_name)
            except Exception as exc:
                errors.append(f"Pinecone reset failed: {exc}")
                print(f"  ERROR: {errors[-1]}")

    print()
    if errors:
        print(f"Completed with {len(errors)} error(s).")
        return 1
    print("Reset complete.")
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Wipe Project Nexus dev data")
    parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("--skip-pinecone", action="store_true", help="Don't touch Pinecone")
    parser.add_argument("--skip-postgres", action="store_true", help="Don't touch Postgres")
    args = parser.parse_args()

    sys.exit(asyncio.run(_main(args.yes, args.skip_pinecone, args.skip_postgres)))
