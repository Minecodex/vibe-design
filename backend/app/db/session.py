import logging

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import (
    DB_POOL_LOGGING,
    DB_POOL_PRE_PING,
    DB_POOL_RECYCLE,
    DB_POOL_TIMEOUT,
    DB_POOL_USE_LIFO,
    SQLALCHEMY_ECHO,
    settings,
)

logger = logging.getLogger(__name__)


def _is_sqlite_url(database_url: str) -> bool:
    return database_url.startswith("sqlite")


def _build_engine_kwargs(current_settings) -> dict:
    kwargs = {
        "pool_pre_ping": DB_POOL_PRE_PING,
        "echo": SQLALCHEMY_ECHO,
    }

    if _is_sqlite_url(current_settings.DATABASE_URL):
        return kwargs

    kwargs.update(
        {
            "pool_size": current_settings.DB_POOL_SIZE,
            "max_overflow": current_settings.DB_MAX_OVERFLOW,
            "pool_timeout": DB_POOL_TIMEOUT,
            "pool_recycle": DB_POOL_RECYCLE,
            "pool_use_lifo": DB_POOL_USE_LIFO,
        }
    )
    return kwargs


def _attach_pool_logging(async_engine) -> None:
    if not DB_POOL_LOGGING:
        return

    sync_engine = async_engine.sync_engine

    @event.listens_for(sync_engine, "checkout")
    def _log_checkout(dbapi_connection, connection_record, connection_proxy) -> None:
        logger.info("DB pool checkout: %s", sync_engine.pool.status())

    @event.listens_for(sync_engine, "checkin")
    def _log_checkin(dbapi_connection, connection_record) -> None:
        logger.info("DB pool checkin: %s", sync_engine.pool.status())

    @event.listens_for(sync_engine, "invalidate")
    def _log_invalidate(dbapi_connection, connection_record, exception) -> None:
        logger.warning("DB pool invalidate: %s", sync_engine.pool.status())


engine = create_async_engine(
    settings.DATABASE_URL,
    **_build_engine_kwargs(settings),
)
_attach_pool_logging(engine)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


def _build_loop_safe_engine_kwargs(current_settings) -> dict:
    # Some code runs off the main app event loop — the harness runs tools on
    # per-worker event loops (WorkflowActivityRunner), and intake transitively
    # enqueues poller work from there. A pooled async (aiomysql) connection is
    # bound to the event loop that created it, so reusing one across loops raises
    # "got Future attached to a different loop". NullPool opens a fresh connection
    # per session on whatever loop is currently running and disposes it on close,
    # which is the SQLAlchemy-documented way to share an async engine across loops.
    if _is_sqlite_url(current_settings.DATABASE_URL):
        # Mirror the primary engine for SQLite: NullPool would give every
        # connection its own in-memory database and break shared in-memory DBs.
        return {"echo": SQLALCHEMY_ECHO}
    return {"echo": SQLALCHEMY_ECHO, "poolclass": NullPool, "pool_pre_ping": DB_POOL_PRE_PING}


# Engine for DB access that may run off the main event loop. Kept separate from
# the primary pooled `engine` so the main app (scheduler loop, request handlers,
# gateway event persistence) keeps connection pooling, while off-loop callers
# (harness worker loops, intake-triggered enqueue) stay cross-loop safe.
loop_safe_engine = create_async_engine(
    settings.DATABASE_URL,
    **_build_loop_safe_engine_kwargs(settings),
)

LoopSafeAsyncSessionLocal = async_sessionmaker(
    loop_safe_engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)
