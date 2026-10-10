"""Own the isolated CI database and exercise real browser/API behavior."""
from __future__ import annotations

import argparse
import asyncio
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path


async def seed(create_schema: bool) -> None:
    import app.main  # register the actual deployed ORM models
    from sqlalchemy import select
    from app.core.security import get_password_hash
    from app.db.init_db import create_tables
    from app.db.session import AsyncSessionLocal
    from app.models.user import User

    if create_schema:
        await create_tables()
    async with AsyncSessionLocal() as session:
        found = await session.scalar(select(User).where(User.email == "ci@example.test"))
        if found is None:
            session.add(User(email="ci@example.test", username="ciadmin", role="admin", is_active=True,
                             hashed_password=get_password_hash("CI-public-fixture-123!")))
            await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed-only", action="store_true")
    parser.add_argument("--external", action="store_true")
    parser.add_argument("--browser", default="chromium")
    parser.add_argument("--migrated", action="store_true")
    args = parser.parse_args()
    if not args.external:
        asyncio.run(seed(not args.migrated))
    if args.seed_only:
        return
    process = None
    if not args.external:
        process = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"])
    try:
        deadline = time.monotonic() + 120
        while True:
            try:
                with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=3) as response:
                    if response.status == 200:
                        break
            except (OSError, TimeoutError):
                pass
            if time.monotonic() >= deadline or (process is not None and process.poll() is not None):
                raise RuntimeError("real application backend did not become healthy")
            time.sleep(0.5)
        frontend = Path(__file__).resolve().parents[2] / "frontend"
        npm = os.environ.get("npm_execpath")
        command = ["node", npm, "exec", "--", "playwright", "test"] if npm else ["npx.cmd" if os.name == "nt" else "npx", "playwright", "test"]
        subprocess.run([*command, "--config", "playwright.ci.config.ts", "--project", args.browser], cwd=frontend, check=True)
    finally:
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == "__main__":
    main()
