from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.redis_client import RedisUnavailableError
from app.core.security import authenticate_token

bearer_scheme = HTTPBearer(auto_error=False)


async def _decode_admin_credentials(
    credentials: HTTPAuthorizationCredentials | None,
) -> dict | None:
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        payload = await authenticate_token(credentials.credentials)
    except RedisUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail="认证安全状态暂不可用，请稍后重试",
        ) from exc
    if payload is None:
        return None
    return {
        "user_id": 0,
        "username": payload["username"],
        "role": "admin",
        "jti": payload["jti"],
        "exp": payload["exp"],
    }


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    # Authentication middleware stores the already-validated user to avoid a
    # second Redis revocation lookup on normal API requests.
    user = getattr(request.state, "current_user", None)
    if user is None:
        user = await _decode_admin_credentials(credentials)
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="暂未登录或登录已过期",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_current_user_optional(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict | None:
    user = getattr(request.state, "current_user", None)
    if user is not None:
        return user
    return await _decode_admin_credentials(credentials)
