import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from app.main import app
from app.api.deps import get_db
from app.db.base import Base
from app.db.session import AsyncSessionLocal

TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    yield loop
    loop.close()
    asyncio.set_event_loop(None)


@pytest.fixture(autouse=True)
def ensure_current_event_loop():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    yield


@pytest.fixture(autouse=True)
def disable_redis_required_in_tests():
    """Unit tests do not have a real Redis available, so distributed-correctness
    operations (lease / rate_limit / duplicate_guard) would raise
    RedisCoordinationDegradedError under the production default REDIS_REQUIRED=True.
    Force REDIS_REQUIRED=False for the test process; tests that explicitly need
    strict-mode semantics construct their own local Settings/RedisCoordinator."""
    from app.core.config import settings

    original = settings.REDIS_REQUIRED
    settings.REDIS_REQUIRED = False
    yield
    settings.REDIS_REQUIRED = original


@pytest.fixture(autouse=True)
def isolate_harness_storage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "app.core.config.settings.HARNESS_STORAGE_DATABASE_URL",
        f"sqlite:///{tmp_path.joinpath('harness_sessions.db').as_posix()}",
    )


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DATABASE_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(test_engine) -> AsyncGenerator[AsyncSession, None]:
    TestSessionLocal = async_sessionmaker(test_engine, expire_on_commit=False)
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


@pytest_asyncio.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    @asynccontextmanager
    async def override_session_factory():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.db_session_factory = override_session_factory

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()
    app.state.db_session_factory = AsyncSessionLocal


@pytest_asyncio.fixture
async def auth_client(client: AsyncClient, db_session: AsyncSession) -> AsyncClient:
    from app.models.user import User
    from app.core.security import get_password_hash, create_access_token

    user = User(
        email="test@example.com",
        username="testuser",
        hashed_password=get_password_hash("Test1234!"),
        role="user",
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    token = create_access_token(subject=user.id)
    client.headers["Authorization"] = f"Bearer {token}"
    return client
