import pytest
from unittest.mock import AsyncMock, patch
from app.services.auth_service import AuthService
from app.schemas.auth import RegisterRequest
from app.core.exceptions import ConflictException, UnauthorizedException
from app.models.user import User

@pytest.fixture
def mock_db_session():
    return AsyncMock()

@pytest.fixture
def auth_service(mock_db_session):
    return AuthService(mock_db_session)

@pytest.mark.asyncio
async def test_register_duplicate_email(auth_service):
    with patch.object(auth_service.repo, 'get_by_email', new_callable=AsyncMock) as mock_get_by_email:
        mock_get_by_email.return_value = User(id=1, email="test@example.com")
        
        request = RegisterRequest(
            email="test@example.com",
            username="testuser",
            password="Password123!"
        )
        
        with pytest.raises(ConflictException, match="该邮箱已被注册"):
            await auth_service.register(request)

@pytest.mark.asyncio
async def test_register_duplicate_username(auth_service):
    with patch.object(auth_service.repo, 'get_by_email', new_callable=AsyncMock) as mock_get_by_email, \
         patch.object(auth_service.repo, 'get_by_username', new_callable=AsyncMock) as mock_get_by_username:
        
        mock_get_by_email.return_value = None
        mock_get_by_username.return_value = User(id=1, username="testuser")
        
        request = RegisterRequest(
            email="new@example.com",
            username="testuser",
            password="Password123!"
        )
        
        with pytest.raises(ConflictException, match="该用户名已被使用"):
            await auth_service.register(request)

@pytest.mark.asyncio
async def test_authenticate_user_not_found(auth_service):
    with patch.object(auth_service.repo, 'get_by_email', new_callable=AsyncMock) as mock_get_by_email, \
         patch.object(auth_service.repo, 'get_by_username', new_callable=AsyncMock) as mock_get_by_username:
        mock_get_by_email.return_value = None
        mock_get_by_username.return_value = None
        
        result = await auth_service.authenticate("test@example.com", "Password123!")
        assert result is None
        mock_get_by_username.assert_awaited_once_with("test@example.com")

@pytest.mark.asyncio
async def test_authenticate_wrong_password(auth_service):
    with patch.object(auth_service.repo, 'get_by_email', new_callable=AsyncMock) as mock_get_by_email, \
         patch('app.services.auth_service.verify_password') as mock_verify:
        
        mock_get_by_email.return_value = User(id=1)
        mock_verify.return_value = False
        
        result = await auth_service.authenticate("test@example.com", "WrongPassword!")
        assert result is None

@pytest.mark.asyncio
async def test_authenticate_user_inactive(auth_service):
    with patch.object(auth_service.repo, 'get_by_email', new_callable=AsyncMock) as mock_get_by_email, \
         patch('app.services.auth_service.verify_password') as mock_verify:
        
        mock_get_by_email.return_value = User(id=1, is_active=False)
        mock_verify.return_value = True
        
        with pytest.raises(UnauthorizedException, match="账户已被禁用"):
            await auth_service.authenticate("test@example.com", "Password123!")

@pytest.mark.asyncio
async def test_refresh_invalid_type(auth_service):
    with patch('app.services.auth_service.decode_token') as mock_decode:
        mock_decode.return_value = {"type": "access", "sub": "1"}
        
        with pytest.raises(UnauthorizedException, match="无效的 refresh token"):
            await auth_service.refresh("invalid_token")

@pytest.mark.asyncio
async def test_refresh_invalid_payload(auth_service):
    with patch('app.services.auth_service.decode_token') as mock_decode:
        mock_decode.side_effect = ValueError()
        
        with pytest.raises(UnauthorizedException, match="无效的 refresh token"):
            await auth_service.refresh("invalid_token")

@pytest.mark.asyncio
async def test_refresh_user_not_found_or_inactive(auth_service):
    with patch('app.services.auth_service.decode_token') as mock_decode, \
         patch.object(auth_service.repo, 'get', new_callable=AsyncMock) as mock_get:
        
        mock_decode.return_value = {"type": "refresh", "sub": "1"}
        mock_get.return_value = None
        
        with pytest.raises(UnauthorizedException, match="用户不存在或已被禁用"):
            await auth_service.refresh("valid_token")
