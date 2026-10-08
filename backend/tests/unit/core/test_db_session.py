from types import SimpleNamespace

from app.db import session as db_session


def test_build_engine_kwargs_uses_configured_pool_values_for_non_sqlite_urls():
    settings = SimpleNamespace(
        DATABASE_URL="mysql+aiomysql://user:pass@host:3306/db",
        SQLALCHEMY_ECHO=True,
        DB_POOL_PRE_PING=True,
        DB_POOL_SIZE=20,
        DB_MAX_OVERFLOW=30,
        DB_POOL_TIMEOUT=45,
        DB_POOL_RECYCLE=1800,
        DB_POOL_USE_LIFO=True,
    )

    assert db_session._build_engine_kwargs(settings) == {
        "pool_pre_ping": True,
        "echo": db_session.SQLALCHEMY_ECHO,
        "pool_size": 20,
        "max_overflow": 30,
        "pool_timeout": db_session.DB_POOL_TIMEOUT,
        "pool_recycle": db_session.DB_POOL_RECYCLE,
        "pool_use_lifo": db_session.DB_POOL_USE_LIFO,
    }


def test_build_engine_kwargs_skips_queue_pool_settings_for_sqlite():
    settings = SimpleNamespace(
        DATABASE_URL="sqlite+aiosqlite:///./dev.db",
        SQLALCHEMY_ECHO=False,
        DB_POOL_PRE_PING=True,
        DB_POOL_SIZE=20,
        DB_MAX_OVERFLOW=30,
        DB_POOL_TIMEOUT=45,
        DB_POOL_RECYCLE=1800,
        DB_POOL_USE_LIFO=True,
    )

    assert db_session._build_engine_kwargs(settings) == {
        "pool_pre_ping": True,
        "echo": False,
    }
