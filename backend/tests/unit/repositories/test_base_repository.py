import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select, func
from app.repositories.base_repository import BaseRepository
from app.models.user import User

@pytest.fixture
def mock_db_session():
    return AsyncMock()

@pytest.fixture
def base_repository(mock_db_session):
    return BaseRepository(User, mock_db_session)


@pytest.mark.asyncio
async def test_get_all(base_repository, mock_db_session):
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_scalars.all.return_value = [User()]
    mock_result.scalars.return_value = mock_scalars
    
    # Needs a mock execute
    mock_db_session.execute.return_value = mock_result
    
    result = await base_repository.get_all(skip=0, limit=10)
    assert len(result) == 1
    mock_db_session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_count(base_repository, mock_db_session):
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 5
    mock_db_session.execute.return_value = mock_result
    
    result = await base_repository.count()
    assert result == 5
    mock_db_session.execute.assert_called_once()

@pytest.mark.asyncio
async def test_create(base_repository, mock_db_session):
    obj = User()
    result = await base_repository.create(obj)
    
    mock_db_session.add.assert_called_once_with(obj)
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(obj)
    assert result == obj

@pytest.mark.asyncio
async def test_update(base_repository, mock_db_session):
    obj = User()
    data = {"email": "updated@example.com"}
    result = await base_repository.update(obj, data)
    
    assert obj.email == "updated@example.com"
    mock_db_session.commit.assert_called_once()
    mock_db_session.refresh.assert_called_once_with(obj)
    assert result == obj

@pytest.mark.asyncio
async def test_delete(base_repository, mock_db_session):
    obj = User()
    await base_repository.delete(obj)
    
    mock_db_session.delete.assert_called_once_with(obj)
    mock_db_session.commit.assert_called_once()
