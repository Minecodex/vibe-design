from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from threading import Lock
from typing import Any, Callable

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import (
    DB_POOL_PRE_PING,
    DB_POOL_RECYCLE,
    DB_POOL_TIMEOUT,
    DB_POOL_USE_LIFO,
    SQLALCHEMY_ECHO,
    settings,
)
from app.models.harness_session import (
    ConversationEvent,
    ContextProjectionRun,
    ContextProjectionState,
    HarnessAgentActivity,
    HarnessAgentRun,
    HarnessAgentStep,
    HarnessConversation,
    HarnessMessage,
    HarnessPresentationProjectionState,
    HarnessResourceLease,
    HarnessWorkspaceFile,
)

_LOCK = Lock()
_ENGINE_CACHE: dict[str, Engine] = {}
_SESSIONMAKER_CACHE: dict[str, sessionmaker[Session]] = {}
_SQLITE_INIT_DONE: set[str] = set()


def harness_sync_database_url() -> str:
    storage_url = str(getattr(settings, "HARNESS_STORAGE_DATABASE_URL", "") or "").strip()
    if storage_url:
        return storage_url
    database_url = str(settings.DATABASE_URL or "").strip()
    if database_url.startswith("mysql+aiomysql://"):
        return "mysql+pymysql://" + database_url.removeprefix("mysql+aiomysql://")
    if database_url.startswith("mysql+pymysql://"):
        return database_url
    raise RuntimeError(
        "Harness hot storage requires a MySQL DATABASE_URL or explicit HARNESS_STORAGE_DATABASE_URL override."
    )


def _build_engine(url: str) -> Engine:
    kwargs: dict[str, object] = {
        "pool_pre_ping": DB_POOL_PRE_PING,
        "echo": SQLALCHEMY_ECHO,
        "future": True,
    }
    if url.startswith("sqlite"):
        kwargs["connect_args"] = {"check_same_thread": False}
    else:
        kwargs.update(
            {
                "pool_size": settings.DB_POOL_SIZE,
                "max_overflow": settings.DB_MAX_OVERFLOW,
                "pool_timeout": DB_POOL_TIMEOUT,
                "pool_recycle": DB_POOL_RECYCLE,
                "pool_use_lifo": DB_POOL_USE_LIFO,
            }
        )
    return create_engine(url, **kwargs)


def _ensure_sqlite_tables(engine: Engine, url: str) -> None:
    if not url.startswith("sqlite"):
        return
    if url in _SQLITE_INIT_DONE:
        return
    with _LOCK:
        if url in _SQLITE_INIT_DONE:
            return
        HarnessConversation.metadata.create_all(
            engine,
            tables=[
                HarnessConversation.__table__,
                HarnessMessage.__table__,
                HarnessWorkspaceFile.__table__,
                ConversationEvent.__table__,
                HarnessPresentationProjectionState.__table__,
                ContextProjectionState.__table__,
                ContextProjectionRun.__table__,
                HarnessAgentRun.__table__,
                HarnessAgentStep.__table__,
                HarnessAgentActivity.__table__,
                HarnessResourceLease.__table__,
            ],
        )
        _SQLITE_INIT_DONE.add(url)


def harness_sync_sessionmaker() -> sessionmaker[Session]:
    url = harness_sync_database_url()
    with _LOCK:
        maker = _SESSIONMAKER_CACHE.get(url)
        if maker is None:
            engine = _ENGINE_CACHE.get(url)
            if engine is None:
                engine = _build_engine(url)
                _ENGINE_CACHE[url] = engine
            maker = sessionmaker(bind=engine, expire_on_commit=False, autoflush=False, future=True)
            _SESSIONMAKER_CACHE[url] = maker
    _ensure_sqlite_tables(_ENGINE_CACHE[url], url)
    return maker


@contextmanager
def harness_sync_session_scope() -> Session:
    session = harness_sync_sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


_HARNESS_DB_EXECUTOR: ThreadPoolExecutor | None = None
_HARNESS_DB_EXECUTOR_LOCK = Lock()


def harness_db_executor() -> ThreadPoolExecutor:
    # Dedicated thread pool for synchronous harness DB calls invoked from
    # async contexts. Sized to the underlying pymysql connection pool so a
    # thread cannot exist without a connection to claim — preventing the
    # "threads queued on get_connection" failure mode. Kept separate from
    # asyncio's default executor so non-DB blocking work (file IO, external
    # APIs) does not compete with DB calls for the same thread budget.
    global _HARNESS_DB_EXECUTOR
    if _HARNESS_DB_EXECUTOR is None:
        with _HARNESS_DB_EXECUTOR_LOCK:
            if _HARNESS_DB_EXECUTOR is None:
                max_workers = max(int(settings.DB_POOL_SIZE) + int(settings.DB_MAX_OVERFLOW), 1)
                _HARNESS_DB_EXECUTOR = ThreadPoolExecutor(
                    max_workers=max_workers,
                    thread_name_prefix="harness-db",
                )
    return _HARNESS_DB_EXECUTOR


async def run_harness_db(func: Callable[..., Any], /, *args: Any, **kwargs: Any) -> Any:
    loop = asyncio.get_running_loop()
    if kwargs:
        return await loop.run_in_executor(harness_db_executor(), partial(func, *args, **kwargs))
    return await loop.run_in_executor(harness_db_executor(), func, *args)


def shutdown_harness_db_executor() -> None:
    global _HARNESS_DB_EXECUTOR
    with _HARNESS_DB_EXECUTOR_LOCK:
        executor = _HARNESS_DB_EXECUTOR
        _HARNESS_DB_EXECUTOR = None
    if executor is not None:
        executor.shutdown(wait=True, cancel_futures=False)
